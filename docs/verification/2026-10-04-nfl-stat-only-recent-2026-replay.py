import argparse
from collections import Counter
from datetime import date
import csv,gzip,hashlib,io,json,math,statistics
from pathlib import Path
import numpy as np
import polars as pl
from sportsbet.quant import kalshi_role_shadow as role
from sportsbet.quant import kalshi_stat_only_tail_calibration as tail_calibration
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
DEFAULT_OUTPUT=Path('.local/nfl-stat-only-recent-2026-verified-20261004.json')
parser=argparse.ArgumentParser(description='Hash-pinned offline recent-season stress test')
parser.add_argument('--output',type=Path,default=DEFAULT_OUTPUT)
parser.add_argument('--recent-role-diagnostic',action='store_true',
                    help='Separate posthoc recent-form bins; does not alter the base report')
parser.add_argument('--tail-calibration-diagnostic',action='store_true',
    help='Test already frozen 2025 lower-tail offsets on the fixed 2026 examples')
parser.add_argument('--freshness-diagnostic',action='store_true',
    help='Separate posthoc last-played-game age bins on the fixed high-NO examples')
args=parser.parse_args()
if sum((args.recent_role_diagnostic,args.tail_calibration_diagnostic,args.freshness_diagnostic))>1:
    parser.error('Use one separate diagnostic at a time')
if (args.recent_role_diagnostic or args.tail_calibration_diagnostic or args.freshness_diagnostic) and args.output==DEFAULT_OUTPUT:
    parser.error('Diagnostic requires a separate output path')

source=Path('.local/kalshi-source-20261003')
stats=[];snaps=[]
for kind,years in [('stats',(2024,2025,2026)),('snaps',(2024,2025,2026))]:
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
pair_path=Path('.local/verified-timely-pair-20261003/pair.json')
pair_sha256='8df6075f9794837f9c99772cf70d5dbdfb7954a07421ebfda0345494637e9acb'
if hashlib.sha256(pair_path.read_bytes()).hexdigest()!=pair_sha256:raise ValueError('quoted-player cohort changed')
_,shadow=unpack(json.loads(pair_path.read_text()))
quoted={(f['gsis_player_id'],f['prop_type']) for f in shadow['forecasts'] if f['prop_type'] in ('rec_yds','receptions')}
schedules_path=Path('.local/team-share-sources/games.parquet')
if hashlib.sha256(schedules_path.read_bytes()).hexdigest()!='4f27270efeba3af862d250a821ff00578da1ce158b76576b72aa283751b22662':raise ValueError('schedule changed')
days={};ids={}
for game in pl.read_parquet(schedules_path).filter(pl.col('game_type')=='REG').iter_rows(named=True):
 for team in (role.team(game['home_team']),role.team(game['away_team'])):
  key=(game['season'],game['week'],team)
  if key in days:raise ValueError('duplicate team week')
  days[key]=date.fromisoformat(game['gameday']);ids[key]=game['game_id']
model_report=Path('.local/nfl-stat-only-exploratory-20261003.json')
if hashlib.sha256(model_report.read_bytes()).hexdigest()!='c44edb356c163113140863d22d0a1b62440be8bff11df6edae0e39ca7eb69557':raise ValueError('selected model report changed')
params=json.loads(model_report.read_text())['props']
tail_offsets=tail_calibration.offsets(tail_calibration.pinned_history(model_report)) \
    if args.tail_calibration_diagnostic else None
print('quoted',len(quoted),'unique_ids',len({g for g,p in quoted}),'pfr_keys',len(by_pfr),'matches',sum(g in pfr for g,p in quoted),'snap_matches',sum(pfr.get(g) in by_pfr for g,p in quoted),flush=True)
collections={}
tails={}
recent_roles={}
freshness_bins={}
tail_calibration_results={}
excluded=Counter()
for prop,stat in [('rec_yds','receiving_yards'),('receptions','receptions')]:
 chosen=params[prop]['evaluation']['selected']
 meta=params[prop]['evaluation']['fitted_corrections'][chosen]
 fitted=Correction(np.array(meta['means']),np.array(meta['scales']),np.array(meta['coefficients']))
 examples=[];target_zero=[];baseline20=[];last_played_age=[]
 for gsis,p in sorted(quoted):
  if p!=prop:continue
  if pairs[gsis]!=1:excluded[prop+':identity']+=1;continue
  pid=pfr[gsis]
  for (season,week),snap in sorted(by_pfr.get(pid,{}).items()):
   if season!=2026 or (snap.get('offense_snaps') or 0)<=0:continue
   target_team=role.team(snap['team'])
   target_day=days.get((season,week,target_team))
   if target_day is None:excluded[prop+':schedule']+=1;continue
   if not date(2026,9,1)<=target_day<date(2026,10,4):continue
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
    age=(target_day-rows[-1]['day']).days
    if age<1:raise ValueError('invalid_last_game_age')
    examples.append(example);target_zero.append(target is None);baseline20.append((sum(r[stat]>line for r in rows[-20:])+.5)/21)
    last_played_age.append(age)
   except (KeyError,ValueError,TypeError) as e:excluded[prop+':'+str(e)]+=1
 predicted=fitted.predict(examples)
 for scope,indices in [('all',list(range(len(examples)))),('explicit_target_stat',[i for i,z in enumerate(target_zero) if not z])]:
  subset=[examples[i] for i in indices]
  cand=predicted[indices]
  base40=np.array([e.base for e in subset])
  base20=np.array([baseline20[i] for i in indices])
  collections[prop+':'+scope]={'candidate':score(subset,cand),'base40':score(subset,base40),'base20':score(subset,base20),'paired_candidate_minus_base40':compare(subset,base40,cand),'paired_candidate_minus_base20':compare(subset,base20,cand),'snap_only_target_zeros':sum(target_zero[i] for i in indices)}
  tails[prop+':'+scope]=no_tail(subset,cand,base20)
  if args.tail_calibration_diagnostic:
   fixed=[i for i,p in enumerate(cand) if 1-float(p)>=.75]
   if len(fixed)!=tails[prop+':'+scope]['selected_rows']:
    raise ValueError('Fixed original NO selection changed')
   supported=[];bands=Counter();unsupported=Counter()
   for i in fixed:
    over=float(cand[i])
    band=next((name for name in tail_offsets[prop]
               if float(name.split('-')[0])<=over<float(name.split('-')[1])),None)
    if band is None:
     unsupported['outside_frozen_over_bands']+=1
     continue
    corrected=over+float(tail_offsets[prop][band])
    if not 0<corrected<1:raise ValueError('Invalid corrected probability')
    supported.append((i,corrected));bands[band]+=1
   picked=[subset[i] for i,p in supported]
   original=np.asarray([cand[i] for i,p in supported])
   adjusted=np.asarray([p for i,p in supported])
   reference=np.asarray([base20[i] for i,p in supported])
   tail_calibration_results[prop+':'+scope]={
      'original_selected_rows':len(fixed),
      'supported_rows':len(supported),'unsupported':dict(unsupported),
      'supported_games':len({e.game for e in picked}),
      'supported_wins':sum(1-e.outcome for e in picked),
      'over_probability_bands':dict(sorted(bands.items())),
      'mean_original_no':float(np.mean(1-original)) if supported else None,
      'mean_corrected_no':float(np.mean(1-adjusted)) if supported else None,
      'corrected_at_least_75':int(np.sum(1-adjusted>=.75)),
      'original_score':score(picked,original),
      'corrected_score':score(picked,adjusted),
      'prior20_score':score(picked,reference),
      'paired_corrected_minus_original':compare(picked,original,adjusted) if supported else None,
      'paired_corrected_minus_prior20':compare(picked,reference,adjusted) if supported else None}
  if args.recent_role_diagnostic and prop=='receptions':
   high=[(e,1-float(p)) for e,p in zip(subset,cand,strict=True) if 1-float(p)>=.75]
   labels={'recent_mean_down':lambda e:e.features[3]<=-.5,
           'recent_mean_stable':lambda e:-.5<e.features[3]<.5,
           'recent_mean_up':lambda e:e.features[3]>=.5}
   bins={}
   for name,condition in labels.items():
    group=[(e,p) for e,p in high if condition(e)]
    n=len(group)
    wins=sum(1-e.outcome for e,p in group)
    bins[name]={'rows':n,'games':len({e.game for e,p in group}),
                'wins':wins,'row_win_rate':(wins/n if n else None),
                'mean_model_no':(sum(p for e,p in group)/n if n else None)}
   if sum(b['rows'] for b in bins.values())!=tails[prop+':'+scope]['selected_rows']:
    raise ValueError('Recent-role bins changed high-confidence denominator')
   recent_roles[scope]=bins
  if args.freshness_diagnostic:
   high=[(subset[j],1-float(cand[j]),last_played_age[indices[j]])
         for j in range(len(subset)) if 1-float(cand[j])>=.75]
   bins={}
   for name,condition in (
      ('last_game_1_to_10_days',lambda age:age<=10),
      ('last_game_11_to_30_days',lambda age:10<age<=30),
      ('last_game_over_30_days',lambda age:age>30)):
    group=[(e,p,age) for e,p,age in high if condition(age)]
    n=len(group);wins=sum(1-e.outcome for e,p,age in group)
    bins[name]={'rows':n,'games':len({e.game for e,p,age in group}),
                'wins':wins,'row_win_rate':(wins/n if n else None),
                'mean_model_no':(sum(p for e,p,age in group)/n if n else None)}
   if sum(b['rows'] for b in bins.values())!=tails[prop+':'+scope]['selected_rows']:
    raise ValueError('Freshness bins changed high-confidence denominator')
   freshness_bins[prop+':'+scope]=bins
  print(prop,scope,len(subset),len({e.game for e in subset}),collections[prop+':'+scope]['paired_candidate_minus_base40']['brier_difference'],collections[prop+':'+scope]['paired_candidate_minus_base40']['brier_game_95'],flush=True)
result={'protocol':'nfl-stat-only-recent-2026-corrected-history-exploratory-v1',
        'status':'retrospective_unpriced_2026_played_games',
        'model_report_sha256':'c44edb356c163113140863d22d0a1b62440be8bff11df6edae0e39ca7eb69557',
        'quoted_cohort_pair_sha256':pair_sha256,
        'schedule_sha256':'4f27270efeba3af862d250a821ff00578da1ce158b76576b72aa283751b22662',
        'target_season':2026,'target_game_date_before':'2026-10-04',
        'quoted_player_prop_pairs':len(quoted),'excluded':dict(excluded),
        'results':collections,'no_tail':tails,
        'historical_market_prices_available':False,
        'consumer_pick_qualified':False,'edge_established':False}
if args.recent_role_diagnostic:
 result['protocol']='nfl-stat-only-recent-2026-role-diagnostic-posthoc-v1'
 result['recent_form_bins']=recent_roles
if args.tail_calibration_diagnostic:
 result['protocol']='nfl-stat-only-recent-2026-tail-calibration-posthoc-v1'
 result['historical_selection_report_sha256']=tail_calibration.HISTORY_SHA256
 result['tail_calibration_offsets']={prop:{band:str(value) for band,value in offsets.items()}
     for prop,offsets in tail_offsets.items()}
 result['fixed_original_no_tail_calibration']=tail_calibration_results
if args.freshness_diagnostic:
 result['protocol']='nfl-stat-only-recent-2026-freshness-diagnostic-posthoc-v1'
 result['last_played_game_age_bins']=freshness_bins
output=args.output
if output.exists() or output.is_symlink():raise ValueError('Recent replay output already exists')
output.write_text(json.dumps(result,indent=2,sort_keys=True))
print('recent_report',output,'results',len(collections),flush=True)
