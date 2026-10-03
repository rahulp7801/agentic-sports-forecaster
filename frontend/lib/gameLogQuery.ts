import type {gameLogRequest} from './publicGameLogs.ts';

type Request = ReturnType<typeof gameLogRequest>;

const FILTERS=' WHERE sport=$1 '
  + 'AND ($6::text IS NULL OR player_id=$6) '
  + 'AND ($6::text IS NOT NULL OR $2=\'\' OR CASE WHEN $5 THEN lower(player_name)=lower($2) ELSE strpos(lower(player_name),lower($2))>0 END) '
  + 'AND ($4::date IS NULL OR game_date<$4::date) '
  + 'AND ($7::timestamptz IS NULL OR record_available_at<=$7::timestamptz) ';

/** Route a bound exact-athlete NFL core card to primary rows, not receiving supplements. */
export function gameLogQuery(query:Request) {
  const {sport,player,limit,before,exact,playerId,observedBefore,stat}=query;
  if(stat!==undefined && (sport!=='nfl' || !['pass_yds','rush_yds'].includes(stat)
    || !exact || !playerId || !before || !observedBefore)) throw new Error('Invalid core history query');
  const sql=stat!==undefined
    ? 'SELECT payload,source_row FROM ('
      + 'SELECT DISTINCT ON (sport,COALESCE(player_id,player_name),game_key) '
      + 'payload,source_row,game_date,player_name,game_key FROM dashboard_nfl_core_gamelogs_asof'
      + FILTERS
      + 'ORDER BY sport,COALESCE(player_id,player_name),game_key,record_available_at DESC NULLS LAST'
      + ') versions ORDER BY game_date DESC,player_name,game_key LIMIT $3'
    : (sport==='cfb' || sport==='nfl') && observedBefore!==null
      ? 'SELECT payload FROM ('
        + 'SELECT DISTINCT ON (sport,COALESCE(player_id,player_name),game_key) '
        + 'payload,game_date,player_name,game_key FROM dashboard_gamelog_versions'
        + FILTERS
        + 'ORDER BY sport,COALESCE(player_id,player_name),game_key,record_available_at DESC NULLS LAST'
        + ') versions ORDER BY game_date DESC,player_name,game_key LIMIT $3'
      : 'SELECT payload FROM dashboard_gamelogs_asof'+FILTERS
        + 'ORDER BY game_date DESC,player_name,game_key LIMIT $3';
  return {sql,args:[sport,player,limit,before,exact,playerId ?? null,observedBefore]};
}
