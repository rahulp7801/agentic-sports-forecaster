"""Privately retain the existing priced NFL prospective evaluation unchanged."""
from __future__ import annotations

from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path

from sportsbet.quant import edge_evidence, priced_market_audit

PROTOCOL = {
    'version': 'nfl-priced-prospective-checkpoint-v1',
    'sport': 'nfl',
    'model_version': 'empirical-jeffreys-v4',
    'captured_after': '2026-09-23T00:34:15+00:00',
    'automatic_promotion': False,
}
MAX_BYTES = 2_000_000


def build_report(reports: dict, *, observed_at: datetime | None = None) -> dict:
    if set(reports) != {'All forecasts', 'Recommendations'}:
        raise ValueError('Both frozen priced audit cohorts are required')
    all_forecasts = reports['All forecasts']
    recommendations = reports['Recommendations']
    if any(report.get('sport') != PROTOCOL['sport']
           or report.get('model_version') != PROTOCOL['model_version']
           or report.get('captured_after') != PROTOCOL['captured_after']
           for report in (all_forecasts, recommendations)):
        raise ValueError('Priced audit source identity changed')
    assessment = edge_evidence.assess_prospective_edge(all_forecasts, recommendations)
    observed_at = observed_at or datetime.now(timezone.utc)
    if observed_at.utcoffset() is None:
        raise ValueError('Audit timestamp requires a timezone')
    return {
        'protocol': dict(PROTOCOL),
        'observed_at': observed_at.isoformat(),
        'assessment': assessment,
        'cohorts': {
            'all_forecasts': all_forecasts['prospective'],
            'recommendations': recommendations['prospective'],
        },
        'evaluator_sha256': {
            module.__name__: hashlib.sha256(Path(module.__file__).read_bytes()).hexdigest()
            for module in (priced_market_audit, edge_evidence)
        },
        'promote': False,
        'target_verified': False,
        'scope': 'Recorded pregame hypothetical prices and authenticated outcomes; no bets executed.',
    }


def encode_report(report: dict) -> tuple[datetime, str, str]:
    if (report.get('protocol') != PROTOCOL or report.get('promote') is not False
            or report.get('target_verified') is not False):
        raise ValueError('Priced edge retention contract changed')
    observed_at = datetime.fromisoformat(report['observed_at'].replace('Z', '+00:00'))
    if observed_at.utcoffset() is None:
        raise ValueError('Audit timestamp requires a timezone')
    payload = json.dumps(report, sort_keys=True, separators=(',', ':'), allow_nan=False)
    if not 0 < len(payload.encode()) <= MAX_BYTES:
        raise ValueError('Private audit report exceeds storage limit')
    return observed_at, payload, hashlib.sha256(payload.encode()).hexdigest()


def insert_report(database_url: str, protocol: str, observed_at: datetime,
                  payload: str, digest: str) -> None:
    import psycopg

    if protocol not in (PROTOCOL['version'], 'nfl-history-priced-prospective-v1'):
        raise ValueError('Unsupported private prospective audit protocol')
    with psycopg.connect(database_url.replace('postgresql+psycopg://', 'postgresql://', 1),
                         connect_timeout=15) as conn:
        if conn.execute('SELECT current_user').fetchone()[0] != 'sportsbet_worker':
            raise PermissionError('Prospective audit requires the restricted worker role')
        conn.execute('''INSERT INTO analytics.prospective_audit_reports
            (protocol,observed_at,payload,payload_sha256) VALUES (%s,%s,%s,%s)''',
            (protocol, observed_at, payload, digest))


def store_report(database_url: str, report: dict) -> None:
    observed_at, payload, digest = encode_report(report)
    insert_report(database_url, PROTOCOL['version'], observed_at, payload, digest)
