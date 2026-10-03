"""Privately retain pinned NBA and corrected-CFB prospective priced audits."""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path

from sportsbet.quant import cfb_history_edge, multisport_edge
from sportsbet.quant.audit_storage import audit_database_url
from sportsbet.quant.nfl_priced_checkpoint import MAX_BYTES, insert_report

EVALUATORS = {'nba': multisport_edge, 'cfb': cfb_history_edge}
FROZEN_DIGESTS = {
    'nba': {
        'runner': '0e590138b3a560ca5f7b5d8c9068c0b3fc81f969490ea23a3b068edc34791929',
        'ledger': 'e33611de7f85c376b2967f3d1f1bf4a02e80ce093d85c7a1182d29b8799fe2b1',
        'backtest': '0126932e824067cfc9b108d4ff61db23fc245900e53ceece2ef43de8c3a08117',
        'priced_market_audit': '6925b66315c7daeab86f0c1cab57c02c7abda9f237f6a80242dba94d8419a5be',
        'edge_evidence': '0504ec85d6134fc8562976c0902c303cd903f10e553c60e7917ef64b6d522984',
        'market_baseline': 'bffd86272a1eac303acb57dbd0b246355b8d2d5b2ab4c39945d5e8d5c3af9404',
        'shadow_prior': 'f26b483f2679a5cdeb21e920c73e12c1af0224bc88ba49dfb2fc096f7824c596',
    },
    'cfb': {
        'runner': '5dbfd0063f3f75f75f9b339270ae113c9db68d8f0172a8d77b718563c455fadf',
        'ledger': 'e33611de7f85c376b2967f3d1f1bf4a02e80ce093d85c7a1182d29b8799fe2b1',
        'model_contract': '96cac511ca3ae555e953985167a18639ef06148947c82a00d8b6c4bc241f4f29',
        'cfb_supplement_proof': '512d728d3f9280bab2469501c1b553247df15fadfd318ab65a09e8b55033d4ce',
        'query_builder': 'f6a90477d30e6839b94b2408c379115484d88d18b9122e42461493c35e185c17',
        'backtest': '0126932e824067cfc9b108d4ff61db23fc245900e53ceece2ef43de8c3a08117',
        'priced_market_audit': '6925b66315c7daeab86f0c1cab57c02c7abda9f237f6a80242dba94d8419a5be',
        'edge_evidence': '0504ec85d6134fc8562976c0902c303cd903f10e553c60e7917ef64b6d522984',
        'market_baseline': 'bffd86272a1eac303acb57dbd0b246355b8d2d5b2ab4c39945d5e8d5c3af9404',
        'shadow_prior': 'f26b483f2679a5cdeb21e920c73e12c1af0224bc88ba49dfb2fc096f7824c596',
    },
}
EXPECTED_KEYS = {'protocol', 'protocol_sha256', 'evaluator_sha256', 'sport',
                 'observed_at', 'status', 'assessment', 'cohorts', 'promote', 'scope'}
PRIVATE_ROW_KEYS = frozenset({'player', 'player_id', 'player_name', 'prediction_id',
                              'game_id', 'raw_predictions', 'raw_quotes', 'quote_source'})


def aggregate_only(value, depth: int = 0) -> None:
    """Reject row-shaped or oversized nested payloads before private persistence."""
    if depth > 8:
        raise ValueError('Prospective audit nesting exceeds limit')
    if isinstance(value, dict):
        if len(value) > 100 or any(not isinstance(key, str) or key in PRIVATE_ROW_KEYS
                                   for key in value):
            raise ValueError('Prospective audit contains row-level fields')
        for item in value.values():
            aggregate_only(item, depth + 1)
    elif isinstance(value, list):
        if len(value) > 100 or any(isinstance(item, (dict, list)) for item in value):
            raise ValueError('Prospective audit contains row-level arrays')
        for item in value:
            aggregate_only(item, depth + 1)
    elif value is None or type(value) in (bool, int, float):
        return
    elif isinstance(value, str) and len(value) <= 300:
        return
    else:
        raise ValueError('Prospective audit contains unsupported data')


def frozen_source_digests(sport: str) -> dict[str, str]:
    evaluator = EVALUATORS[sport]
    return {
        name: hashlib.sha256(Path(evaluator.__file__ if name == 'runner'
            else getattr(evaluator, 'ledger_module' if name == 'ledger' else name).__file__)
            .read_bytes().replace(b'\r\n', b'\n')).hexdigest()
        for name in FROZEN_DIGESTS[sport]
    }


def build_report(result: dict, sport: str) -> dict:
    """Accept only the aggregate result from the pinned sport evaluator."""
    if sport not in EVALUATORS or not isinstance(result, dict) or set(result) != EXPECTED_KEYS:
        raise ValueError('Unsupported private prospective audit result')
    evaluator = EVALUATORS[sport]
    protocol = evaluator.PROTOCOL
    if (result.get('protocol') != protocol or result.get('sport') != sport
            or result.get('promote') is not False
            or set(result.get('cohorts', {})) != {'all_predictions', 'recommendations'}
            or result.get('status') != result.get('assessment', {}).get('status')):
        raise ValueError('Private prospective audit scope changed')
    expected_hash = hashlib.sha256(json.dumps(protocol, sort_keys=True,
        separators=(',', ':')).encode()).hexdigest()
    if result.get('protocol_sha256') != expected_hash:
        raise ValueError('Private prospective protocol digest changed')
    if (frozen_source_digests(sport) != FROZEN_DIGESTS[sport]
            or result.get('evaluator_sha256') != evaluator.source_digests()):
        raise ValueError('Prospective evaluator changed; new protocol required')
    try:
        observed = datetime.fromisoformat(result['observed_at'].replace('Z', '+00:00'))
    except (TypeError, ValueError, KeyError) as exc:
        raise ValueError('Invalid prospective audit time') from exc
    if observed.utcoffset() is None or observed < datetime.fromisoformat(protocol['captured_after']):
        raise ValueError('Prospective audit requires a later aware timestamp')
    aggregate_only(result)
    return {**result, 'target_verified': False}


def encode_report(report: dict, sport: str) -> tuple[datetime, str, str]:
    if report.get('target_verified') is not False:
        raise ValueError('Private prospective report cannot claim a verified target')
    build_report({key: value for key, value in report.items() if key != 'target_verified'}, sport)
    observed = datetime.fromisoformat(report['observed_at'].replace('Z', '+00:00'))
    payload = json.dumps(report, sort_keys=True, separators=(',', ':'), allow_nan=False)
    encoded = payload.encode()
    if not 0 < len(encoded) <= MAX_BYTES:
        raise ValueError('Private prospective report exceeds storage limit')
    return observed, payload, hashlib.sha256(encoded).hexdigest()


def store_report(database_url: str, report: dict, sport: str) -> None:
    observed, payload, digest = encode_report(report, sport)
    insert_report(database_url, EVALUATORS[sport].PROTOCOL['version'], observed, payload, digest)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--sport', choices=['nba', 'cfb', 'all'], default='all')
    args = parser.parse_args()
    sports = list(EVALUATORS) if args.sport == 'all' else [args.sport]
    try:
        url = audit_database_url()
    except Exception as exc:
        raise SystemExit(f'Private NBA/CFB audit source unavailable: {type(exc).__name__}') from None
    failures = []
    for sport in sports:
        try:
            evaluator = EVALUATORS[sport]
            ledger = evaluator.ProspectiveLedger(database_url=url)
            with ledger.snapshot():
                result = evaluator.audit_sport(ledger, sport, now=datetime.now(timezone.utc))
            store_report(url, build_report(result, sport), sport)
            print(json.dumps({'sport': sport, 'status': result['status'],
                              'protocol': evaluator.PROTOCOL['version']}))
        except Exception as exc:
            failures.append(sport)
            print(json.dumps({'sport': sport, 'status': 'unavailable',
                              'error_type': type(exc).__name__}))
    if failures:
        raise SystemExit('Private NBA/CFB prospective audit incomplete: ' + ','.join(failures))


if __name__ == '__main__':
    main()
