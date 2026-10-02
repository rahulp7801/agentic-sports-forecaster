import type {EVSignal} from './types';
import {calendarForm,historyCutoff,historyObservedBefore} from './forecastHistory.ts';
import {validPlayerId} from './publicGameLogs.ts';

/** The card uses the same exact-athlete, capture-time window as the evidence panel. */
export function pickCardFormRequest(signal:EVSignal) {
  if(!signal.player_id || !validPlayerId(signal.player_id,signal.sport)
    || signal.availability?.status!=='observed' || !signal.availability.roster_confirmed
    || !signal.availability.team) return null;
  try {
    const params=new URLSearchParams({sport:signal.sport,player:signal.player,
      player_id:signal.player_id,before:historyCutoff(signal),
      observed_before:historyObservedBefore(signal),exact:'1',limit:'20'});
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
  if(!sample.observed) return `${sample.games} ${team} game${sample.games===1?'':'s'} recorded in the prior 30 days; this stat was unavailable.${limit}`;
  return `${team} last 30 days: ${sample.observed} recorded stat${sample.observed===1?'':'s'} in ${sample.games} game${sample.games===1?'':'s'}, average ${sample.mean!.toFixed(1)} (line ${signal.line}). Latest ${sample.newest}.${limit}`;
}
