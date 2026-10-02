"""Portable receipt verification for the frozen NFL recent-role shadow.

The frozen producer uses gzip.compress(mtime=0). Python's gzip OS header byte can
be 3 on Linux and 10 on Windows for identical canonical input. Recompute every
model and source check, and tolerate only that one byte during audit replay.
"""
from __future__ import annotations

import base64
import binascii
import json
import zlib

from sportsbet.ledger import utc_timestamp
from sportsbet.quant import nfl_recent_role_shadow as frozen

AUDIT_PROTOCOL = 'nfl-recent-role-portable-proof-v1'
_GZIP_OS_BYTES = frozenset((3, 10))


def _same_gzip_except_os(stored: str, replayed: str) -> bool:
    left = base64.b64decode(stored, validate=True)
    right = base64.b64decode(replayed, validate=True)
    return (len(left) == len(right) and len(left) >= 10
        and left[:9] == right[:9] and left[10:] == right[10:]
        and left[9] in _GZIP_OS_BYTES and right[9] in _GZIP_OS_BYTES)


def verified_recorded_shadow_probability(payload: dict) -> float | None:
    """Replay a stored receipt without changing the frozen model or its inputs."""
    try:
        receipt = utc_timestamp(payload['role_history_shadow_recorded_at'])
        captured = utc_timestamp(payload['captured_at'])
        kickoff = utc_timestamp(payload['game_start_time'])
        quote = utc_timestamp(payload['quote_time'])
        if not captured <= receipt < kickoff or not 0 <= (receipt-quote).total_seconds() <= 300:
            return None
        record = payload['role_history_shadow']
        if not isinstance(record, dict) or record.get('status') != 'predicted':
            return None
        inputs = record['inputs']
        decoded = frozen.decoded_inputs(json.dumps(inputs, sort_keys=True, separators=(',', ':')))
        expected = frozen.shadow_record(payload, decoded)
        if expected.get('status') != 'predicted' or set(record) != set(expected):
            return None
        if record['record_sha256'] != frozen.digest({k: v for k, v in record.items() if k != 'record_sha256'}):
            return None
        if any(record[k] != expected[k] for k in record if k not in ('inputs', 'record_sha256')):
            return None
        produced_inputs = expected['inputs']
        if set(inputs) != set(produced_inputs):
            return None
        if any(inputs[k] != produced_inputs[k] for k in inputs if k != 'data'):
            return None
        if not _same_gzip_except_os(inputs['data'], produced_inputs['data']):
            return None
        return expected['probability']
    except (KeyError, TypeError, ValueError, OverflowError, AttributeError, binascii.Error, zlib.error):
        return None
