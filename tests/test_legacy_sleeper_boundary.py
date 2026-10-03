"""Commercial launch boundary for the dormant legacy context graph."""
from __future__ import annotations

import pytest

from sportsbet.graph.agents import _fetch_sleeper_injuries
from sportsbet.ingestion import sleeper


@pytest.mark.asyncio
@pytest.mark.parametrize(("sport", "team"), [("nfl", "KC"), ("nba", "LAL")])
async def test_legacy_context_never_opens_unlicensed_sleeper_client(
    monkeypatch: pytest.MonkeyPatch, sport: str, team: str
) -> None:
    requests: list[object] = []

    def forbidden_client(*args: object, **kwargs: object) -> object:
        requests.append((args, kwargs))
        raise AssertionError("Sleeper API must not be called by the consumer graph")

    monkeypatch.setattr(sleeper, "_AsyncClient", forbidden_client)
    assert await _fetch_sleeper_injuries(sport, team) == []
    assert requests == []
