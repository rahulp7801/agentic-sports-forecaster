import type {EVSignal} from './types';
import {calendarForm,historyCutoff,historyObservedBefore} from './forecastHistory.ts';
import {validPlayerId} from './publicGameLogs.ts';
import {capturedRosterTeam} from './pickContext.ts';

/** Stable card input retaining every field needed to validate as-of form. */
export function pickCardFormSnapshot(signal:EVSignal):EVSignal {
  const availability=signal.availability;
  return {player:signal.player,player_id:signal.player_id,sport:signal.sport,
    forecast_cutoff:signal.forecast_cutoff,snapped_at:signal.snapped_at,
    captured_at:signal.captured_at,game_start_time:signal.game_start_time,
    model_version:signal.model_version,history_policy_version:signal.history_policy_version,
    history_observed_before:signal.history_observed_before,
    prop_type:signal.prop_type,line:signal.line,direction:signal.direction,
    ...(availability ? {availability:{status:availability.status,
      roster_confirmed:availability.roster_confirmed,captured_at:availability.captured_at,
      team:availability.team}} : {})} as EVSignal;
}

/** The card uses the same exact-athlete, capture-time window as the evidence panel. */
export function pickCardFormRequest(signal:EVSignal) {
  if(!signal.player_id || !validPlayerId(signal.player_id,signal.sport)
    || !capturedRosterTeam(signal)) return null;
  try {
    const params=new URLSearchParams({sport:signal.sport,player:signal.player,
      player_id:signal.player_id,before:historyCutoff(signal),
      observed_before:historyObservedBefore(signal),exact:'1',limit:'20'});
    if(signal.sport==='nfl' && (signal.prop_type==='pass_yds' || signal.prop_type==='rush_yds'))
      params.set('stat',signal.prop_type);
    return `/api/gamelogs?${params}`;
  } catch {return null;}
}

/** Descriptive only: no history-derived probability or pick eligibility change. */
export function pickCardFormSummary(logs:unknown,signal:EVSignal) {
  const form=calendarForm(logs,signal);
  const team=form.capturedTeam;
  const sample=form.capturedTeamSample;
  if(!team || !sample) return 'Current-team form was not verified at forecast capture.';
  const limit=form.limitedToLatest20 ? ' Only the latest 20 records were checked.' : '';
  if(!sample.games) return `No ${team} game appears in the retrieved records from the prior 30 days.${limit}`;
  if(!sample.newestObserved) return `${sample.games} ${team} game${sample.games===1?'':'s'} recorded in the prior 30 days; this stat was unavailable. Latest recorded game ${sample.newest}; no observed stat in these records. This does not establish current form.${limit}`;
  const daysBeforeStat=Math.round((Date.parse(form.before)-Date.parse(sample.newestObserved))/86400000);
  const latest=`Latest observed stat ${sample.newestObserved}, ${daysBeforeStat} day${daysBeforeStat===1?'':'s'} before the target game.`;
  const missingLatest=sample.newest!==sample.newestObserved
    ? ` Newer recorded game ${sample.newest} has no observed value for this stat.` : '';
  const stale=daysBeforeStat>14 ? ' This does not establish current form.' : '';
  return `${team} last 30 days: ${sample.observed} recorded stat${sample.observed===1?'':'s'} in ${sample.games} game${sample.games===1?'':'s'}, average ${sample.mean!.toFixed(1)} (line ${signal.line}). ${latest}${missingLatest}${stale}${limit}`;
}
