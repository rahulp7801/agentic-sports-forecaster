"""Daily read-only orchestration: refresh histories, collect markets, evaluate props."""
from __future__ import annotations

from sportsbet.config import DEFAULT_DAILY_CREDIT_LIMIT, settings

import argparse
import asyncio
import inspect
import json
import os
import re
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import TypedDict

from langgraph.graph import END, START, StateGraph

from sportsbet.dashboard import load_snapshot, publish_snapshot
from sportsbet.diagnostics import error_fields, failure_stage
from sportsbet.market_watch import run as watch, DEFAULT_GAME_LIMIT
from sportsbet.live_settlement_ledger import Ledger
from sportsbet.model_contract import MODEL_VERSION
from sportsbet.nba_source_asof import model_version_for
from sportsbet.picks import build_pick_board
from sportsbet.player_profiles import run as refresh_profiles
from sportsbet.refresh import refresh_history
from sportsbet.scan import run as scan, timestamp, prop_credit_holdback, MARKETS
from sportsbet.schedules import collect as collect_schedule
from sportsbet.settlement import pending_schedule_offsets, settle_final_props

MODES=('daily','monitor','public_daily','public_monitor')
PUBLIC_SCOPES={
    'public_daily':(
        'Public-only daily collection: Kalshi markets, PrizePicks projections when publicly available, '
        'ESPN schedules, source-backed player profile metadata, NBA/NFL history refresh, and settlement evaluation. Sportsbooks and prop '
        'recommendations are not requested. Partial market sampling is retained explicitly. This is periodic collection, '
        'not continuous arbitrage monitoring.'
    ),
    'public_monitor':(
        'Public-only market observation: Kalshi markets and ESPN schedules. History refresh, '
        'settlement evaluation, player profile refresh, sportsbooks, PrizePicks and prop recommendations are not requested. '
        'Partial market sampling is retained explicitly. This is periodic collection, not continuous '
        'arbitrage monitoring.'
    ),
}


PUBLIC_MARKET_REUSE = timedelta(minutes=10)
PROFILE_READY_TIMEOUT_SECONDS = 120


def reusable_public_market(snapshot: object, sport: str, mode: str,
                           now: datetime) -> bool:
    """Reuse only a recent complete capture for the same public source scope."""
    if not isinstance(snapshot,dict) or mode not in ('public_monitor','public_daily'):
        return False
    if (snapshot.get('schema_version')!=2 or snapshot.get('sport')!=sport
            or snapshot.get('execution_ready') is not False
            or not isinstance(snapshot.get('comparisons'),list)
            or not isinstance(snapshot.get('evidence_sha256'),str)
            or re.fullmatch('[0-9a-f]{64}',snapshot['evidence_sha256']) is None):
        return False
    if not isinstance(snapshot.get('captured_at'),str):
        return False
    try:
        captured=datetime.fromisoformat(snapshot['captured_at'].replace('Z','+00:00'))
        age=now-captured
    except (KeyError,TypeError,ValueError):
        return False
    if not timedelta(0)<=age<=PUBLIC_MARKET_REUSE:
        return False
    sources=snapshot.get('sources')
    if not isinstance(sources,dict) or set(sources)!= {'sportsbook','kalshi','prizepicks'}:
        return False
    expected={'sportsbook':'not_requested','kalshi':'observed',
              'prizepicks':'observed' if mode=='public_daily' else 'not_requested'}
    # A complete daily capture is a recent superset of the monitor's sources.
    # Reusing it avoids fetching the same public quotes in adjacent cron slots.
    if (mode=='public_monitor' and isinstance(sources['prizepicks'],dict)
            and sources['prizepicks'].get('status')=='observed'):
        expected['prizepicks']='observed'
    return all(isinstance(sources[name],dict)
               and sources[name].get('status')==status
               and sources[name].get('partial_coverage') is (status=='not_requested')
               for name,status in expected.items())


class DailyState(TypedDict, total=False):
    sports: list[str]
    mode: str
    daily_credit_limit: int
    histories: dict
    markets: dict
    schedules: dict
    schedule_evidence: dict
    settlements: dict
    props: dict
    profiles: dict
    profile_readiness: dict
    report: dict


def _diagnosed_node(action, stage):
    # Preserve LangGraph's async/sync execution choice and the original error.
    if inspect.iscoroutinefunction(action):
        async def guarded(state):
            with failure_stage('daily', stage):
                return await action(state)
    else:
        def guarded(state):
            with failure_stage('daily', stage):
                return action(state)
    return guarded


def create_daily_graph():
    graph=StateGraph(DailyState)

    async def initialize(state):
        # Futures belong to this invocation, including when a compiled graph is reused.
        return {'profile_readiness':{sport:asyncio.get_running_loop().create_future()
            for sport in state['sports']} if state['mode']=='public_daily' else {}}

    async def catchup_schedule(sport,now,current,*,offload=False):
        def offsets_to_collect():
            try:
                extra=pending_schedule_offsets(Ledger(),sport,now)
            except Exception:
                extra=()
            return tuple(sorted(set(range(-7,-1))|set(extra)))
        offsets=await asyncio.to_thread(offsets_to_collect) if offload else offsets_to_collect()
        older=await collect_schedule(sport,now,offsets=offsets)
        combined={**current,'captured_at':older['captured_at'],
            'games':older.get('games',[])+current.get('games',[]),
            'failures':older.get('failures',[])+current.get('failures',[]),
            'sources':older.get('sources',[])+current.get('sources',[]),
            'partial':older.get('status')!='complete' or current.get('status')!='complete'}
        combined['status']='complete' if not combined['partial'] else 'unavailable' if (
            older.get('status')=='unavailable' and current.get('status')=='unavailable') else 'partial'
        return combined

    async def schedules(state):
        results={};evidence={};pending=[]
        readiness=state['profile_readiness']
        try:
            for sport in state['sports']:
                catchup=state['mode'] in ('daily','public_daily')
                now=datetime.now(timezone.utc)
                current=await collect_schedule(sport,now)
                publish_snapshot('schedule:'+sport,current)
                results[sport]={'status':current['status'],'captured_at':current['captured_at']}
                if catchup and state['mode']!='public_daily':
                    evidence[sport]=await catchup_schedule(sport,now,current)
                else:
                    evidence[sport]=current
                future=await collect_schedule(sport,now,offsets=(2,3,4,5,6))
                partial=current['status']!='complete' or future['status']!='complete'
                slate={**current,'captured_at':future['captured_at'],
                    'games':current.get('games',[])+future.get('games',[]),
                    'failures':current.get('failures',[])+future.get('failures',[]),
                    'sources':current.get('sources',[])+future.get('sources',[]),
                    'partial':partial,'status':'complete' if not partial else 'unavailable' if (
                        current['status']=='unavailable' and future['status']=='unavailable') else 'partial'}
                publish_snapshot('slate:'+sport,slate)
                results[sport].update(slate_status=slate['status'],slate_captured_at=slate['captured_at'])
                if state['mode']=='public_daily':
                    readiness[sport].set_result(slate['captured_at'])
                    pending.append((sport,now,current))
            # Fresh per-sport inputs are released before unrelated historical reads.
            for sport,now,current in pending:
                evidence[sport]=await catchup_schedule(sport,now,current,offload=True)
        finally:
            for ready in readiness.values():
                if not ready.done(): ready.set_result(None)
        return {'schedules':results,'schedule_evidence':evidence}

    async def histories(state):
        results={}
        if state['mode']=='public_monitor':
            return {'histories':{sport:{'status':'not_requested'} for sport in state['sports']}}
        for sport in state['sports']:
            now=datetime.now(timezone.utc)
            if state['mode'] in ('daily','public_daily'):
                result=await asyncio.to_thread(refresh_history,sport,now.date())
            else:
                result=load_snapshot('refresh:'+sport) or {'status':'not_run'}
                try:
                    # Compare after the read: a concurrent refresh may finish during I/O.
                    age=datetime.now(timezone.utc)-timestamp(result['finished_at'])
                    if result['status']!='complete' or not timedelta(0)<=age<=timedelta(hours=36):
                        result={'status':'stale'}
                except (KeyError,ValueError,TypeError,AttributeError):
                    result={'status':'not_run'}
            results[sport]=result
        return {'histories':results}

    async def markets(state):
        results={};profiles={sport:dict(status='not_requested',reason='public_daily_only') for sport in state['sports']}
        public=state['mode'].startswith('public_')
        held=prop_credit_holdback(state['sports'],state['daily_credit_limit'])
        market_holdback=held+max(len(MARKETS[s]) for s in state['sports']) if held else 0
        for sport in state['sports']:
            pair_state='market_unavailable' if state['mode']=='public_daily' and sport=='nfl' else None
            try:
                public_provider='public' if state['mode']=='public_daily' else 'kalshi'
                cached=None
                if public:
                    try:
                        cached=load_snapshot('markets:'+sport)
                    except Exception:
                        pass  # A failed cache read must not hide source availability.
                if reusable_public_market(cached,sport,state['mode'],datetime.now(timezone.utc)):
                    summary=cached
                    if pair_state is not None:
                        pair_state='market_reused'
                else:
                    summary,archive=await watch(sport,state['daily_credit_limit'],DEFAULT_GAME_LIMIT,True,
                        **({'provider':public_provider} if public else {'credit_holdback':market_holdback,'sportsbook_cadence_hours':6}))
                    if pair_state is not None:
                        source_dir=os.environ.get('KALSHI_PAIR_SOURCE_DIR')
                        output=os.environ.get('KALSHI_PAIR_OUTPUT')
                        if archive is None:
                            pair_state='archive_unavailable'
                        elif not source_dir or not output:
                            pair_state='not_configured'
                        elif (manifest_path:=Path(source_dir)/'source-manifest.json').is_symlink() or not manifest_path.is_file():
                            pair_state='source_unavailable'
                        else:
                            # This private research receipt is made at the free
                            # capture, before NBA refresh/settlement can age it out.
                            # A failure cannot change public data or consumer picks.
                            try:
                                from sportsbet.quant.kalshi_pair_capture import capture, save_pair
                                from sportsbet.quant.kalshi_ask_policy import freeze as freeze_ask_policy
                                from sportsbet.quant.kalshi_prior20_ask_policy import freeze as freeze_prior20_policy
                                market_archive=json.loads(Path(archive).read_text(encoding='utf-8'))
                                manifest=json.loads(manifest_path.read_text(encoding='utf-8'))
                                pair=await asyncio.to_thread(capture,market_archive,Path(source_dir),
                                    started_at=datetime.now(timezone.utc),source_manifest=manifest)
                                pair['ask_policy']=freeze_ask_policy(pair)
                                pair['prior20_ask_policy']=freeze_prior20_policy(pair)
                                save_pair(pair,Path(output))
                                pair_state='captured_local'
                            except Exception as exc:
                                pair_state='capture_failed'
                                import structlog
                                structlog.get_logger().warning('kalshi_pair_unavailable',
                                    error_type=type(exc).__name__)
                requested=[source for source in summary['sources'].values() if source['status']!='not_requested']
                complete = bool(requested) and all(
                    source['status']=='observed' and not source.get('partial_coverage',True)
                    for source in requested
                )
                status='complete' if complete else 'degraded'
                if public:
                    status='observed' if summary['sources'].get('kalshi',{}).get('status')=='observed' else 'degraded'
                results[sport]=dict(status=status,
                    sources=summary['sources'],captured_at=summary['captured_at'])
                if pair_state is not None:
                    # Aggregate diagnostics only; the player-level receipt stays private.
                    results[sport]['research_pair_status']=pair_state
            except Exception as exc:
                results[sport]=dict(status='failed',**error_fields(exc))
                if pair_state is not None:
                    results[sport]['research_pair_status']=pair_state
            if state['mode']=='public_daily':
                try:
                    try:
                        slate_at=await asyncio.wait_for(asyncio.shield(state['profile_readiness'][sport]),PROFILE_READY_TIMEOUT_SECONDS)
                    except TimeoutError:
                        slate_at=None
                    result=(await refresh_profiles([sport],expected_public_captures={sport:dict(
                        market_captured_at=results[sport].get('captured_at'),slate_captured_at=slate_at)}))[sport]
                    status='complete' if result['public_input_status']=='observed' and result['unavailable']==0 else 'degraded'
                    profiles[sport]=dict(result,status=status)
                except Exception as exc:
                    profiles[sport]=dict(status='failed',**error_fields(exc))
        return {'markets':results,'profiles':profiles}

    async def props(state):
        if state['mode'].startswith('public_'):
            return {'props':{sport:{'status':'not_requested','reason':'public_only_collection'} for sport in state['sports']}}
        ready=[s for s in state['sports'] if state['histories'][s]['status']=='complete']
        results={}
        for sport in set(state['sports'])-set(ready):
            result=dict(status='blocked',reason='history_refresh_unavailable',sport=sport,
                finished_at=datetime.now(timezone.utc).isoformat(),execution_ready=False)
            publish_snapshot('scan:'+sport,result)
            results[sport]=result
        if ready:
            try:
                results.update(await scan(ready,state['daily_credit_limit']))
            except Exception as exc:
                for sport in ready:
                    result=dict(status='failed',**error_fields(exc),sport=sport,
                        finished_at=datetime.now(timezone.utc).isoformat(),execution_ready=False)
                    publish_snapshot('scan:'+sport,result)
                    results[sport]=result
        if 'nfl' in ready and isinstance(results.get('nfl'),dict) and results['nfl'].get('scan_id'):
            from sportsbet.db.connection import create_async_pool
            from sportsbet.quant import nfl_corrected_workload_paper as workload_paper
            from sportsbet.quant import nfl_stat_only_paper as stat_only_paper
            research = (
                ('stat-only', stat_only_paper),
                ('corrected-workload', workload_paper),
            )
            pool=None
            try:
                pool=await create_async_pool(max_size=2)
                for label,paper in research:
                    capture_key=f'research:{label}-capture:nfl'
                    report_key=f'{label}-shadow-validation:nfl'
                    try:
                        captured=(results['nfl'].get('stat_only_capture')
                                  if label=='stat-only' else None)
                        if captured is None:
                            captured=await paper.capture(pool,results['nfl']['scan_id'])
                        publish_snapshot(capture_key,captured)
                        publish_snapshot(report_key,await paper.report(pool))
                    except Exception as exc:
                        try:
                            publish_snapshot(capture_key,
                                dict(status='unavailable',error_type=type(exc).__name__))
                        except Exception:
                            pass
            except Exception as exc:
                for label,_ in research:
                    try:
                        publish_snapshot(f'research:{label}-capture:nfl',
                            dict(status='unavailable',error_type=type(exc).__name__))
                    except Exception:
                        pass
            finally:
                if pool is not None:
                    try:
                        await pool.close()
                    except Exception:
                        pass
        return {'props':results}

    async def settlements(state):
        if state['mode']=='public_monitor':
            return {'settlements':{sport:{'status':'not_requested','reason':'monitor_mode'}
                for sport in state['sports']}}
        try:
            ledger=Ledger()
        except Exception as exc:
            return {'settlements':{sport:{'status':'failed','error_type':type(exc).__name__}
                for sport in state['sports']}}
        results={}
        for sport in state['sports']:
            if state['histories'][sport]['status']!='complete':
                results[sport]={'status':'blocked','reason':'history_refresh_unavailable'}
                continue
            try:
                results[sport]=await asyncio.to_thread(
                    settle_final_props,ledger,sport,state['schedule_evidence'][sport])
            except Exception as exc:
                results[sport]={'status':'failed','error_type':type(exc).__name__}
        try:
            publish_snapshot('metrics:all',ledger.report(model_version=MODEL_VERSION))
            publish_snapshot('metrics:recommendations',ledger.report(True,model_version=MODEL_VERSION))
            prediction_rows=ledger.predictions()
            for sport in state['sports']:
                publish_snapshot(f'metrics:all:{sport}',ledger.report(model_version=model_version_for(sport),sport=sport))
                publish_snapshot(f'metrics:recommendations:{sport}',
                    ledger.report(True,model_version=model_version_for(sport),sport=sport))
                publish_snapshot(f'picks:{sport}',build_pick_board(prediction_rows,sport))
                from sportsbet.quant.history_shadow_audit import publish_history_shadow
                publish_history_shadow(prediction_rows,sport,publish_snapshot)
        except Exception as exc:
            for result in results.values():
                if result['status']=='complete':
                    result.update(status='failed',error_type=type(exc).__name__)
        return {'settlements':results}

    def report(state):
        public=state['mode'].startswith('public_')
        groups=('markets','schedules') if public else ('histories','markets','props','schedules','settlements')
        if state['mode']=='public_daily':groups+=('histories','settlements','profiles')
        accepted=('complete','observed') if public else ('complete',)
        healthy=all(r['status'] in accepted or (group=='props' and r['status']=='scheduled')
            for group in groups for r in state[group].values())
        result=dict(mode=state['mode'],finished_at=datetime.now(timezone.utc).isoformat(),
            status=('observed' if public else 'complete') if healthy else 'degraded',execution_ready=False,
            histories=state['histories'],markets=state['markets'],schedules=state['schedules'],
            settlements=state['settlements'],profiles=state['profiles'],
            props={s:{k:v for k,v in r.items() if k not in ('attempts','coverage')} for s,r in state['props'].items()})
        if public:
            result['scope']=PUBLIC_SCOPES[state['mode']]
        publish_snapshot('pipeline:'+state['mode'],result)
        return {'report':result}

    graph.add_node('initialize',_diagnosed_node(initialize,'initialize'))
    graph.add_node('histories',_diagnosed_node(histories,'histories'))
    graph.add_node('markets',_diagnosed_node(markets,'markets'))
    graph.add_node('schedules',_diagnosed_node(schedules,'schedules'))
    graph.add_node('settlements',_diagnosed_node(settlements,'settlements'))
    graph.add_node('props',_diagnosed_node(props,'props'))
    graph.add_node('report',_diagnosed_node(report,'report'))
    graph.add_edge(START,'initialize')
    graph.add_edge('initialize','histories')
    graph.add_edge('initialize','markets')
    graph.add_edge('initialize','schedules')
    # Collect market prices before props compete for the remaining paid allowance.
    graph.add_edge(['histories','schedules'],'settlements')
    graph.add_edge(['markets','settlements'],'props')
    graph.add_edge('props','report')
    graph.add_edge('report',END)
    return graph.compile()


async def run(sports: list[str], mode: str, daily_credit_limit: int):
    if (not sports or len(sports)!=len(set(sports)) or any(s not in ('nba','nfl','cfb') for s in sports)
            or mode not in MODES or type(daily_credit_limit) is not int or daily_credit_limit<1
            or (not mode.startswith('public_') and
                (daily_credit_limit>DEFAULT_DAILY_CREDIT_LIMIT or settings.odds_rolling_credit_limit>450))
            or (mode.startswith('public_') and 'cfb' in sports)):
        raise ValueError('Invalid pipeline request')
    return (await create_daily_graph().ainvoke(dict(sports=sports,mode=mode,daily_credit_limit=daily_credit_limit)))['report']


def _write_report(path: str, report: dict) -> None:
    destination=Path(path)
    destination.parent.mkdir(parents=True,exist_ok=True)
    temporary=destination.with_name(destination.name+'.tmp')
    temporary.write_text(json.dumps(report,separators=(',',':'))+'\n',encoding='utf-8')
    temporary.replace(destination)


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--sport',choices=['nba','nfl','cfb','both','all'],default='both')
    parser.add_argument('--mode',choices=MODES,default='daily')
    parser.add_argument('--daily-credit-limit',type=int,default=DEFAULT_DAILY_CREDIT_LIMIT)
    parser.add_argument('--report-output',help='Write the final machine-readable report to this file')
    args=parser.parse_args()
    try:
        sports=['nfl','nba'] if args.sport=='both' else ['nfl','nba','cfb'] if args.sport=='all' else [args.sport]
        report=asyncio.run(run(sports,args.mode,args.daily_credit_limit))
        if args.report_output:
            with failure_stage('daily','report_write'):
                _write_report(args.report_output,report)
        print(json.dumps(report))
        # Degraded provider coverage must remain visible as a failed scheduled run.
        if report['status'] not in ('complete','observed'):
            raise SystemExit(2)
    except Exception as exc:
        raise SystemExit(f'Daily pipeline unavailable ({type(exc).__name__})') from None


if __name__=='__main__':
    main()
