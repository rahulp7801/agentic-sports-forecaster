import type {Sport} from './types';
import type {scanStatus} from './scanStatus';

export type PublicScanStatus = ReturnType<typeof scanStatus>;
const SPORTS:readonly Sport[] = ['nba','nfl','cfb'];
const STATES=new Set(['not_run','unknown','running','interrupted','overdue','stale',
  'blocked','failed','degraded','partial','scheduled','no_games','no_quotes','complete']);
const TIMES=['updated_at','next_refresh_at','overdue_at','reserve_release_at'] as const;
const COUNTS=['eligible','completed','deferred','quotes','selections','model_requests',
  'model_estimates','unresolved_selections','missing_estimates'] as const;

function timestamp(value:unknown) {
  return typeof value==='string' && value.length<=64
    && /(?:Z|[+-]\d\d:\d\d)$/.test(value) && Number.isFinite(Date.parse(value));
}

function normalizedStatus(value:unknown):PublicScanStatus|null {
  if(!value || typeof value!=='object' || Array.isArray(value)) return null;
  const row=value as Record<string,unknown>;
  const legacyRolling=!Object.hasOwn(row,'rolling_release_at') && !Object.hasOwn(row,'rolling_release_passed');
  const rollingValid=legacyRolling || ((row.rolling_release_at===null || timestamp(row.rolling_release_at))
    && typeof row.rolling_release_passed==='boolean');
  const valid=rollingValid && typeof row.state==='string' && STATES.has(row.state)
    && typeof row.label==='string' && row.label.length>0 && row.label.length<=120
    && !/[\u0000-\u001f]/.test(row.label)
    && TIMES.every(key=>row[key]===null || timestamp(row[key]))
    && COUNTS.every(key=>row[key]===null
      || (Number.isSafeInteger(row[key]) && Number(row[key])>=0))
    && (row.recorded_budget_label===null
      || (typeof row.recorded_budget_label==='string'
        && row.recorded_budget_label.length<=120
        && !/[\u0000-\u001f]/.test(row.recorded_budget_label)))
    && typeof row.reserve_release_passed==='boolean';
  return valid ? {...row,rolling_release_at:legacyRolling ? null : row.rolling_release_at,
    rolling_release_passed:legacyRolling ? false : row.rolling_release_passed} as PublicScanStatus : null;
}

/** A 200 response without every requested league is unavailable, not an empty pipeline. */
export function scanRailRows(value:unknown,sport?:Sport):[Sport,PublicScanStatus][]|null {
  if(!value || typeof value!=='object' || Array.isArray(value)) return null;
  const data=value as Record<string,unknown>;
  const sports=sport ? [sport] : SPORTS;
  const rows=sports.map((key):[Sport,PublicScanStatus|null]=>[key,normalizedStatus(data[key])]);
  if(rows.some(([,status])=>!status)) return null;
  return rows as [Sport,PublicScanStatus][];
}
