"""Private, append-only pregame receipts for the frozen cross-book experiment."""
from __future__ import annotations
import asyncio
from collections import Counter,defaultdict
from datetime import datetime,timedelta,timezone
import hashlib
import json
from pathlib import Path
from statistics import mean

from sportsbet.ledger import utc_timestamp
from sportsbet.quant import cross_book_forward as forward,market_challengers as candidate
from sportsbet.quant.audit_storage import ReadOnlyLedger,audit_database_url

VERSION='cross-book-paper-v1'
# Settlement fields change legitimately; bulky explanations are not selector inputs.
OMIT={'outcome','outcome_source','outcome_ref','outcome_observed_at','actual_value','outcome_evidence',
      'history_shadow','role_history_shadow','role_history_shadow_recorded_at',
      'availability','trade_plan','next_gen_stats'}
MAX_BYTES=2_000_000


def encode(value):
    return json.dumps(value,sort_keys=True,separators=(',',':'),allow_nan=False)


def clean(row):
    return {k:v for k,v in row.items() if k not in OMIT and not k.startswith(('history_shadow','role_history_shadow'))}


def digest(value):
    return hashlib.sha256(encode(value).encode()).hexdigest()


def implementation():
    return {name:hashlib.sha256(Path(module.__file__).read_text(encoding='utf-8').encode()).hexdigest()
        for name,module in [('forward',forward),('paper',__import__(__name__,fromlist=['']))]}


def prepare(rows,sport,now):
    if now<utc_timestamp(forward.PROTOCOL['captured_after']):
        return []
    rows=[clean(row) for row in rows]
    report=forward.evaluate(rows,sport,now=now)
    observed,_=candidate.observations(rows,sport,forward.PROTOCOL['model_versions'][sport])
    by_id={x['row']['prediction_id']:x for x in observed};result=[]
    for selected in report['selections']:
        needed=[selected['prediction_id'],*selected['reference_prediction_ids']]
        sources=[by_id[key] for key in needed]
        deadline=min(min(x['start'],x['quote']+timedelta(seconds=candidate.PROTOCOL['quote_max_age_seconds'])) for x in sources)
        decision=utc_timestamp(selected['decision_at'])
        if not decision<=now<deadline:
            continue
        offer=by_id[selected['prediction_id']]
        selected={k:v for k,v in selected.items() if k!='verified_outcome'}
        selected['offered_market_probability']=offer['q'] if selected['direction']=='over' else 1-offer['q']
        evidence=sorted((r for r in rows if (r['game_id'],r['player_id'])==
            (selected['game_id'],selected['player_id'])),key=lambda r:r['prediction_id'])
        body=dict(version=VERSION,sport=sport,selection=selected,evidence=evidence,
            forward_protocol_sha256=report['protocol_sha256'],evaluator_sha256=report['evaluator_sha256'],
            implementation=implementation())
        payload=encode(body)
        if len(payload.encode())>MAX_BYTES:
            raise ValueError('Paper evidence exceeds the bounded payload size')
        result.append(dict(protocol=VERSION,sport=sport,game_id=selected['game_id'],
            player_id=selected['player_id'],prediction_id=selected['prediction_id'],
            decision_at=decision,valid_until=deadline,payload=payload,
            payload_sha256=hashlib.sha256(payload.encode()).hexdigest()))
    return result


INSERT_SQL='''INSERT INTO analytics.paper_selections
    (protocol,sport,game_id,player_id,prediction_id,decision_at,valid_until,payload,payload_sha256)
    SELECT $1,$2,$3,$4,$5,$6,$7,$8,$9 WHERE clock_timestamp() >= $6 AND clock_timestamp() < $7
    ON CONFLICT (protocol,sport,game_id,player_id) DO NOTHING RETURNING prediction_id'''


async def record(pool,rows,sport):
    """Called after forecasts are committed. No providers, exposure or public output."""
    import structlog
    try:
        records=prepare(rows,sport,datetime.now(timezone.utc))
        if not records:
            return
        async with asyncio.timeout(3):
            async with pool.acquire() as conn:
                async with conn.transaction():
                    await conn.execute("SET LOCAL statement_timeout='2s'")
                    for row in records:
                        await conn.fetchval(INSERT_SQL,*[row[key] for key in (
                            'protocol','sport','game_id','player_id','prediction_id',
                            'decision_at','valid_until','payload','payload_sha256')])
    except Exception as exc:
        # Research failures cannot suppress public forecasts; never log private results.
        structlog.get_logger().warning('paper_receipt_unavailable',error_type=type(exc).__name__)


class PaperLedger(ReadOnlyLedger):
    ids=()
    def _prediction_records(self,*,ordered=False):
        rows=[]
        with self.connect() as db:
            for offset in range(0,len(self.ids),250):
                rows.extend(db.execute('''SELECT id,payload,outcome,outcome_source,outcome_ref,
                    outcome_observed_at,actual_value,outcome_evidence FROM predictions
                    WHERE id=ANY(?) ORDER BY id''',(list(self.ids[offset:offset+250]),)).fetchall())
        return rows


def audit_receipts(receipts,predictions,sport,now):
    by_id={r['prediction_id']:r for r in predictions};scores=[];returns=defaultdict(list)
    errors=Counter();pending=valid=0;seen=set()
    for receipt in receipts:
        if receipt['sport']!=sport or receipt['protocol']!=VERSION:
            continue
        try:
            identity=(receipt['protocol'],sport,receipt['game_id'],receipt['player_id'])
            if identity in seen:raise ValueError('duplicate_receipt')
            seen.add(identity)
            recorded=utc_timestamp(str(receipt['recorded_at']))
            if recorded>now or hashlib.sha256(receipt['payload'].encode()).hexdigest()!=receipt['payload_sha256']:
                raise ValueError('receipt_hash_or_clock')
            body=json.loads(receipt['payload'])
            if body['implementation']!=implementation():raise ValueError('changed_paper_implementation')
            evidence=body['evidence']
            if any(r['prediction_id'] not in by_id or digest(r)!=digest(clean(by_id[r['prediction_id']])) for r in evidence):
                raise ValueError('changed_or_missing_forecast')
            matches=[r for r in prepare(evidence,sport,recorded) if r['prediction_id']==receipt['prediction_id']]
            if len(matches)!=1 or matches[0]['payload_sha256']!=receipt['payload_sha256']:
                raise ValueError('selection_not_reproducible')
            expected=matches[0]
            if any(str(expected[k])!=str(receipt[k]) for k in ('protocol','sport','game_id','player_id','prediction_id')):
                raise ValueError('receipt_identity')
            if utc_timestamp(str(receipt['valid_until']))!=expected['valid_until'] or utc_timestamp(str(receipt['decision_at']))!=expected['decision_at']:
                raise ValueError('receipt_deadline')
            valid+=1
            row=by_id[receipt['prediction_id']];outcome=candidate.audit._verified_outcome(row)
            if type(outcome) is not bool or utc_timestamp(row['outcome_observed_at'])>now:
                pending+=1;continue
            s=body['selection'];odds=s['american_odds']
            profit=odds/100 if odds>0 else 100/-odds
            returns[s['game_id']].append(profit if outcome else -1.)
            scores.append(dict(unit=(s['game_id'],s['player_id'],s['prop_type'],s['line']),
                y=int(outcome),p=s['reference_probability'],q=s['offered_market_probability']))
        except (KeyError,ValueError,TypeError,ArithmeticError) as exc:
            errors[type(exc).__name__]+=1
    values=[v for group in returns.values() for v in group]
    scored=candidate.score(scores,lambda r:r['p']);interval=candidate.cluster_interval(returns)
    adequate=(len(values)>=forward.PROTOCOL['minimum_decided_selections'] and
        len(returns)>=max(forward.PROTOCOL['minimum_paired_games'],forward.PROTOCOL['minimum_selection_games']))
    supported=bool(adequate and not errors and interval and interval[0]>0 and scored['game_cluster_95'][1]<0)
    return dict(version=VERSION,sport=sport,observed_at=now.isoformat(),valid_receipts=valid,
        invalid_receipts=sum(errors.values()),errors=dict(errors),pending=pending,decided=len(values),
        settled_games=len(returns),wins=sum(v>0 for v in values),flat_stake_roi=mean(values) if values else None,
        roi_game_cluster_95=interval,probability_scores=scored,promote=False,
        status='invalid_evidence' if errors else 'awaiting_start' if now<utc_timestamp(forward.PROTOCOL['captured_after']) else 'review_required' if supported else
            'insufficient_evidence' if not adequate else 'edge_not_demonstrated',
        scope='Private timestamped paper selections; hypothetical returns, no bets or production recommendations.')


def main():
    import argparse
    from dotenv import load_dotenv
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args();load_dotenv()
    ledger=PaperLedger(database_url=audit_database_url())
    with ledger.snapshot():
        with ledger.connect() as db:
            raw=db.execute('''SELECT protocol,sport,game_id,player_id,prediction_id,decision_at,
                valid_until,recorded_at,payload,payload_sha256 FROM paper_selections WHERE protocol=?''',(VERSION,)).fetchall()
        keys=('protocol','sport','game_id','player_id','prediction_id','decision_at','valid_until','recorded_at','payload','payload_sha256')
        receipts=[dict(zip(keys,r,strict=True)) for r in raw]
        ledger.ids=sorted({row['prediction_id'] for r in receipts for row in json.loads(r['payload'])['evidence']})
        predictions=ledger.predictions()
    now=datetime.now(timezone.utc)
    reports={s:audit_receipts(receipts,predictions,s,now) for s in forward.PROTOCOL['model_versions']}
    args.output.parent.mkdir(parents=True,exist_ok=True)
    args.output.write_text(json.dumps(reports,indent=2,allow_nan=False),encoding='utf-8')
    print('Private paper audit completed')


if __name__=='__main__':main()
