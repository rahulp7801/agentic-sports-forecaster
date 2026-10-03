"""Admission-only source proof for NFL passing and rushing forecasts.

The frozen query builder determines the history sample and probability. Append
one aggregate to that same SELECT, so corrections cannot race a second read.
This module is outside byte-pinned prospective evaluator dependencies.
"""
from __future__ import annotations

import json
from collections.abc import Mapping

from sportsbet.graph.models import PropParams
from sportsbet.ingestion.provenance import stat_row_sha256


_FROM = '\nFROM player_stats\nWHERE '
_PROOF = ("BOOL_AND(source_provider = 'nflverse' "
    "AND source_sha256 ~ '^[0-9a-f]{{64}}$' "
    "AND source_record_sha256 ~ '^[0-9a-f]{{64}}$' "
    "AND source_observed_at IS NOT NULL AND source_observed_at <= ${index}) "
    "AS history_source_verified")
_FIELDS = ('player_id', 'season', 'week', 'team', 'passing_yards',
    'rushing_yards', 'receiving_yards', 'receptions', 'source_record_sha256')
_RECORDS = ("JSONB_AGG(JSONB_BUILD_OBJECT(" + ', '.join(
    f"'{field}', {field}" for field in _FIELDS) + ")) AS history_source_rows")


def attach_source_proof(sql: str, args: tuple[object, ...],
                        params: PropParams) -> tuple[str, tuple[object, ...]]:
    """Add a bound source cutoff to the unchanged production history sample."""
    if params.sport != 'nfl' or params.prop_type not in ('pass_yds', 'rush_yds'):
        return sql, args
    cutoff = params.observed_before
    if cutoff is None:
        return sql, args  # The scanner admission gate rejects absent proof.
    if params.as_of_date is None or cutoff.utcoffset() is None:
        raise ValueError('NFL core source proof requires aware selection and game cutoffs')
    if sql.count(_FROM) != 1:
        raise ValueError('NFL core history query shape changed; proof unavailable')
    proof = _PROOF.format(index=len(args)+1)
    return sql.replace(_FROM, ',\n    '+proof+',\n    '+_RECORDS+_FROM, 1), (*args, cutoff)


def verify_source_rows(rows: object, total: int) -> bool:
    """Check stored row commitments for the exact aggregate sample.

    asyncpg returns jsonb as text with its default codec. Legacy NFL hashes did
    not include receptions, but did commit every field used by core forecasts.
    """
    if isinstance(rows, str):
        try:
            rows = json.loads(rows)
        except ValueError:
            return False
    if not isinstance(rows, list) or len(rows) != total or total <= 0:
        return False
    for row in rows:
        if not isinstance(row, Mapping) or set(row) != set(_FIELDS):
            return False
        try:
            current = stat_row_sha256('nfl', row)
            legacy = stat_row_sha256('nfl', row, legacy_nfl=True)
        except (TypeError, ValueError):
            return False
        if row['source_record_sha256'] not in (current, legacy):
            return False
    return True
