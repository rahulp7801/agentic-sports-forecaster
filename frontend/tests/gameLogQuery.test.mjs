import test from 'node:test';
import assert from 'node:assert/strict';
import {gameLogRequest} from '../lib/publicGameLogs.ts';
import {gameLogQuery} from '../lib/gameLogQuery.ts';

test('exact NFL core form reads primary source rows with both cutoffs bound',()=>{
  const base={sport:'nfl',player:'Player',player_id:'00-0000001',exact:'1',limit:'20',
    before:'2026-10-04',observed_before:'2026-10-04T19:00:00Z'};
  const core=gameLogQuery(gameLogRequest(new URLSearchParams({...base,stat:'pass_yds'})));
  assert.match(core.sql,/FROM dashboard_nfl_core_gamelogs_asof/);
  assert.match(core.sql,/SELECT payload,source_row/);
  assert.match(core.sql,/SELECT DISTINCT ON \(sport,COALESCE\(player_id,player_name\),game_key\)/);
  assert.match(core.sql,/record_available_at DESC NULLS LAST/);
  assert.match(core.sql,/\) versions ORDER BY game_date DESC,player_name,game_key LIMIT \$3/);
  assert.doesNotMatch(core.sql,/dashboard_gamelog_versions/);
  assert.match(core.sql,/game_date<\$4::date/);
  assert.match(core.sql,/record_available_at<=\$7::timestamptz/);
  assert.deepEqual(core.args,['nfl','Player',20,'2026-10-04',true,'00-0000001','2026-10-04T19:00:00Z']);
  assert.doesNotMatch(core.sql,/00-0000001|2026-10-04T19:00:00Z/);
  const receiving=gameLogQuery(gameLogRequest(new URLSearchParams(base)));
  assert.match(receiving.sql,/FROM dashboard_gamelog_versions/);
  assert.doesNotMatch(receiving.sql,/dashboard_nfl_core_gamelogs_asof/);
  assert.doesNotMatch(receiving.sql,/source_row/);
});
