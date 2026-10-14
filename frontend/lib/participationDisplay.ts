import type {AvailabilityContextSplit} from './types';

export function contextWindowText(split:AvailabilityContextSplit) {
  if(!split.sample_window) return ['Dates for these participation groups were not retained in this forecast; their recency is unknown.'];
  return (['active','absent','unknown'] as const).flatMap(group=>{
    const range=split.sample_window![group];if(!range) return [];
    const label=group==='active' ? 'Recorded participation' : group==='absent' ? 'Recorded zero minutes' : 'Unknown participation';
    const age=Math.floor((Date.parse(split.sample_window!.cutoff)-Date.parse(range.newest))/86400000);
    return [`${label}: ${range.oldest} to ${range.newest}; latest ${age} day${age===1?'':'s'} before the target game.${age>30 ? ' This group does not establish current form.' : ''}`];
  });
}

export function recentParticipationText(split:AvailabilityContextSplit):string {
  const recent=split.recent_window;
  if(!recent) return 'A separate 30-day participation summary was not retained in this forecast.';
  const total=recent.active.games+recent.absent.games+recent.unknown_games;
  return `${recent.since} to ${recent.cutoff} (exclusive): ${total} retrieved game${total===1?'':'s'}; ${recent.unknown_games} with unknown participation, excluded from hit rates. Only the latest 40 eligible history games were checked; this is not a complete schedule audit.`;
}
