"""Refresh free CFB results and publish verified forecasts without odds collection."""
from __future__ import annotations

import argparse
import asyncio
from datetime import datetime, timezone
import json

from sportsbet.dashboard import publish_snapshot
from sportsbet.diagnostics import failure_stage
from sportsbet.ledger import Ledger
from sportsbet.model_contract import model_version_for
from sportsbet.picks import build_pick_board
from sportsbet.quant.history_shadow_audit import publish_history_shadow
from sportsbet.refresh import refresh_history
from sportsbet.schedules import collect as collect_schedule
from sportsbet.settlement import pending_schedule_offsets, settle_final_props


def run(now: datetime | None = None) -> dict:
    now = now or datetime.now(timezone.utc)
    if now.tzinfo is None or now.utcoffset() is None:
        raise ValueError('An aware settlement time is required')
    with failure_stage('cfb_settlement', 'history'):
        history = refresh_history('cfb', now.date())
    if history['status'] != 'complete':
        report = dict(mode='public_cfb_settlement', sport='cfb', status='blocked',
            reason='history_refresh_unavailable', history=history, execution_ready=False,
            finished_at=datetime.now(timezone.utc).isoformat())
        with failure_stage('cfb_settlement', 'report_publish'):
            publish_snapshot('pipeline:public_cfb_settlement', report)
        return report

    with failure_stage('cfb_settlement', 'ledger'):
        ledger = Ledger()
    # Match the normal daily catch-up window and retry bounded older pending
    # dates. This fetches only ESPN schedules, never a sportsbook quote.
    with failure_stage('cfb_settlement', 'pending_offsets'):
        extra = pending_schedule_offsets(ledger, 'cfb', now)
    offsets = tuple(sorted(set(range(-7, 2)) | set(extra)))
    with failure_stage('cfb_settlement', 'schedules'):
        schedule = asyncio.run(collect_schedule('cfb', now, offsets=offsets))
    with failure_stage('cfb_settlement', 'settlement'):
        settlement = settle_final_props(ledger, 'cfb', schedule)
    with failure_stage('cfb_settlement', 'predictions'):
        predictions = ledger.predictions()
    version = model_version_for('cfb')
    with failure_stage('cfb_settlement', 'publications'):
        publish_snapshot('metrics:all:cfb', ledger.report(model_version=version, sport='cfb'))
        publish_snapshot('metrics:recommendations:cfb', ledger.report(True, model_version=version, sport='cfb'))
        publish_snapshot('picks:cfb', build_pick_board(predictions, 'cfb'))
        publish_history_shadow(predictions, 'cfb', publish_snapshot)
    # The generic settlement runner can finish successfully while final-game
    # forecasts remain ungraded because its free stat asset is still stale.
    # Surface that source lag without treating nonfinal scheduled games as errors.
    reasons = settlement.get('reasons') or {}
    final_stat_evidence_pending = sum(reasons.get(key, 0) for key in (
        'stat_not_found_or_ambiguous', 'stat_provenance_invalid'))
    complete = (schedule['status'] == 'complete' and settlement['status'] == 'complete'
                and final_stat_evidence_pending == 0)
    report = dict(mode='public_cfb_settlement', sport='cfb',
        status='complete' if complete else 'degraded',
        **({'reason': 'final_stat_evidence_unavailable'} if final_stat_evidence_pending else {}),
        final_stat_evidence_pending=final_stat_evidence_pending,
        history=history, schedule_status=schedule['status'], settlement=settlement,
        execution_ready=False, finished_at=datetime.now(timezone.utc).isoformat())
    with failure_stage('cfb_settlement', 'report_publish'):
        publish_snapshot('pipeline:public_cfb_settlement', report)
    return report


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.parse_args()
    try:
        report = run()
        print(json.dumps(report))
        if report['status'] != 'complete':
            raise SystemExit(2)
    except Exception as exc:
        raise SystemExit(f'Free CFB settlement unavailable ({type(exc).__name__})') from None


if __name__ == '__main__':
    main()
