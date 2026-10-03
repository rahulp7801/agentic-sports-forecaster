from collections import Counter
from datetime import date
import csv,gzip,hashlib,io,json,math,statistics
from pathlib import Path
import numpy as np
import polars as pl
from sportsbet.quant import kalshi_role_shadow as role
from sportsbet.quant.kalshi_pair_capture import unpack
from sportsbet.quant.history_features import history_estimates
from sportsbet.quant.history_tuning import Correction, Example, score, compare, game_weights
from sportsbet.quant.backtest import _game_cluster_ratio_interval

def no_tail(examples, predicted_over, prior20_over):
 threshold=.75
 selected=[i for i,p in enumerate(predicted_over) if 1-float(p)>=threshold]
 chosen=[examples[i] for i in selected]
 result={'threshold':threshold,'selected_rows':len(chosen),'distinct_games':len({e.game for e in chosen}),
         'players':len({e.player for e in chosen}),'wins':sum(1-e.outcome for e in chosen),
         'row_win_rate':None,'game_balanced_win_rate':None,'mean_model_no':None,
         'game_cluster_win_rate_95':None,'candidate_minus_prior20':None}
 if not chosen:return result
 weights=game_weights(chosen)
 wins=np.asarray([1-e.outcome for e in chosen])
 no=np.asarray([1-float(predicted_over[i]) for i in selected])
 _,interval=_game_cluster_ratio_interval([(e.game,float(w*y),float(w))
     for e,w,y in zip(chosen,weights,wins,strict=True)],0,1)
 result.update(row_win_rate=float(np.mean(wins)),
     game_balanced_win_rate=float(np.average(wins,weights=weights)),
     mean_model_no=float(np.average(no,weights=weights)),
     game_cluster_win_rate_95=list(interval) if interval else None,
     candidate_minus_prior20=compare(chosen,np.asarray([prior20_over[i] for i in selected]),
                                     np.asarray([predicted_over[i] for i in selected])))
 return result
source=Path('.local/kalshi-source-20261003')
stats=[];snaps=[]
for kind,years in [('stats',(2024,2025)),('snaps',(2024,2025))]:
 for year in years:
  name=(f'stats_player_week_{year}.parquet' if kind=='stats' else f'snap_counts_{year}.parquet')
  path=source/name
  if hashlib.sha256(path.read_bytes()).hexdigest()!=role.SOURCES[(kind,year)][2]:raise ValueError('source changed')
  frame=pl.read_parquet(path).select(role.STATS_COLUMNS if kind=='stats' else role.SNAP_COLUMNS)
  (stats if kind=='stats' else snaps).extend((frame.filter(pl.col('season_type')=='REG') if kind=='stats' else frame.filter(pl.col('week')<=18)).to_dicts())
by_player,by_pfr,_=role._index(stats,snaps)
cross=Path('src/sportsbet/quant/nfl_role_sources.json.gz')
if hashlib.sha256(cross.read_bytes()).hexdigest()!=role.SOURCE_SHA256:raise ValueError('crosswalk changed')
bundle=json.loads(gzip.decompress(cross.read_bytes()))
ident=bundle['identity']
if hashlib.sha256(ident['response_text'].encode()).hexdigest()!=ident['source_sha256']:raise ValueError('crosswalk response changed')
pairs=Counter();pfr={}
for r in csv.DictReader(io.StringIO(ident['response_text'])):
 pairs[r['gsis_id']]+=1
 pfr[r['gsis_id']]=r['pfr_id']
_,shadow=unpack(json.loads(Path('.local/verified-timely-pair-20261003/pair.json').read_text()))
quoted={(f['gsis_player_id'],f['prop_type']) for f in shadow['forecasts'] if f['prop_type'] in ('rec_yds','receptions')}
schedules_path=Path('.local/team-share-sources/games.parquet')
if hashlib.sha256(schedules_path.read_bytes()).hexdigest()!='4f27270efeba3af862d250a821ff00578da1ce158b76576b72aa283751b22662':raise ValueError('schedule changed')
days={};ids={}
for game in pl.read_parquet(schedules_path).filter(pl.col('game_type')=='REG').iter_rows(named=True):
 for team in (role.team(game['home_team']),role.team(game['away_team'])):
  key=(game['season'],game['week'],team)
  if key in days:raise ValueError('duplicate team week')
  days[key]=date.fromisoformat(game['gameday']);ids[key]=game['game_id']
params=json.loads(Path('.local/nfl-stat-only-exploratory-20261003.json').read_text())['props']
print('quoted',len(quoted),'unique_ids',len({g for g,p in quoted}),'pfr_keys',len(by_pfr),'matches',sum(g in pfr for g,p in quoted),'snap_matches',sum(pfr.get(g) in by_pfr for g,p in quoted),flush=True)
collections={}
tails={}
excluded=Counter()
for prop,stat in [('rec_yds','receiving_yards'),('receptions','receptions')]:
 chosen=params[prop]['evaluation']['selected']
 meta=params[prop]['evaluation']['fitted_corrections'][chosen]
 fitted=Correction(np.array(meta['means']),np.array(meta['scales']),np.array(meta['coefficients']))
 examples=[];target_zero=[];baseline20=[]
 for gsis,p in sorted(quoted):
  if p!=prop:continue
  if pairs[gsis]!=1:excluded[prop+':identity']+=1;continue
  pid=pfr[gsis]
  for (season,week),snap in sorted(by_pfr.get(pid,{}).items()):
   if season!=2025 or (snap.get('offense_snaps') or 0)<=0:continue
   target_team=role.team(snap['team'])
   target_day=days.get((season,week,target_team))
   if target_day is None:excluded[prop+':schedule']+=1;continue
   if target_day<date(2025,11,1):continue
   prior_stats={k:r for k,r in by_player.get(gsis,{}).items() if k<(season,week)}
   prior_snaps={k:r for k,r in by_pfr[pid].items() if k<(season,week)}
   try:
    history=role._player_history(gsis,pid,stat,{gsis:prior_stats},{pid:prior_snaps})
    if len(history)<20:excluded[prop+':short_history']+=1;continue
    history=history[-40:]
    rows=[]
    for h in history:
     day=days.get((h['season'],h['week'],h['team']))
     if day is None or day>=target_day:raise ValueError('history_schedule')
     rows.append({'team':h['team'],'day':day,stat:h['value']})
    line=max(.5,math.floor(statistics.median(r[stat] for r in rows[-10:]))+.5)
    if line < (19.5 if prop=='rec_yds' else 2.5):excluded[prop+':low_line']+=1;continue
    target=by_player.get(gsis,{}).get((season,week))
    if target is not None and (role.team(target['team'])!=target_team or target.get(stat) is None):raise ValueError('target_mismatch')
    actual=target[stat] if target is not None else 0
    if not math.isfinite(actual):raise ValueError('target_invalid')
    est=history_estimates(rows,stat,None,target_day,line)
    example=Example('evaluate',ids[(season,week,target_team)],gsis,target_day,line,int(actual>line),est['base'],est['prior80'],est['recency'],est['features'],len(rows),est['role_drift'])
    examples.append(example);target_zero.append(target is None);baseline20.append((sum(r[stat]>line for r in rows[-20:])+.5)/21)
   except (KeyError,ValueError,TypeError) as e:excluded[prop+':'+str(e)]+=1
 predicted=fitted.predict(examples)
 for scope,indices in [('all',list(range(len(examples)))),('explicit_target_stat',[i for i,z in enumerate(target_zero) if not z])]:
  subset=[examples[i] for i in indices]
  cand=predicted[indices]
  base40=np.array([e.base for e in subset])
  base20=np.array([baseline20[i] for i in indices])
  collections[prop+':'+scope]={'candidate':score(subset,cand),'base40':score(subset,base40),'base20':score(subset,base20),'paired_candidate_minus_base40':compare(subset,base40,cand),'paired_candidate_minus_base20':compare(subset,base20,cand),'snap_only_target_zeros':sum(target_zero[i] for i in indices)}
  tails[prop+':'+scope]=no_tail(subset,cand,base20)
  print(prop,scope,len(subset),len({e.game for e in subset}),collections[prop+':'+scope]['paired_candidate_minus_base40']['brier_difference'],collections[prop+':'+scope]['paired_candidate_minus_base40']['brier_game_95'],flush=True)
result={'status':'exploratory_corrected_history_transfer_unpriced','sources_sha256_verified':True,'quoted_player_prop_pairs':len(quoted),'excluded':dict(excluded),'results':collections}
original_text=json.dumps(result,indent=2,sort_keys=True)
original_bytes=original_text.replace('\n','\r\n').encode()
if hashlib.sha256(original_bytes).hexdigest()!='a72ff20d2b86f65f35c12e91467c8057a37e5744b1e159c7394f2a6731a0f396':
 raise ValueError('Original corrected-transfer report changed')
Path('.local/nfl-stat-only-corrected-transfer-20261003.json').write_bytes(original_bytes)
original_report=Path('.local/nfl-stat-only-corrected-transfer-20261003.json')
tail_report={'protocol':'nfl-stat-only-corrected-history-no-tail-exploratory-v1',
             'status':'retrospective_unpriced_posthoc',
             'source_report_sha256':hashlib.sha256(original_report.read_bytes()).hexdigest(),
             'threshold_selected_after_prior_outcome_inspection':.75,
             'same_2026_quoted_player_prop_universe':len(quoted),
             'results':tails,'consumer_pick_qualified':False,'edge_established':False}
Path('.local/nfl-stat-only-corrected-tail-20261004.json').write_text(json.dumps(tail_report,indent=2,sort_keys=True))
