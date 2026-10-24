"""Explicit source replay optimization keeps the default writer contract."""
import pytest

from sportsbet.ingestion.upsert import upsert_rows


def test_skip_unchanged_updates_requires_preserving_original_observation():
    with pytest.raises(ValueError,match='requires observation preservation'):
        upsert_rows(['id'],skip_unchanged_updates=True)
