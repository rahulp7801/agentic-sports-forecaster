import {publicContextWindow} from './contextWindow.ts';
import type {AvailabilityContextSplit} from './types';

type Recent=NonNullable<AvailabilityContextSplit['recent_window']>;
type Full=Pick<AvailabilityContextSplit,'active'|'absent'|'unknown_games'|'sample_window'>;
const groups=['active','absent','unknown'] as const;

/** Optional descriptive subset of the same retrieved, preforecast proof rows. */
export function publicRecentParticipation(value:unknown,full:Full,cutoff:unknown):Recent|undefined {
  if(!value || typeof value!=='object' || Array.isArray(value) || !full.sample_window) return undefined;
  const r=value as Record<string,unknown>;
  const time=typeof cutoff==='string' ? Date.parse(`${cutoff}T00:00:00Z`) : NaN;
  if(!Number.isFinite(time) || r.cutoff!==cutoff || r.version!=='participation-recent-30d-v1'
    || r.since!==new Date(time-30*86400000).toISOString().slice(0,10)) return undefined;
  const readCohort=(value:unknown,maximum:number)=>{
    if(!value || typeof value!=='object' || Array.isArray(value)) return undefined;
    const c=value as Record<string,unknown>;
    if(typeof c.games!=='number' || !Number.isSafeInteger(c.games) || c.games<0 || c.games>maximum) return undefined;
    if(c.games===0) return c.mean===null && c.hit_rate===null ? {games:0,mean:null,hit_rate:null} : undefined;
    if(typeof c.mean!=='number' || !Number.isFinite(c.mean) || Math.abs(c.mean)>10000
      || typeof c.hit_rate!=='number' || !Number.isFinite(c.hit_rate) || c.hit_rate<0 || c.hit_rate>1
      || Math.abs(c.hit_rate-Math.round(c.hit_rate*c.games)/c.games)>0.000051) return undefined;
    return {games:c.games,mean:c.mean,hit_rate:c.hit_rate};
  };
  const active=readCohort(r.active,full.active.games),absent=readCohort(r.absent,full.absent.games);
  if(!active || !absent || typeof r.unknown_games!=='number' || !Number.isSafeInteger(r.unknown_games)
    || r.unknown_games<0 || r.unknown_games>full.unknown_games) return undefined;
  const counts={active:active.games,absent:absent.games,unknown:r.unknown_games};
  const window=publicContextWindow(r.sample_window,counts,cutoff);
  if(!window) return undefined;
  for(const group of groups) {
    const range=window[group],whole=full.sample_window[group];
    const total=group==='unknown' ? full.unknown_games : full[group].games;
    if((range && (!whole || range.oldest<String(r.since) || range.oldest<whole.oldest || range.newest!==whole.newest))
      || (whole && ((whole.newest>=String(r.since)) !== (counts[group]>0)))
      || (whole && whole.oldest>=String(r.since) && counts[group]!==total)
      || (counts[group]===total && total>0 && (!range || !whole
        || range.oldest!==whole.oldest || range.newest!==whole.newest))) return undefined;
  }
  for(const [subset,whole] of [[active,full.active],[absent,full.absent]]) {
    if(subset.games===whole.games && (subset.mean!==whole.mean || subset.hit_rate!==whole.hit_rate)) return undefined;
  }
  return {version:'participation-recent-30d-v1',since:r.since as string,cutoff:cutoff as string,
    active,absent,unknown_games:r.unknown_games,sample_window:window};
}

export function recentParticipationText(split:AvailabilityContextSplit):string {
  const recent=split.recent_window;
  if(!recent) return 'A separate 30-day participation summary was not retained in this forecast.';
  const total=recent.active.games+recent.absent.games+recent.unknown_games;
  return `${recent.since} to ${recent.cutoff} (exclusive): ${total} retrieved game${total===1?'':'s'}; ${recent.unknown_games} with unknown participation, excluded from hit rates. Only the latest 40 eligible history games were checked; this is not a complete schedule audit.`;
}
