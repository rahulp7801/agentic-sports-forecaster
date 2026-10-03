import {createHash} from 'node:crypto';

type CoreRow={payload:unknown;source_row?:unknown};
const FIELDS=['player_id','season','week','team','passing_yards','rushing_yards',
  'receiving_yards','receptions'] as const;
const KEYS=[...FIELDS,'source_record_sha256'];
const HASH=/^[0-9a-f]{64}$/;

/** Recheck the Python ingestion commitment before displaying a core stat. */
export function nflCoreHistoryPayloads(rows:readonly CoreRow[]):unknown[] {
  return rows.map(({payload,source_row})=>{
    if(!source_row || typeof source_row!=='object' || Array.isArray(source_row)) {
      throw new Error('NFL core source row unavailable');
    }
    const row=source_row as Record<string,unknown>;
    if(Object.keys(row).length!==KEYS.length || KEYS.some(key=>!Object.hasOwn(row,key))
      || typeof row.player_id!=='string' || !row.player_id.trim()
      || typeof row.team!=='string' || !row.team.trim()
      || !Number.isSafeInteger(row.season) || (row.season as number)<0
      || !Number.isSafeInteger(row.week) || (row.week as number)<0
      || FIELDS.slice(4).some(key=>row[key]!==null && !Number.isSafeInteger(row[key]))
      || typeof row.source_record_sha256!=='string' || !HASH.test(row.source_record_sha256)) {
      throw new Error('NFL core source row invalid');
    }
    const digest=(legacy:boolean)=>{
      const ordered=[...FIELDS].filter(key=>!legacy || key!=='receptions').sort();
      const record=Object.fromEntries(ordered.map(key=>[key,row[key]]));
      return createHash('sha256').update(JSON.stringify(record)).digest('hex');
    };
    if(row.source_record_sha256!==digest(false) && row.source_record_sha256!==digest(true)) {
      throw new Error('NFL core source row commitment mismatch');
    }
    return payload;
  });
}
