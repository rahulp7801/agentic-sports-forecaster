"""Recheck NFL explicit-result receipts before an exceptional recovery write.

The frozen ledger and forward evaluators retain their original source digests.
This additional write-boundary check uses the same v1 participation contract as
history supplements; it does not substitute play-by-play for published snaps.
"""
from __future__ import annotations

import hashlib
import json

from sportsbet.ingestion.nfl_supplement_proof import POLICY, _sha, valid_supplement
from sportsbet.ingestion.provenance import stat_row_sha256


def valid_recovery_proof(proof: dict) -> bool:
    try:
        if proof['stat_provider'] != 'espn':
            return False
        explicit = proof['explicit_final_source']
        # The recovery planner commits this receipt with json.dumps defaults.
        source_sha = hashlib.sha256(json.dumps(explicit, sort_keys=True,
            separators=(',', ':'), allow_nan=False).encode()).hexdigest()
        if source_sha != proof['stat_source_sha256']:
            return False
        row = proof['stat_row']
        if stat_row_sha256('nfl', row) != proof['stat_record_sha256']:
            return False
        # valid_supplement validates exact game/athlete identity, source URLs,
        # receipt chronology, and the independent nflverse offensive snap row.
        # The enclosing manifest is an adapter; it does not claim to recheck
        # the raw ESPN response archive, which was checked during preview.
        manifest = dict(version=1, policy_version=POLICY,
            bundle_sha256=source_sha, game=proof, explicit_source=explicit,
            explicit_source_sha256=_sha(explicit),
            stat_record_sha256=proof['stat_record_sha256'])
        return valid_supplement(row, manifest, _sha(manifest),
            proof['stat_observed_at'], proof)
    except (ArithmeticError, KeyError, TypeError, ValueError):
        return False
