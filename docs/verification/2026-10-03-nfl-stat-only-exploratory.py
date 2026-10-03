from collections import Counter
from datetime import date
import hashlib, json
from pathlib import Path
from unittest.mock import patch
import polars as pl
from sportsbet.quant.history_tuning import PROPS, build_examples, evaluate_examples

ROOT = Path('.local/team-share-sources')
EXPECTED = {
 'stats_player_week_2023.parquet': 'ac776fbd7c9fefdb4069b72304f4c5fa05ae417acd49f6e4e27be14b9d7a4bbc',
 'stats_player_week_2024.parquet': '847569d194ca3d96b5efcf91e6eac5e18780fc47568a713fd545a82d29d155c1',
 'stats_player_week_2025.parquet': '2a461becaa9adb3c93a3074a3a31f1e960162a50163371a2d34e28393b5fff10',
 'games.parquet': '4f27270efeba3af862d250a821ff00578da1ce158b76576b72aa283751b22662',
}
for name, expected in EXPECTED.items():
 actual = hashlib.sha256((ROOT/name).read_bytes()).hexdigest()
 if actual != expected: raise ValueError('source hash mismatch: '+name)
schedules = {}
for game in pl.read_parquet(ROOT/'games.parquet').filter(pl.col('game_type')=='REG').iter_rows(named=True):
 if game['game_id'] in schedules: raise ValueError('duplicate schedule game')
 schedules[game['game_id']] = game
rows=[]; exclude=Counter()
for year in (2023,2024,2025):
 for row in pl.read_parquet(ROOT/f'stats_player_week_{year}.parquet').filter(pl.col('season_type')=='REG').select('player_id','season','week','game_id','team','receiving_yards','receptions').iter_rows(named=True):
  g=schedules.get(row['game_id'])
  if not g or g['season']!=row['season'] or g['week']!=row['week'] or row['team'] not in (g['home_team'],g['away_team']): exclude['schedule_mismatch']+=1; continue
  if not row['player_id']: exclude['missing_player']+=1; continue
  if row['receiving_yards'] is None or row['receptions'] is None: exclude['missing_stat']+=1; continue
  rows.append(dict(player=row['player_id'],season=row['season'],week=row['week'],game=row['game_id'],team=row['team'],day=date.fromisoformat(g['gameday']),receiving_yards=row['receiving_yards'],receptions=row['receptions']))
seen=Counter((r['player'],r['game']) for r in rows)
duplicates={k for k,n in seen.items() if n>1}
exclude['duplicate_rows']=sum(seen[k] for k in duplicates)
rows=[r for r in rows if (r['player'],r['game']) not in duplicates]
from sportsbet.quant.kalshi_pair_capture import unpack
_, shadow=unpack(json.loads(Path('.local/verified-timely-pair-20261003/pair.json').read_text()))
quoted={(f['gsis_player_id'],f['prop_type']) for f in shadow['forecasts']}
report={'status':'exploratory_unpriced_stat_only','sources':EXPECTED,'observed_rows':len(rows),'exclusions':dict(exclude),'props':{}}
for prop,stat in [('rec_yds','receiving_yards'),('receptions','receptions')]:
 with patch.dict(PROPS['nfl'],{prop:(stat,None,0)}):
  examples, coverage=build_examples(rows,'nfl',prop)
 result=evaluate_examples(examples)
 qualified=[e for e in examples if e.line >= (19.5 if prop=='rec_yds' else 2.5)]
 restricted=evaluate_examples(qualified)
 quote_restricted=evaluate_examples([e for e in qualified if (e.player,prop) in quoted])
 report['props'][prop]={'coverage':coverage,'evaluation':result,'restricted':restricted,'quoted_universe_restricted':quote_restricted}
 print(prop,'selected',result.get('selected'),'split_examples',result['counts'], 'held_brier_difference',result.get('paired_comparison',{}).get('brier_difference'),'held_brier_game_95',result.get('paired_comparison',{}).get('brier_game_95'),'restricted',restricted.get('selected'),restricted['counts'],restricted.get('paired_comparison',{}).get('brier_difference'),restricted.get('paired_comparison',{}).get('brier_game_95'),'quoted_universe',quote_restricted.get('selected'),quote_restricted['counts'],quote_restricted.get('paired_comparison',{}).get('brier_difference'),quote_restricted.get('paired_comparison',{}).get('brier_game_95'),flush=True)
Path('.local/nfl-stat-only-exploratory-20261003.json').write_text(json.dumps(report,indent=2,default=str))
