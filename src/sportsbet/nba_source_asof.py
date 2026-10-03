"""Forward-only NBA source-time contract outside byte-pinned v4 evaluators.

The original model_contract and Ledger source files stay unchanged so their
precommitted prospective audits continue to verify the original population.
"""
from __future__ import annotations

from datetime import datetime, timezone

from sportsbet.ledger import (Ledger, json_object, quote_evidence_valid as
    legacy_quote_evidence_valid, settlement_identity_valid, utc_timestamp)
from sportsbet.model_contract import (MODEL_VERSION, forecast_version_valid as
    legacy_forecast_version_valid, history_policy_for as legacy_history_policy_for,
    model_version_for as legacy_model_version_for)


NBA_MODEL_VERSION = 'empirical-jeffreys-v4-nba-source-asof-v1'
NBA_HISTORY_POLICY = 'nba-source-asof-v1'
NBA_HISTORY_FROZEN_AT = '2026-10-04T03:00:00+00:00'
_FREEZE = datetime.fromisoformat(NBA_HISTORY_FROZEN_AT)


def model_version_for(sport: str, observed_at: datetime | None = None) -> str:
    if sport == 'nba':
        if (observed_at or datetime.now(timezone.utc)) < _FREEZE:
            return MODEL_VERSION
        return NBA_MODEL_VERSION
    return legacy_model_version_for(sport, observed_at)


def history_policy_for(sport: str) -> str | None:
    return NBA_HISTORY_POLICY if sport == 'nba' else legacy_history_policy_for(sport)


def forecast_version_valid(payload: dict, captured: datetime) -> bool:
    if payload.get('model_version') != NBA_MODEL_VERSION:
        return legacy_forecast_version_valid(payload, captured)
    if payload.get('sport') != 'nba' or payload.get('history_policy_version') != NBA_HISTORY_POLICY:
        return False
    try:
        cutoff = utc_timestamp(payload['history_observed_before'])
        generated = utc_timestamp(payload['model_generated_at'])
        captured = utc_timestamp(captured.isoformat())
        return _FREEZE <= cutoff <= generated <= captured
    except (ArithmeticError, AttributeError, KeyError, TypeError, ValueError):
        return False


def quote_evidence_valid(payload: dict) -> bool:
    """Authenticate new NBA time/quote evidence using the unchanged v4 quote parser."""
    if payload.get('model_version') != NBA_MODEL_VERSION:
        return legacy_quote_evidence_valid(payload)
    try:
        captured = utc_timestamp(payload['captured_at'])
        quoted = utc_timestamp(payload['quote_time'])
        started = utc_timestamp(payload['game_start_time'])
        cutoff = utc_timestamp(payload['history_observed_before'])
        if (not forecast_version_valid(payload, captured)
                or not quoted <= cutoff <= captured < started):
            return False
        return (legacy_quote_evidence_valid(payload | {'model_version': MODEL_VERSION})
                and settlement_identity_valid(payload))
    except (ArithmeticError, AttributeError, KeyError, TypeError, ValueError):
        return False


class ReleaseLedger(Ledger):
    """Require the new NBA quote proof on write and every consumer/report read."""

    def _prepare_record(self, scan_id: str, payload: dict):
        if payload.get('model_version') == NBA_MODEL_VERSION and not quote_evidence_valid(payload):
            raise ValueError('NBA source-time prediction requires verified quote evidence')
        return super()._prepare_record(scan_id, payload)

    def _prediction_records(self, *, ordered: bool = False):
        records = super()._prediction_records(ordered=ordered)
        guarded = []
        for record in records:
            payload = json_object(record[1])
            if (payload and payload.get('model_version') == NBA_MODEL_VERSION
                    and not quote_evidence_valid(payload)):
                # Base reports count this as excluded metadata; public predictions
                # omit it. Never reinterpret an invalid new version as legacy v4.
                guarded.append((record[0], 'null', *record[2:]))
            else:
                guarded.append(record)
        return guarded
