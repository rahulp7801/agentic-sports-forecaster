"""Private offline single-pick accuracy experiment; no production promotion.

Filter the original earliest selection rather than searching later quotes.
Current-role estimates here are a stat-only diagnostic, not the frozen complete
participation shadow. Archived roster summaries cannot restore full source feeds.
"""
from __future__ import annotations
import argparse
from collections import Counter, defaultdict
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
from zoneinfo import ZoneInfo

from sportsbet.quant import current_history_replay as replay
from sportsbet.quant import priced_recent_form as recent
from sportsbet.quant import edge_search_stress as search

PROTOCOL = {'version':'individual-pick-accuracy-v1', 'target_probability':.75,
    'recent_games':10, 'current_role_prior_strength':20, 'minimum_current_games':2,
    'maximum_recent_gap_days':30, 'maximum_roster_age_seconds':3600,
    'rules':['original_75','recent_agreement_75','recent_and_current_role_75'],
    'selection':'Original earliest EV-qualified pick per player/game, then filter; never replace rejected picks',
    'scope':'Previously inspected historical archive; exploratory and private; no promotion'}


def context(row, entry):
    a=row.get('availability')
    if not isinstance(a,dict) or a.get('status')!='observed' or a.get('roster_confirmed') is not True:
        return None,'missing_recorded_roster'
    observed=replay.stamp(a.get('captured_at'))
    if observed is None or not 0<=(entry-observed).total_seconds()<=3600:
        return None,'stale_or_future_roster'
    if not all(replay.digest(a.get(k)) for k in ('source_sha256','roster_source_sha256')):
        return None,'missing_roster_commitment'
    if not isinstance(a.get('team'),str) or not a['team'] or len(a['team'])>30:
        return None,'missing_recorded_team'
    return a,None


def bound_history(sample, snapshot, sport, player, prop):
    source='cfb' if sport=='cfb' else 'nfl_receiving' if prop in ('rec_yds','receptions') else 'nfl_base'
    id_key='athlete_id' if sport=='cfb' else 'player_id'
    records=defaultdict(list)
    for row in snapshot[source]:
        if str(row[id_key])==str(player):records[row['source_record_sha256']].append(row)
    rows=[]
    for key,value,sha in sample:
        matches=records[sha]
        if len(matches)!=1:return None,'ambiguous_history_binding'
        row=matches[0]
        row_key=(row['game_date'],str(row['game_id'])) if sport=='cfb' else (row['season'],row['week'])
        if tuple(key)!=row_key or row.get(replay.COLUMNS[prop])!=value:return None,'invalid_history_binding'
        rows.append((row,value))
    return rows,None


def current_role(sample, snapshot, sport, player, prop, day, team):
    rows,reason=bound_history(sample,snapshot,sport,player,prop)
    if rows is None:return None,reason
    season=day.year if day.month>=9 else day.year-1
    field='team_abbreviation' if sport=='cfb' else 'team'
    # A latest-game team change cannot be hidden by older same-team observations.
    if not rows or rows[0][0].get(field)!=team:return None,'latest_team_mismatch'
    current=[v for r,v in rows if r['season']==season and r.get(field)==team]
    older=[v for r,v in rows if not (r['season']==season and r.get(field)==team)]
    if len(current)<PROTOCOL['minimum_current_games']:return None,'insufficient_current_role_games'
    if not older:return None,'missing_prior_role_games'
    return {'current':current,'older':older},None


def role_probability(values,line,direction):
    hit=lambda v:v>line if direction=='over' else v<line
    prior=(sum(hit(v) for v in values['older'])+.5)/(len(values['older'])+1)
    return (sum(hit(v) for v in values['current'])+20*prior)/(len(values['current'])+20)


def decide(c, sample, role, recent_gap_days):
    """Outcome-free fixed rule, with explicit missing-data abstention."""
    p=c['probability'];line=float(c['x']['row']['line']);direction=c['x']['row']['direction']
    valid=len(sample)>=20 and recent_gap_days is not None and 0<=recent_gap_days<=30
    hit=lambda v:v>line if direction=='over' else v<line
    rp=(sum(hit(v) for _,v,_ in sample[:10])+.5)/11 if valid else None
    cp=role_probability(role,line,direction) if role is not None else None
    original=p>=.75
    agrees=original and rp is not None and rp>=.75
    return {'original_75':original,'recent_agreement_75':agrees,
        'recent_and_current_role_75':agrees and cp is not None and cp>=.75,
        'recent_probability':rp,'current_role_probability':cp,
        'consensus_score':min(p,rp,cp) if rp is not None and cp is not None else None}


def teammate_group(a,entry):
    reports=a.get('teammates') if a else None
    if not isinstance(reports,list) or len(reports)>64:return 'unknown'
    # Legacy reports did not distinguish teammate/opponent; never infer a causal effect.
    if any(not isinstance(r,dict) or r.get('relationship') not in ('teammate','opponent')
           or replay.stamp(r.get('reported_at')) is None or replay.stamp(r['reported_at'])>entry for r in reports):
        return 'unknown'
    return 'reported_teammate_absence' if any(r['relationship']=='teammate' and
        r.get('status','').lower() in ('out','inactive','doubtful','injured reserve','suspension') for r in reports) else 'no_reported_teammate_absence'


def run(rows,snapshot,sport):
    original,excluded=search.frozen.observations(rows,sport,'empirical-jeffreys-v4')
    history=replay.History(snapshot);samples={};observed=[];missing=Counter()
    for x in original:
        day=x['start'].astimezone(ZoneInfo('America/New_York')).date()
        key=(x['row']['player_id'],x['row']['prop_type'],day,x['entry'])
        if key not in samples:samples[key]=history.sample(sport,key[0],key[1],day,x['entry'])[0]
        sample=samples[key];estimate=replay.estimate(sample,float(x['row']['line']))
        if estimate is None or estimate['n']<20 or estimate['push_probability']!=0:
            missing['insufficient_as_of_history']+=1;continue
        observed.append(dict(x,p=estimate['p'],n=estimate['n'],sample=sample,day=day))
    selected=search.select_model(observed);rules={k:[] for k in PROTOCOL['rules']};details=[];groups=defaultdict(list)
    for c in selected:
        x=c['x'];row=x['row'];sample=x['sample'];day=x['day'];a,reason=context(row,x['entry'])
        role=None
        if a:role,reason=current_role(sample,snapshot,sport,row['player_id'],row['prop_type'],day,a['team'])
        bound,_=bound_history(sample,snapshot,sport,row['player_id'],row['prop_type'])
        latest=bound[0][0] if bound else None
        dates=([datetime.fromisoformat(latest['game_date']).date()] if sport=='cfb' else
            history.schedule[latest['season'],latest['week'],latest['team']]) if latest else []
        gap=(day-dates[0]).days if len(set(dates))==1 else None
        decision=decide(c,sample,role,gap)
        for name in rules:
            if decision[name]:rules[name].append(c)
        if decision['original_75']:
            group=teammate_group(a,x['entry']);groups[group].append(c)
            details.append(dict(prediction_id=row['prediction_id'],player=row['player'],sport=sport,
                prop_type=row['prop_type'],direction=row['direction'],line=row['line'],american_odds=row['american_odds'],
                decision_at=c['decision'].isoformat(),model_probability=c['probability'],
                market_probability=x['q'] if row['direction']=='over' else 1-x['q'],
                outcome=search.result(c),recent_gap_days=gap,current_role_reason=reason,
                current_role_games=len(role['current']) if role else None,teammate_group=group,**decision))
    def summary(cs):return dict(accuracy=recent.accuracy(cs),performance=search.metrics(cs))
    return dict(sport=sport,eligible_quotes=len(original),replayed_quotes=len(observed),
        archive_exclusions=excluded,history_exclusions=dict(missing),original_selected=len(selected),
        rules={k:summary(v) for k,v in rules.items()},
        rejected_by_context=summary([c for c in rules['original_75'] if c not in rules['recent_and_current_role_75']]),
        teammate_slices={k:summary(v) for k,v in groups.items()},individual_picks=details,promote=False)


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--ledger-path',type=Path,required=True);p.add_argument('--history-path',type=Path,required=True)
    p.add_argument('--output',type=Path,required=True);args=p.parse_args()
    rows=search.frozen.OfflineLedger(args.ledger_path).predictions();snapshot=json.loads(args.history_path.read_text())
    report=dict(protocol=PROTOCOL,observed_at=datetime.now(timezone.utc).isoformat(),
        inputs={p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in (args.ledger_path,args.history_path)},
        implementation_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        dependencies={Path(m.__file__).name:hashlib.sha256(Path(m.__file__).read_bytes()).hexdigest() for m in (replay,recent,search,search.frozen)},
        limitations=['Previously inspected archive; no untouched holdout or prospective accuracy claim.',
            'Rules filter identical original selections; no replacement quotes, parlays, or production picks.',
            'Current-role calculation uses retained stat rows, not verified complete participation; distinct from frozen role shadow.',
            'Roster summaries are archived commitments, not a replay of original raw roster feeds.',
            'Teammate groups are descriptive; untyped legacy reports remain unknown and do not change probabilities.',
            'Consensus scores are not calibrated probabilities; actual selected-model calibration is reported separately.',
            'Game intervals are exploratory, unadjusted for multiple rules and repeated players.',
            'NBA has no retained quote cohort and cannot be evaluated.'],reports={})
    for sport in ('nfl','cfb'):
        report['reports'][sport]=run(rows,snapshot,sport);print(sport+' individual-pick replay complete',flush=True)
    args.output.parent.mkdir(parents=True,exist_ok=True)
    args.output.write_text(json.dumps(report,indent=2,allow_nan=False),encoding='utf-8')

if __name__=='__main__':main()
