import type {AvailabilityContextSplit,AvailabilityEvidence,ContextDateRange,EVSignal,
  NextGenMetric,NextGenStatsEvidence,PlayerProfile,PropType,Sport} from './types';

export type SignalDisplayGame={game_id:string;home_team:string;away_team:string;date:string;sport:Sport};
type Row=Record<string,unknown>;
type Reader=(value:unknown)=>unknown;

const SPORTS=new Set(['nba','nfl','cfb']);
const PROPS=new Set(['points','rebounds','assists','threes','pra','steals','blocks',
  'pass_yds','pass_tds','rush_yds','rec_yds','receptions']);
const TRACKING_METRICS=new Set(['avg_time_to_throw','avg_completed_air_yards','avg_intended_air_yards',
  'aggressiveness','avg_separation','avg_cushion','avg_yac_above_expectation','efficiency',
  'percent_attempts_gte_eight_defenders','rush_yards_over_expected','avg_time_to_los']);

function invalid():never {throw Error('Invalid signal display');}
function object(value:unknown):Row {
  if(!value||typeof value!=='object'||Array.isArray(value)) return invalid();
  const prototype=Object.getPrototypeOf(value);
  if(prototype!==null&&prototype!==Object.prototype||Object.getOwnPropertySymbols(value).length) return invalid();
  if(Object.values(Object.getOwnPropertyDescriptors(value)).some(item=>!item.enumerable||!Object.hasOwn(item,'value'))) return invalid();
  return value as Row;
}
function text(value:unknown,maximum:number,empty=false):string {
  if(typeof value!=='string'||value.length>maximum||/[\u0000-\u001f]/.test(value)||(!empty&&!value.trim())) return invalid();
  return value;
}
function number(value:unknown,minimum=-Infinity,maximum=Infinity):number {
  if(typeof value!=='number'||!Number.isFinite(value)||value<minimum||value>maximum) return invalid();
  return value;
}
function integer(value:unknown,minimum:number,maximum:number):number {
  const result=number(value,minimum,maximum);
  return Number.isSafeInteger(result) ? result : invalid();
}
function boolean(value:unknown):boolean {return typeof value==='boolean' ? value : invalid();}
function enumeration<T extends string>(value:unknown,values:readonly T[]):T {
  return typeof value==='string'&&values.includes(value as T) ? value as T : invalid();
}
function timestamp(value:unknown):string {
  const result=text(value,64);
  return /([zZ]|[+-]\d\d:\d\d)$/.test(result)&&Number.isFinite(Date.parse(result)) ? result : invalid();
}
function day(value:unknown):string {
  const result=text(value,10),parsed=new Date(result+'T00:00:00Z');
  return /^\d{4}-\d{2}-\d{2}$/.test(result)&&Number.isFinite(parsed.valueOf())
    &&parsed.toISOString().slice(0,10)===result ? result : invalid();
}
function digest(value:unknown):string {
  const result=text(value,64);
  return /^[a-f0-9]{64}$/.test(result) ? result : invalid();
}
function https(value:unknown):string {
  const result=text(value,512),url=new URL(result);
  return url.protocol==='https:'&&!url.username&&!url.password ? result : invalid();
}
function array<T>(value:unknown,maximum:number,read:(item:unknown)=>T):T[] {
  if(!Array.isArray(value)||value.length>maximum||Object.keys(value).length!==value.length
    ||Object.getPrototypeOf(value)!==Array.prototype||Object.getOwnPropertySymbols(value).length
    ||Object.keys(value).some((key,index)=>key!==String(index))
    ||Object.entries(Object.getOwnPropertyDescriptors(value)).some(([key,item])=>key!=='length'
      &&(!item.enumerable||!Object.hasOwn(item,'value')))) return invalid();
  return value.map(read);
}
function optional(source:Row,target:Row,key:string,read:Reader) {
  if(source[key]!==undefined) target[key]=read(source[key]);
}
const nullableNumber=(value:unknown)=>value===null ? null : number(value,-10000,10000);

function range(value:unknown):ContextDateRange|null {
  if(value===null) return null;
  const source=object(value),oldest=day(source.oldest),newest=day(source.newest);
  if(oldest>newest) return invalid();
  return {oldest,newest};
}
function window(value:unknown):NonNullable<AvailabilityContextSplit['sample_window']> {
  const source=object(value);
  return {cutoff:day(source.cutoff),active:range(source.active),absent:range(source.absent),unknown:range(source.unknown)};
}
function cohort(value:unknown):AvailabilityContextSplit['active'] {
  const source=object(value);
  return {games:integer(source.games,0,100000),mean:nullableNumber(source.mean),
    hit_rate:source.hit_rate===null ? null : number(source.hit_rate,0,1)};
}
function recent(value:unknown):NonNullable<AvailabilityContextSplit['recent_window']> {
  const source=object(value);
  return {version:text(source.version,64) as NonNullable<AvailabilityContextSplit['recent_window']>['version'],
    since:day(source.since),cutoff:day(source.cutoff),active:cohort(source.active),absent:cohort(source.absent),
    unknown_games:integer(source.unknown_games,0,100000),sample_window:window(source.sample_window)};
}
function split(value:unknown):AvailabilityContextSplit {
  const source=object(value),result:Row={player:text(source.player,100),status:text(source.status,100),
    position:text(source.position,10),team:text(source.team,5),
    relationship:enumeration(source.relationship,['teammate','opponent']),unit:enumeration(source.unit,['offense','defense']),
    source:enumeration(source.source,['nflverse_snap_counts','nba_final_box_scores']),
    participation:enumeration(source.participation,['recorded unit snaps','recorded minutes']),
    evidence_version:text(source.evidence_version,64),unknown_games:integer(source.unknown_games,0,100000),
    active:cohort(source.active),absent:cohort(source.absent)};
  optional(source,result,'sample_window',window);optional(source,result,'recent_window',recent);
  return result as unknown as AvailabilityContextSplit;
}
function report(value:unknown):AvailabilityEvidence['teammates'][number] {
  const source=object(value),result:Row={player:text(source.player,100),status:text(source.status,100),
    position:text(source.position,10),reported_at:timestamp(source.reported_at)};
  optional(source,result,'team',value=>text(value,5));
  optional(source,result,'relationship',value=>enumeration(value,['teammate','opponent']));
  optional(source,result,'unit',value=>enumeration(value,['offense','defense']));
  optional(source,result,'source_url',https);optional(source,result,'source_sha256',digest);
  return result as AvailabilityEvidence['teammates'][number];
}
function availability(value:unknown):AvailabilityEvidence {
  const source=object(value);
  if(source.probability_adjusted!==false) return invalid();
  const result:Row={status:enumeration(source.status,['observed','unavailable']),
    roster_confirmed:boolean(source.roster_confirmed),subject_status:text(source.subject_status,100),
    teammates:array(source.teammates,64,report),probability_adjusted:false};
  // This is a serialized status shape, not an injury or eligibility decision.
  for(const key of ['source_url','roster_source_url','identity_source_url','player_image_url']) optional(source,result,key,https);
  for(const key of ['source_sha256','roster_source_sha256','identity_source_sha256']) optional(source,result,key,digest);
  optional(source,result,'captured_at',timestamp);optional(source,result,'team',value=>text(value,5));
  optional(source,result,'opponent_team',value=>text(value,5));optional(source,result,'player_id',value=>text(value,20));
  optional(source,result,'roster_player_name',value=>text(value,100));
  optional(source,result,'opponent_injury_coverage',value=>enumeration(value,['observed','unavailable']));
  optional(source,result,'context_splits',value=>array(value,8,split));
  if(result.status==='observed') {
    if(result.roster_confirmed!==true) return invalid();
    for(const key of ['captured_at','team','source_url','source_sha256','roster_source_url','roster_source_sha256'])
      if(result[key]===undefined) return invalid();
  }
  return result as unknown as AvailabilityEvidence;
}
function tracking(value:unknown):NextGenStatsEvidence {
  const source=object(value),metrics=object(source.metrics),entries=Object.entries(metrics);
  if(!entries.length||entries.length>TRACKING_METRICS.size||entries.some(([key])=>!TRACKING_METRICS.has(key))
    ||source.cutoff_exclusive!==true||source.probability_adjusted!==false) return invalid();
  const result:Row={status:enumeration(source.status,['observed']),stat_type:enumeration(source.stat_type,['passing','receiving','rushing']),
    sample_weeks:integer(source.sample_weeks,0,100000),cutoff_season:integer(source.cutoff_season,0,10000),
    cutoff_week:integer(source.cutoff_week,0,100),cutoff_exclusive:true,
    metrics:Object.fromEntries(entries.map(([key,value])=>[key,number(value,-10000,10000)])) as Partial<Record<NextGenMetric,number>>,
    source_provider:enumeration(source.source_provider,['nflverse_ngs']),source_url:https(source.source_url),
    source_sha256:digest(source.source_sha256),source_observed_at:timestamp(source.source_observed_at),probability_adjusted:false};
  optional(source,result,'evidence_version',value=>text(value,64));optional(source,result,'observed_before',timestamp);
  optional(source,result,'roster_team',value=>text(value,3));
  optional(source,result,'sample_periods',value=>array(value,1000,item=>{
    const row=object(item);
    return {season:integer(row.season,0,10000),week:integer(row.week,0,100),team:row.team===null ? null : text(row.team,3)};
  }));
  return result as unknown as NextGenStatsEvidence;
}
function profile(value:unknown):PlayerProfile {
  const source=object(value),result:Row={player:text(source.player,100),name:text(source.name,100),team:text(source.team,5),
    player_id:text(source.player_id,20),image_url:https(source.image_url),captured_at:timestamp(source.captured_at),
    source_url:https(source.source_url),source_sha256:digest(source.source_sha256)};
  optional(source,result,'jersey',value=>text(value,2));optional(source,result,'position',value=>text(value,10));
  optional(source,result,'identity_source_url',https);optional(source,result,'identity_source_sha256',digest);
  return result as unknown as PlayerProfile;
}

/** Decode already-approved outputs. No probability, gate, source policy or ranking is reconstructed. */
export function readSignalDisplay(value:unknown):EVSignal|null {
  try {
    const source=object(value);
    if(!SPORTS.has(source.sport as string)||!PROPS.has(source.prop_type as string)) return null;
    const odds=number(source.american_odds);
    if(!Number.isInteger(odds)||Math.abs(odds)<100) return null;
    const interval=source.confidence_interval===null ? null : array(source.confidence_interval,2,item=>number(item,0,1));
    if(interval&&(interval.length!==2||interval[0]>interval[1])) return null;
    const flags=object(source.injury_flags),entries=Object.entries(flags);
    if(entries.length>20) return null;
    const result:Row={id:text(source.id,128),player:text(source.player,100),team:text(source.team,20,true),
      opponent:text(source.opponent,20,true),home_team:text(source.home_team,100),away_team:text(source.away_team,100),
      sport:source.sport as Sport,prop_type:source.prop_type as PropType,line:number(source.line,0,10000),
      direction:enumeration(source.direction,['over','under']),true_prob:number(source.true_prob,0,1),
      implied_prob:number(source.implied_prob,0,1),ev_pct:number(source.ev_pct,-1,1),
      expected_return:source.expected_return===null ? null : number(source.expected_return),
      push_probability:number(source.push_probability,0,1),confidence_interval:interval,
      model_version:text(source.model_version,64),game_start_time:timestamp(source.game_start_time),
      kelly_fraction:number(source.kelly_fraction,0,1),american_odds:odds,sportsbook:text(source.sportsbook,64),
      trade_plan:array(source.trade_plan,3,item=>text(item,300,true)),
      injury_flags:Object.fromEntries(entries.map(([key,item])=>[text(key,64),text(item,300,true)])),
      market_type:text(source.market_type,100),snapped_at:timestamp(source.snapped_at),
      strength:enumeration(source.strength,['high','medium','low','unrated']),gated:boolean(source.gated),
      sample_size:integer(source.sample_size,0,100000),mean_stat:nullableNumber(source.mean_stat),game_id:text(source.game_id,128)};
    optional(source,result,'player_id',value=>text(value,20));optional(source,result,'captured_at',timestamp);
    optional(source,result,'gate_reason',value=>text(value,300));
    for(const key of ['history_policy_version','history_source_admission_policy']) optional(source,result,key,value=>text(value,64));
    optional(source,result,'history_observed_before',timestamp);optional(source,result,'history_source_verified',boolean);
    optional(source,result,'forecast_cutoff',day);optional(source,result,'availability',availability);
    optional(source,result,'next_gen_stats',tracking);optional(source,result,'player_profile',profile);
    return result as unknown as EVSignal;
  } catch {return null;}
}

function game(value:unknown):SignalDisplayGame {
  const source=object(value),date=text(source.date,8);
  if(!/^\d{8}$/.test(date)||!SPORTS.has(source.sport as string)) return invalid();
  day(`${date.slice(0,4)}-${date.slice(4,6)}-${date.slice(6,8)}`);
  return {game_id:text(source.game_id,128),home_team:text(source.home_team,100),away_team:text(source.away_team,100),
    date,sport:source.sport as Sport};
}

/** Bound and project display snapshots while retaining source order and explicit invalid-row counts. */
export function readSignalDisplaySnapshots(value:unknown,sport?:Sport) {
  if(sport!==undefined&&!SPORTS.has(sport)) return invalid();
  const snapshots=array(value,100,object),signals:EVSignal[]=[],games=new Map<string,SignalDisplayGame>();
  let generated_at:string|null=null,invalid_signals=0,total=0;
  for(const snapshot of snapshots) {
    const records=array(snapshot.signals ?? [],5000,item=>item);
    const snapshotGames=array(snapshot.games ?? [],100,game);
    if(snapshot.generated_at!==null||records.length||snapshotGames.length) {
      const generated=timestamp(snapshot.generated_at);
      if(generated_at===null||Date.parse(generated)>Date.parse(generated_at)) generated_at=generated;
    }
    total+=records.length;if(total>5000) return invalid();
    for(const value of records) {
      const signal=readSignalDisplay(value);
      if(!signal) invalid_signals++;else if(sport===undefined||signal.sport===sport) signals.push(signal);
    }
    for(const item of snapshotGames) {
      const key=item.sport+':'+item.game_id,previous=games.get(key);
      if(previous&&JSON.stringify(previous)!==JSON.stringify(item)) return invalid();
      games.set(key,item);
    }
  }
  return {generated_at,games:[...games.values()].filter(game=>sport===undefined||game.sport===sport),signals,invalid_signals};
}
