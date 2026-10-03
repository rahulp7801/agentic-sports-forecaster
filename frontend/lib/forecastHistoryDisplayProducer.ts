import {createHash} from 'node:crypto';
import {calendarForm,forecastHistory,historyCutoff,historyObservedBefore,recentForm} from './forecastHistory.ts';
import {pickCardFormSummary} from './pickCardForm.ts';
import {contextWindowText,recentParticipationText} from './participationDisplay.ts';
import {canonicalForecastDisplayJson} from './forecastDisplayPacket.ts';
import {readSignalDisplay} from './signalDisplay.ts';
import {readForecastHistoryDisplay,FORECAST_HISTORY_DISPLAY_PROTOCOL,
  type ForecastHistoryDisplay,type ForecastHistoryDisplayBinding,type ForecastHistoryDisplayScope} from './forecastHistoryDisplay.ts';
import type {EVSignal} from './types';

export const FORECAST_HISTORY_PRODUCER_VERSION='linework-private-history-display-v1';
export type ForecastHistorySourceRead={logs:unknown;game_date_before:string;source_observed_before:string};

/** Private output preparation; callers must resolve a stored forecast and an exact as-of read. */
export function forecastHistoryDisplay(signal:EVSignal,revision:string,source:ForecastHistorySourceRead|null):ForecastHistoryDisplay {
  const projected=readSignalDisplay(signal);
  if(!projected||!/^[a-f0-9]{64}$/.test(revision)) throw Error('Invalid forecast history subject');
  const subject={forecast_id:projected.id,forecast_record_sha256:createHash('sha256')
    .update(canonicalForecastDisplayJson(projected)).digest('hex'),sport:projected.sport,player:projected.player,
    player_id:projected.player_id ?? null,prop_type:projected.prop_type,line:projected.line,direction:projected.direction};
  let scope:ForecastHistoryDisplayScope={captured_at:null,game_date_before:null,source_observed_before:null,source_cutoff_kind:'unavailable'};
  const finish=(value:unknown)=>{
    const binding:ForecastHistoryDisplayBinding={revision,subject,scope};
    const result=readForecastHistoryDisplay(value,binding);
    if(!result) throw Error('Invalid forecast history display');
    return result;
  };
  const base=()=>({protocol:FORECAST_HISTORY_DISPLAY_PROTOCOL,producer_version:FORECAST_HISTORY_PRODUCER_VERSION,revision,subject,scope});
  const unavailable=(reason:string)=>finish({...base(),status:'unavailable',reason});
  try {
    const before=historyCutoff(projected),observed=historyObservedBefore(projected);
    // The unchanged history helper decides the cutoff. Its original known model
    // versions use selection time; older archive versions use forecast capture.
    const selected=projected.sport==='nba'&&projected.model_version==='empirical-jeffreys-v4-nba-source-asof-v1'
      ||projected.sport==='nfl'&&projected.model_version==='empirical-jeffreys-v4-nfl-history-v1'
      ||projected.sport==='cfb'&&projected.model_version==='empirical-jeffreys-v4-cfb-history-v1';
    scope={captured_at:projected.captured_at as string,game_date_before:before,source_observed_before:observed,
      source_cutoff_kind:selected ? 'model_selection' : 'forecast_capture'};
  } catch {return unavailable('forecast_timing_unavailable');}
  if(!source) return unavailable('history_source_unavailable');
  if(source.game_date_before!==scope.game_date_before||source.source_observed_before!==scope.source_observed_before)
    return unavailable('history_scope_mismatch');
  try {
    const windows={'10':forecastHistory(source.logs,projected,10),'20':forecastHistory(source.logs,projected,20)};
    const recent=recentForm(source.logs,projected),calendar=calendarForm(source.logs,projected);
    const card_summary=pickCardFormSummary(source.logs,projected);
    const context_labels=(projected.availability?.context_splits ?? []).map(split=>({player:split.player,team:split.team,
      relationship:split.relationship,unit:split.unit,window:contextWindowText(split),recent:recentParticipationText(split)}));
    return finish({...base(),status:'available',source_coverage:'bounded_as_of_records',windows,recent,calendar,card_summary,context_labels});
  } catch {return unavailable('history_records_unavailable');}
}
