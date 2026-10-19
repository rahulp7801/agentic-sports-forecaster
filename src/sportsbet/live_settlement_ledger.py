"""Explicit live settlement reader/writer outside the frozen research Ledger.

Legacy evaluators retain their original Ledger and v1/v2 evidence interpretation.
This runtime keeps the release's NBA source-time admission checks and opts only
exact Utah v3 settlements into separately identified live reports.
"""
from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal
import hashlib
import json
import re

from sportsbet.graph.models import QuantResult
from sportsbet.ledger import (
    MAX_RECOMMENDATION_FRACTION, QUOTE_PROVENANCE_MODEL_VERSIONS,
    SETTLEMENT_REF, STAT_COLUMNS, VERIFIED_SETTLEMENT_SOURCE, json_object,
    normalized_model_version, quote_evidence_valid, settlement_identity_valid,
    utc_timestamp, validated_selection,
    verified_settlement_evidence as legacy_verified_settlement_evidence,
)
from sportsbet.nba_source_asof import ReleaseLedger
from sportsbet.ingestion.provenance import stat_row_sha256
from sportsbet.quant.backtest import BacktestEngine, BacktestSignal
from sportsbet.schedules import scheduled_stat_teams


VERSION='live-settlement-v3'


def verified_settlement_evidence(payload: dict, outcome, source, source_ref,
                                 observed_at, actual_value, evidence) -> bool:
    """Verify v3 directly; retain the unchanged legacy verifier for v1/v2."""
    proof=json_object(evidence)
    if not isinstance(proof,dict) or proof.get('schedule_identity_version',1) in (1,2):
        return legacy_verified_settlement_evidence(payload,outcome,source,source_ref,
            observed_at,actual_value,evidence)
    try:
        version=proof.get('schedule_identity_version')
        if type(version) is not int or version!=3 or payload['sport']!='nba':
            return False
        match=SETTLEMENT_REF.fullmatch(source_ref or '')
        if source!=VERIFIED_SETTLEMENT_SOURCE or not match:
            return False
        canonical=json.dumps(proof,sort_keys=True,separators=(',',':'),allow_nan=False)
        if hashlib.sha256(canonical.encode()).hexdigest()!=match.group(3):
            return False
        column=STAT_COLUMNS['nba'][payload['prop_type']]
        row=proof['stat_row']
        if (proof['stat_provider'] not in ('nba','espn')
                or match.group(1)!=proof['stat_provider']
                or match.group(2)!=proof['provider_event_id']
                or proof.get('completed') is not True or proof.get('date')!=payload['game_date']
                or proof.get('home_name')!=payload['home_team']
                or proof.get('away_name')!=payload['away_team']
                or str(proof.get('player_id'))!=str(payload['player_id'])
                or proof.get('prop_type')!=payload['prop_type'] or not isinstance(row,dict)
                or not re.fullmatch('[0-9a-f]{64}',proof.get('stat_source_sha256',''))
                or not re.fullmatch('[0-9a-f]{64}',proof.get('stat_record_sha256',''))):
            return False
        player_id=str(payload['player_id'])
        if (not re.fullmatch('[1-9][0-9]*',player_id)
                or type(row.get('player_id')) is not int or row['player_id']<=0
                or str(row['player_id'])!=player_id
                or row.get('game_date')!=payload['game_date']):
            return False
        if row.get('team_abbreviation') not in scheduled_stat_teams('nba',proof,identity_version=3):
            return False
        if stat_row_sha256('nba',row)!=proof['stat_record_sha256']:
            return False
        actual=Decimal(str(actual_value))
        if (not actual.is_finite() or actual!=Decimal(str(proof['actual_value']))
                or actual!=Decimal(str(row[column]))):
            return False
        line=Decimal(str(payload['line']))
        expected='push' if actual==line else ((actual>line)==(payload['direction']=='over'))
        if outcome!=expected:
            return False
        game_time=utc_timestamp(proof['game_time'])
        stat_time=utc_timestamp(proof['stat_observed_at'])
        settlement_time=observed_at if isinstance(observed_at,datetime) else utc_timestamp(observed_at)
        return game_time<=stat_time<=settlement_time.astimezone(timezone.utc)
    except (ArithmeticError,KeyError,TypeError,ValueError):
        return False


class Ledger(ReleaseLedger):
    """Current runtime ledger; record/budget/source-time admission stays inherited."""

    settlement_evidence_protocol=VERSION

    def settle(self, outcomes: dict, *, source: str = 'manual', source_ref: str = 'caller_supplied',
               observed_at: datetime | None = None, actual_values: dict | None = None,
               evidence: dict | None = None) -> None:
        proofs=[(evidence or {}).get(key) for key in outcomes]
        if not any(isinstance(proof,dict) and proof.get('schedule_identity_version')==3
                   for proof in proofs):
            return super().settle(outcomes,source=source,source_ref=source_ref,
                observed_at=observed_at,actual_values=actual_values,evidence=evidence)
        if (source!=VERIFIED_SETTLEMENT_SOURCE
                or any(not isinstance(proof,dict)
                    or type(proof.get('schedule_identity_version')) is not int
                    or proof['schedule_identity_version']!=3 for proof in proofs)):
            raise ValueError('Version3 settlements require one verified version3 batch')
        if not isinstance(source_ref,str) or not source_ref.strip() or len(source_ref)>200:
            raise ValueError('Settlement provenance is invalid')
        stamp=observed_at or datetime.now(timezone.utc)
        if stamp.tzinfo is None or stamp.utcoffset() is None:
            raise ValueError('Settlement observation time requires a timezone')
        stamp=stamp.astimezone(timezone.utc)
        items=list(outcomes.items())
        with self.connect() as db:
            for offset in range(0,len(items),250):
                batch=items[offset:offset+250]
                keys=[key for key,_ in batch]
                placeholders=','.join('?' for _ in keys)
                query=f'SELECT id,payload FROM predictions WHERE id IN ({placeholders})'
                rows=dict(db.execute(query,keys).fetchall())
                guarded=[]
                for key,outcome in batch:
                    if outcome is not None and type(outcome) is not bool and outcome not in ('push','void'):
                        raise ValueError('Settlement must be true/false/push/void/null')
                    actual=(actual_values or {}).get(key)
                    if actual is not None:
                        actual=Decimal(str(actual))
                        if not actual.is_finite():
                            raise ValueError('Settlement actual value is invalid')
                        actual=int(actual) if actual==actual.to_integral_value() else str(actual)
                    payload=rows.get(key)
                    if payload is None:
                        raise ValueError(f'Unknown prediction ID: {key}')
                    proof=(evidence or {}).get(key)
                    encoded=json.dumps(proof,sort_keys=True,separators=(',',':'),allow_nan=False)
                    if not verified_settlement_evidence(json.loads(payload),outcome,source,
                            source_ref,stamp,actual,encoded):
                        raise ValueError('Verified settlement evidence is invalid')
                    # Decoded None values and an earlier read cannot grant a write.
                    prior=db.execute('''SELECT outcome,outcome_source,outcome_ref,
                        outcome_observed_at,actual_value,outcome_evidence
                        FROM predictions WHERE id=?''',(key,)).fetchone()
                    if prior is None:
                        raise ValueError('Utah settlement prior state is unavailable')
                    if all(value is None for value in prior):
                        condition='''outcome IS NULL AND outcome_source IS NULL
                            AND outcome_ref IS NULL AND outcome_observed_at IS NULL
                            AND actual_value IS NULL AND outcome_evidence IS NULL'''
                        expected=()
                    else:
                        previous=json_object(prior[5])
                        if (any(value is None for value in prior) or not isinstance(previous,dict)
                                or type(previous.get('schedule_identity_version')) is not int
                                or previous['schedule_identity_version']!=3
                                or not verified_settlement_evidence(json.loads(payload),
                                    json.loads(prior[0]),prior[1],prior[2],prior[3],prior[4],previous)):
                            raise ValueError('Utah settlement cannot replace retained evidence')
                        condition='''outcome=? AND outcome_source=? AND outcome_ref=?
                            AND outcome_observed_at=? AND actual_value=? AND outcome_evidence=?'''
                        expected=tuple(prior)
                    update=(json.dumps(outcome),source,source_ref,stamp.isoformat(),actual,encoded,key)
                    guarded.append((update,condition,expected))
                for update,condition,expected in guarded:
                    cursor=db.execute('''UPDATE predictions SET outcome=?,outcome_source=?,outcome_ref=?,
                        outcome_observed_at=?,actual_value=?,outcome_evidence=? WHERE id=? AND '''+condition,
                        (*update,*expected))
                    if cursor.rowcount!=1:
                        raise ValueError('Utah settlement prior state changed')

    def report(self, recommendations_only: bool = False, model_version: str | None = None,
               sport: str | None = None, captured_after: str | None = None) -> dict:
        from dataclasses import fields
        from sportsbet.arbitrage.ev import quote_terms
        if sport is not None and sport not in STAT_COLUMNS:
            raise ValueError('Evaluation sport is invalid')
        cutoff = utc_timestamp(captured_after) if captured_after is not None else None
        records = self._prediction_records()
        signals = []
        excluded = 0
        duplicate = 0
        invalid_closing = 0
        seen = set()
        parsed = []
        versions = set()
        unverified_settlements=0
        for prediction_id, raw, outcome, outcome_source, outcome_ref, outcome_observed, actual, proof in records:
            p = json_object(raw)
            if p is None:
                excluded += 1
                continue
            if sport is not None and p.get('sport') != sport:
                continue
            try:
                version=normalized_model_version(p)
            except ValueError:
                excluded += 1
                continue
            versions.add(version)
            if model_version is not None and version != model_version:
                continue
            if recommendations_only and p.get('accepted') is not True:
                continue
            decoded_outcome=None
            if outcome is not None:
                try:
                    decoded_outcome=json.loads(outcome)
                except (TypeError,ValueError):
                    unverified_settlements+=1
                else:
                    if not verified_settlement_evidence(
                            p,decoded_outcome,outcome_source,outcome_ref,outcome_observed,actual,proof):
                        decoded_outcome=None
                        unverified_settlements+=1
            # Without recorded actual tipoff/entry, no trustworthy historical evaluation.
            if not p.get('game_start_time') or not p.get('captured_at') or p.get('model_probability') is None:
                excluded += 1
                continue
            try:
                if (version in QUOTE_PROVENANCE_MODEL_VERSIONS
                        and not quote_evidence_valid(p)):
                    raise ValueError('Model quote evidence required')
                if (version in QUOTE_PROVENANCE_MODEL_VERSIONS
                        and not settlement_identity_valid(p)):
                    raise ValueError('Model settlement identity required')
                start = utc_timestamp(p['game_start_time'])
                entered = utc_timestamp(p['captured_at'])
                quote_time = utc_timestamp(p.get('quote_time') or p['captured_at'])
                generated = utc_timestamp(p.get('model_generated_at') or p['captured_at'])
                probability = Decimal(str(p['model_probability']))
                push = Decimal(str(p.get('push_probability',0)))
                stake = Decimal(str(p.get('stake_fraction',0))) if recommendations_only else Decimal(1)
                selection=validated_selection(p)[:5]
                if (not stake.is_finite() or stake < 0
                        or (recommendations_only
                            and not 0 < stake <= MAX_RECOMMENDATION_FRACTION)):
                    raise ValueError('Invalid recorded stake')
                if not probability.is_finite() or not push.is_finite() or not 0 <= probability <= 1 or not 0 <= push <= 1-probability:
                    raise ValueError('Invalid model probabilities')
                if type(p.get('american_odds')) is not int or abs(p['american_odds']) < 100:
                    raise ValueError('Actual American price required')
                quote_terms(p['american_odds'],Decimal(0))
            except (ValueError, TypeError, KeyError, ArithmeticError):
                excluded += 1
                continue
            if entered >= start or quote_time > entered or generated > entered or p.get('synthetic_price') or str(p.get('sportsbook','')).lower()=='prizepicks':
                excluded += 1
                continue
            if cutoff is not None and entered < cutoff:
                continue
            parsed.append((entered,prediction_id,start,p,decoded_outcome,selection))
        # UTC chronology, not lexical ISO strings with different offsets.
        parsed.sort(key=lambda row: (row[0], row[1]))
        closing_quotes={}
        identities=sorted({self.quote_identity(row[3]) for row in parsed})
        if identities:
            with self.connect() as db:
                for offset in range(0,len(identities),250):
                    batch=identities[offset:offset+250]
                    placeholders=','.join('?' for _ in batch)
                    # The only interpolated text is one literal '?' per bounded batch item;
                    # quote identities remain bound values.
                    query=f'SELECT identity,captured_at,probability FROM quotes WHERE identity IN ({placeholders}) ORDER BY captured_at DESC'
                    rows=db.execute(query,batch).fetchall()
                    for identity,captured,probability in rows:
                        closing_quotes.setdefault(identity,[]).append((captured,probability))
        for entered,_,start,p,outcome,selection in parsed:
            if selection in seen:
                duplicate += 1
                continue
            seen.add(selection)
            close = None
            closing_time = entered
            closing=None
            entered_text=entered.astimezone(timezone.utc).isoformat()
            start_text=start.astimezone(timezone.utc).isoformat()
            for candidate in closing_quotes.get(self.quote_identity(p),()):
                # Preserve the legacy TEXT-column range and newest-row behavior;
                # timestamp validation below still rejects malformed retained rows.
                if isinstance(candidate[0],str) and entered_text < candidate[0] < start_text:
                    closing=candidate
                    break
            if closing:
                try:
                    closing_time = utc_timestamp(closing[0])
                    close = Decimal(str(closing[1]))
                    if not close.is_finite() or not 0 <= close <= 1 or not entered < closing_time < start:
                        raise ValueError('Invalid closing quote')
                except (ValueError, TypeError, ArithmeticError):
                    close, closing_time = None, entered
                    invalid_closing += 1
            signals.append(BacktestSignal(
                QuantResult(true_probability=Decimal(str(p['model_probability']))),
                close,
                outcome,
                Decimal(str(p.get('stake_fraction',0))) if recommendations_only else Decimal('1'),
                quote_terms(p['american_odds'],Decimal(0))[1]+1, start,
                closing_time, entered,
                push_probability=Decimal(str(p.get('push_probability',0))),
                game_cluster_id=p['game_id'],
            ))
        report = BacktestEngine().run(signals)
        return {'settlement_evidence_protocol':VERSION,
                **{f.name:getattr(report,f.name) for f in fields(report) if f.name!='signals_df'},
                'excluded_missing_metadata':excluded, 'duplicate_predictions':duplicate,
                'excluded_closing_quotes':invalid_closing,
                'cohort':'recommendations' if recommendations_only else 'all_predictions',
                'sport':sport or 'all',
                'model_version':model_version, 'available_model_versions':sorted(versions),
                'unverified_settlements':unverified_settlements,
                'selection_policy':'Earliest eligible prediction per game/player/market/side/line within the selected cohort.',
                'profit_scope':'Hypothetical recorded-stake replay, not executed bets or realized account profit.',
                **({'captured_after':cutoff.isoformat()} if cutoff is not None else {})}
