import type {AvailabilityContextSplit} from './types';

type Window=NonNullable<AvailabilityContextSplit['sample_window']>;
function validDay(value:unknown):value is string {
  if(typeof value!=='string' || !/^\d{4}-\d{2}-\d{2}$/.test(value) || value<'0001-01-01') return false;
  const day=new Date(`${value}T00:00:00Z`);
  return Number.isFinite(day.valueOf()) && day.toISOString().slice(0,10)===value;
}
/** Project dated descriptive cohorts, bound to this forecast's exclusive cutoff. */
export function publicContextWindow(value:unknown,counts:{active:number;absent:number;unknown:number},cutoff:unknown):Window|null {
  if(!value || typeof value!=='object' || Array.isArray(value)) return null;
  const source=value as Record<string,unknown>;
  if(!validDay(source.cutoff) || source.cutoff!==cutoff) return null;
  const result:Window={cutoff:source.cutoff,active:null,absent:null,unknown:null};
  for(const group of ['active','absent','unknown'] as const) {
    const row=source[group];
    if(counts[group]===0) {if(row!==null) return null;continue;}
    if(!row || typeof row!=='object' || Array.isArray(row)) return null;
    const range=row as Record<string,unknown>;
    if(!validDay(range.oldest) || !validDay(range.newest) || range.oldest>range.newest || range.newest>=source.cutoff) return null;
    result[group]={oldest:range.oldest,newest:range.newest};
  }
  return result;
}

export function contextWindowText(split:AvailabilityContextSplit) {
  if(!split.sample_window) return ['Dates for these participation groups were not retained in this forecast; their recency is unknown.'];
  return (['active','absent','unknown'] as const).flatMap(group=>{
    const range=split.sample_window![group];if(!range) return [];
    const label=group==='active' ? 'Recorded participation' : group==='absent' ? 'Recorded zero minutes' : 'Unknown participation';
    const age=Math.floor((Date.parse(split.sample_window!.cutoff)-Date.parse(range.newest))/86400000);
    return [`${label}: ${range.oldest} to ${range.newest}; latest ${age} day${age===1?'':'s'} before the target game.${age>30 ? ' This group does not establish current form.' : ''}`];
  });
}
