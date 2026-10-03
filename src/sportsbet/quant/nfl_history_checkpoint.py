"""Retain the frozen corrected-NFL-model market audit in the private ledger."""
from __future__ import annotations

from datetime import datetime
import hashlib
import json
from pathlib import Path

from sportsbet.quant import nfl_history_edge
from sportsbet.quant.nfl_priced_checkpoint import MAX_BYTES, insert_report

PROTOCOL = nfl_history_edge.PROTOCOL
# Committed source blobs at the corrected-model protocol freeze. Normalize only
# checkout line endings; the evaluator's own raw-byte digests remain retained.
FROZEN_DIGESTS = {
    'runner': '4dabc23d293780b9c035b0afaf1d3dc9da25051da4e08520879b6df746e03c08',
    'ledger': 'e33611de7f85c376b2967f3d1f1bf4a02e80ce093d85c7a1182d29b8799fe2b1',
    'model_contract': '96cac511ca3ae555e953985167a18639ef06148947c82a00d8b6c4bc241f4f29',
    'nfl_supplement_proof': '766a499f11656bc744360c9e917fc9cdd89d253dba033c9b2db88d09c23549a2',
    'query_builder': 'f6a90477d30e6839b94b2408c379115484d88d18b9122e42461493c35e185c17',
    'backtest': '0126932e824067cfc9b108d4ff61db23fc245900e53ceece2ef43de8c3a08117',
    'priced_market_audit': '6925b66315c7daeab86f0c1cab57c02c7abda9f237f6a80242dba94d8419a5be',
    'edge_evidence': '0504ec85d6134fc8562976c0902c303cd903f10e553c60e7917ef64b6d522984',
    'market_baseline': 'bffd86272a1eac303acb57dbd0b246355b8d2d5b2ab4c39945d5e8d5c3af9404',
    'shadow_prior': 'f26b483f2679a5cdeb21e920c73e12c1af0224bc88ba49dfb2fc096f7824c596',
}


def frozen_source_digests() -> dict[str, str]:
    return {
        name: hashlib.sha256(Path(nfl_history_edge.__file__ if name == 'runner'
            else getattr(nfl_history_edge, 'ledger_module' if name == 'ledger' else name).__file__).read_bytes()
            .replace(b'\r\n', b'\n')).hexdigest()
        for name in FROZEN_DIGESTS
    }


def build_report(result: dict) -> dict:
    """Accept only the aggregate result from the existing frozen evaluator."""
    expected_keys = {'protocol', 'protocol_sha256', 'evaluator_sha256',
                     'sport', 'observed_at', 'status', 'assessment', 'cohorts',
                     'promote', 'scope'}
    if not isinstance(result, dict) or set(result) != expected_keys or result.get('protocol') != PROTOCOL:
        raise ValueError('Current NFL history audit protocol changed')
    if result.get('sport') != 'nfl' or result.get('promote') is not False:
        raise ValueError('Current NFL history audit scope changed')
    if set(result.get('cohorts', {})) != {'all_predictions', 'recommendations'}:
        raise ValueError('Both current-model cohorts are required')
    if result.get('status') != result.get('assessment', {}).get('status'):
        raise ValueError('Current NFL history audit status changed')
    expected = hashlib.sha256(json.dumps(PROTOCOL, sort_keys=True,
        separators=(',', ':')).encode()).hexdigest()
    if result.get('protocol_sha256') != expected:
        raise ValueError('Current NFL history protocol digest changed')
    if (frozen_source_digests() != FROZEN_DIGESTS
            or result.get('evaluator_sha256') != nfl_history_edge.source_digests()):
        raise ValueError('Current NFL history evaluator digest changed; new protocol required')
    observed_at = datetime.fromisoformat(result['observed_at'].replace('Z', '+00:00'))
    cutoff = datetime.fromisoformat(PROTOCOL['captured_after'])
    if observed_at.utcoffset() is None or observed_at < cutoff:
        raise ValueError('Current NFL history audit requires a prospective timestamp')
    return {**result, 'target_verified': False}


def encode_report(report: dict) -> tuple[datetime, str, str]:
    if report.get('target_verified') is not False:
        raise ValueError('Current NFL history report cannot claim a verified target')
    # Recheck source identity before allowing persistence.
    build_report({key: value for key, value in report.items() if key != 'target_verified'})
    observed_at = datetime.fromisoformat(report['observed_at'].replace('Z', '+00:00'))
    payload = json.dumps(report, sort_keys=True, separators=(',', ':'), allow_nan=False)
    encoded = payload.encode()
    if not 0 < len(encoded) <= MAX_BYTES:
        raise ValueError('Private audit report exceeds storage limit')
    return observed_at, payload, hashlib.sha256(encoded).hexdigest()


def store_report(database_url: str, report: dict) -> None:
    observed_at, payload, digest = encode_report(report)
    insert_report(database_url, PROTOCOL['version'], observed_at, payload, digest)
