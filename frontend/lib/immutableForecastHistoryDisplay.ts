import {createHash} from 'node:crypto';
import {canonicalForecastDisplayJson} from './forecastDisplayPacket.ts';
import {readSignalDisplay} from './signalDisplay.ts';
import {resolveImmutableForecast,type ImmutableForecastRead,type ImmutableForecastContext} from './immutableForecastHistory.ts';
import {immutableHistoryCalculations} from './immutableHistoryCalculations.ts';
import {nflCoreHistoryPayloads} from './nflCoreHistoryEvidence.ts';
import {publicGameLogs} from './publicGameLogs.ts';
import {FORECAST_HISTORY_DISPLAY_PROTOCOL,readForecastHistoryDisplay,
  type ForecastHistoryDisplay,type ForecastHistoryDisplayBinding,type ForecastHistoryDisplayAvailableScope} from './forecastHistoryDisplay.ts';
import type {EVSignal} from './types';

export const IMMUTABLE_HISTORY_DISPLAY_PRODUCER_VERSION='linework-private-immutable-history-display-v1';
export type ImmutableHistoryDisplayReads={predictionRead:ImmutableForecastRead;
  approvedRecordRead:(request:Readonly<{id:string;revision:string}>)=>Promise<unknown>;
  historyRead:(sql:string,args:readonly unknown[])=>Promise<unknown[]>};
export type ImmutableHistoryDisplayResolution={status:'resolved';display:ForecastHistoryDisplay}
  |{status:'unavailable';reason:'invalid_request'|'prediction_unavailable'|'receipt_unavailable'
    |'history_context_unavailable'|'chronology_unavailable'|'approved_record_unavailable'|'approved_record_mismatch'};

const HASH=/^[a-f0-9]{64}$/;
function exact(value:unknown,keys:readonly string[]):Record<string,unknown> {
  if(!value||typeof value!=='object'||Array.isArray(value)) throw Error('Unavailable');
  const prototype=Object.getPrototypeOf(value),descriptors=Object.getOwnPropertyDescriptors(value);
  if(prototype!==Object.prototype&&prototype!==null||Reflect.ownKeys(value).length!==keys.length
    ||keys.some(key=>!Object.hasOwn(descriptors,key))
    ||Object.values(descriptors).some(item=>!item.enumerable||!Object.hasOwn(item,'value'))) throw Error('Unavailable');
  // Snapshot own data values. Do not invoke Proxy get traps or reread caller objects after awaits.
  return Object.fromEntries(keys.map(key=>[key,descriptors[key].value]));
}
function hash(value:unknown):string {
  if(typeof value!=='string'||!HASH.test(value)) throw Error('Unavailable');
  return value;
}
function privateJson(value:unknown):unknown {
  let nodes=0,bytes=0;
  const account=(json:string)=>{
    bytes+=new TextEncoder().encode(json).length;
    if(bytes>1024*1024) throw Error('Unavailable');
  };
  const copy=(item:unknown,depth:number):unknown=>{
    if(++nodes>50_000||depth>32) throw Error('Unavailable');
    if(item===null||typeof item==='boolean'||typeof item==='string'||typeof item==='number'&&Number.isFinite(item)) {
      if(typeof item==='string'&&item.length>1024*1024) throw Error('Unavailable');
      account(JSON.stringify(item));return item;
    }
    if(!item||typeof item!=='object') throw Error('Unavailable');
    const descriptors=Object.getOwnPropertyDescriptors(item),keys=Reflect.ownKeys(item);
    if(keys.length>50_000||keys.some(key=>typeof key!=='string')) throw Error('Unavailable');
    if(Array.isArray(item)) {
      const length:unknown=descriptors.length?.value;
      if(Object.getPrototypeOf(item)!==Array.prototype||typeof length!=='number'||!Number.isSafeInteger(length)
        ||length<0||length>50_000||keys.length!==length+1) throw Error('Unavailable');
      bytes+=2+Math.max(0,length-1);if(bytes>1024*1024) throw Error('Unavailable');
      return Array.from({length},(_,index)=>{
        const entry=descriptors[index];
        if(!entry?.enumerable||!Object.hasOwn(entry,'value')) throw Error('Unavailable');
        return copy(entry.value,depth+1);
      });
    }
    const prototype=Object.getPrototypeOf(item);
    if(prototype!==Object.prototype&&prototype!==null
      ||Object.values(descriptors).some(entry=>!entry.enumerable||!Object.hasOwn(entry,'value'))) throw Error('Unavailable');
    bytes+=2+Math.max(0,keys.length-1);if(bytes>1024*1024) throw Error('Unavailable');
    return Object.fromEntries(Object.keys(descriptors).map(key=>{
      if(key.length>1024*1024) throw Error('Unavailable');
      account(JSON.stringify(key)+':');return [key,copy(descriptors[key].value,depth+1)];
    }));
  };
  const normalized=copy(value,0);
  canonicalForecastDisplayJson(normalized); // Retain the shared one-MiB encoded bound.
  return normalized;
}
function denseRows(value:unknown):unknown[] {
  if(!Array.isArray(value)||Object.getPrototypeOf(value)!==Array.prototype) throw Error('Unavailable');
  const length:unknown=Object.getOwnPropertyDescriptor(value,'length')?.value;
  if(typeof length!=='number'||!Number.isSafeInteger(length)||length<0||length>20
    ||Reflect.ownKeys(value).length!==length+1) throw Error('Unavailable');
  // Bound and copy private callback data before any projection; getters and exotic JSON fail closed.
  return privateJson(value) as unknown[];
}
function sameContext(record:EVSignal,retained:ImmutableForecastContext):boolean {
  const fields=['id','game_id','sport','player','player_id','prop_type','line','direction','snapped_at',
    'captured_at','game_start_time','model_version','forecast_cutoff','history_policy_version','history_observed_before'] as const;
  if(fields.some(key=>record[key]!==retained[key])) return false;
  const original=retained.availability,approved=record.availability;
  if(!original) return approved===undefined;
  if(!approved||approved.status!==original.status||approved.roster_confirmed!==original.roster_confirmed) return false;
  // Unavailable optional roster fields were not retained in the minimal context and are never used.
  return original.status!=='observed'||approved.captured_at===original.captured_at&&approved.team===original.team;
}

/** PRIVATE preparation: injected trusted readers only; no DB, live route or caller-selected history scope. */
export async function buildImmutableHistoryDisplay(request:unknown,reads:ImmutableHistoryDisplayReads,now=Date.now()):Promise<ImmutableHistoryDisplayResolution> {
  const unavailable=(reason:Extract<ImmutableHistoryDisplayResolution,{status:'unavailable'}>['reason']):ImmutableHistoryDisplayResolution=>({status:'unavailable',reason});
  let id:string,payload_sha256:string,forecast_record_sha256:string,revision:string;
  let predictionRead:ImmutableForecastRead,approvedRecordRead:ImmutableHistoryDisplayReads['approvedRecordRead'],historyRead:ImmutableHistoryDisplayReads['historyRead'];
  try {
    const wanted=exact(request,['id','payload_sha256','forecast_record_sha256','revision']);
    id=hash(wanted.id);payload_sha256=hash(wanted.payload_sha256);
    forecast_record_sha256=hash(wanted.forecast_record_sha256);revision=hash(wanted.revision);
    const callbacks=exact(reads,['predictionRead','approvedRecordRead','historyRead']);
    if(Object.values(callbacks).some(callback=>typeof callback!=='function')) return unavailable('invalid_request');
    predictionRead=callbacks.predictionRead as ImmutableForecastRead;
    approvedRecordRead=callbacks.approvedRecordRead as ImmutableHistoryDisplayReads['approvedRecordRead'];
    historyRead=callbacks.historyRead as ImmutableHistoryDisplayReads['historyRead'];
  } catch {return unavailable('invalid_request');}
  const resolution=await resolveImmutableForecast({id,payload_sha256},predictionRead,now);
  if(resolution.status==='unavailable') return resolution;
  let envelope:Record<string,unknown>,projected:EVSignal;
  try {
    envelope=exact(await approvedRecordRead({id,revision}),['revision','record']);
    // The separate approved-output lookup is version-bound; original ledger TEXT uses another hash.
    const normalized=privateJson(envelope.record);
    const record=readSignalDisplay(normalized);
    if(!record) return unavailable('approved_record_unavailable');
    projected=record;
  } catch {return unavailable('approved_record_unavailable');}
  if(envelope.revision!==revision||projected.id!==id
    ||createHash('sha256').update(canonicalForecastDisplayJson(projected)).digest('hex')!==forecast_record_sha256
    ||!sameContext(projected,resolution.context)) return unavailable('approved_record_mismatch');
  const retained=resolution.context,before=resolution.query.args[3],observed=resolution.query.args[6];
  if(typeof before!=='string'||typeof observed!=='string') return unavailable('history_context_unavailable');
  const selected=retained.sport==='nba'&&retained.model_version==='empirical-jeffreys-v4-nba-source-asof-v1'
    ||retained.sport==='nfl'&&retained.model_version==='empirical-jeffreys-v4-nfl-history-v1'
    ||retained.sport==='cfb'&&retained.model_version==='empirical-jeffreys-v4-cfb-history-v1';
  const scope:ForecastHistoryDisplayAvailableScope={captured_at:retained.captured_at,game_date_before:before,
    source_observed_before:observed,source_cutoff_kind:selected ? 'model_selection' : 'forecast_capture'};
  const subject={forecast_id:id,forecast_record_sha256,sport:retained.sport,player:retained.player,
    player_id:retained.player_id,prop_type:retained.prop_type,line:retained.line,direction:retained.direction};
  const binding:ForecastHistoryDisplayBinding={revision,subject,scope};
  const base={protocol:FORECAST_HISTORY_DISPLAY_PROTOCOL,producer_version:IMMUTABLE_HISTORY_DISPLAY_PRODUCER_VERSION,revision,subject,scope};
  const finish=(value:unknown):ImmutableHistoryDisplayResolution=>{
    const display=readForecastHistoryDisplay(value,binding);
    if(!display) throw Error('Unavailable');
    return {status:'resolved',display};
  };
  const noHistory=(reason:string)=>finish({...base,status:'unavailable',reason});
  let rows:unknown[];
  try {rows=await historyRead(resolution.query.sql,[...resolution.query.args]);}
  catch {return noHistory('history_source_unavailable');}
  try {
    const core=retained.sport==='nfl'&&(retained.prop_type==='pass_yds'||retained.prop_type==='rush_yds');
    const wrappers=denseRows(rows).map(row=>exact(row,core ? ['payload','source_row'] : ['payload']));
    const values=core ? nflCoreHistoryPayloads(wrappers.map(row=>({payload:row.payload,source_row:row.source_row})),retained.player_id)
      : wrappers.map(row=>row.payload);
    const logs=publicGameLogs(values,retained.sport);
    if(logs.some(row=>row.player_id!==retained.player_id||String(row.date)>=before)) return noHistory('history_records_unavailable');
    const calculated=immutableHistoryCalculations(logs,retained);
    // Participation splits are not resolved by the minimal immutable context yet.
    // Omit labels instead of treating later approved-record enrichment as retained source proof.
    return finish({...base,status:'available',source_coverage:'bounded_as_of_records',...calculated,context_labels:[]});
  } catch {return noHistory('history_records_unavailable');}
}
