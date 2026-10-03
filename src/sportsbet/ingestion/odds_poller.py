"""Odds API poller with budget manager and staleness guard.

Implements OddsAPIPoller (async context manager) for fetching NFL and NBA odds
and player prop odds from The Odds API, BudgetExhaustedError for credit-cap
enforcement, and is_stale() for staleness checking before odds reach the
Arbitrage Agent.

Every paid request reserves its maximum specified-market cost in the same
persistent ledger as scheduled scans. Provider remaining-credit headers add
another guard; the local instance counter does not authorize requests.
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import TYPE_CHECKING, Literal

import httpx
import structlog

from sportsbet.config import DEFAULT_DAILY_CREDIT_LIMIT, settings
from sportsbet.ledger import Ledger
from sportsbet.model_contract import PROP_MARKETS

if TYPE_CHECKING:
    pass

log = structlog.get_logger()

# ---------------------------------------------------------------------------
# Module constants
# ---------------------------------------------------------------------------

ODDS_API_BASE = "https://api.the-odds-api.com"
NFL_SPORT_KEY = "americanfootball_nfl"
NBA_SPORT_KEY = "basketball_nba"
DEFAULT_STALENESS_MINUTES = 5

# Player prop market keys for NFL (7 markets)
NFL_PROP_MARKETS = (
    "player_pass_yds,player_pass_tds,player_rush_yds,"
    "player_rush_tds,player_reception_yds,player_reception_tds,"
    "player_receptions"
)

# Player prop market keys for NBA (7 markets)
NBA_PROP_MARKETS = (
    "player_points,player_rebounds,player_assists,"
    "player_threes,player_steals,player_blocks,"
    "player_points_rebounds_assists"
)


# ---------------------------------------------------------------------------
# Exceptions
# ---------------------------------------------------------------------------


class BudgetExhaustedError(RuntimeError):
    """Raised when Odds API daily credit cap is reached or credits_remaining < 1."""


# ---------------------------------------------------------------------------
# Staleness guard
# ---------------------------------------------------------------------------


def is_stale(
    snapped_at: datetime,
    threshold_minutes: int = DEFAULT_STALENESS_MINUTES,
) -> bool:
    """Return True if snapped_at is older than threshold_minutes, else False.

    Args:
        snapped_at: Timezone-aware UTC datetime of the odds snapshot.
        threshold_minutes: Maximum acceptable age in minutes. Defaults to 5.

    Returns:
        True when stale (age > threshold), False when fresh.

    Raises:
        TypeError: If snapped_at is a naive datetime (no tzinfo).
    """
    now = datetime.now(timezone.utc)
    if snapped_at.tzinfo is None:
        raise TypeError(
            "snapped_at must be timezone-aware; got naive datetime. "
            "Use datetime.now(timezone.utc) or attach tzinfo=timezone.utc."
        )
    age_minutes = (now - snapped_at).total_seconds() / 60.0
    return age_minutes > threshold_minutes


# ---------------------------------------------------------------------------
# OddsAPIPoller
# ---------------------------------------------------------------------------


class OddsAPIPoller:
    """Legacy NFL/NBA poller sharing the scheduled scan credit ledger.

    Usage:
        async with OddsAPIPoller(api_key="...", daily_credit_cap=20) as poller:
            odds = await poller.fetch_nfl_odds()

    Each request reserves its maximum configured-market cost before network
    I/O. The provider's remaining-credit header adds a second guard.
    """

    def __init__(self, api_key: str, daily_credit_cap: int) -> None:
        if not isinstance(api_key, str) or not api_key.strip():
            raise ValueError('Legacy poller requires an API key')
        if (type(daily_credit_cap) is not int
                or not 1 <= daily_credit_cap <= DEFAULT_DAILY_CREDIT_LIMIT):
            raise ValueError('Legacy poller allowance must be at most 20 credits')
        self._api_key = api_key
        self._daily_credit_cap = daily_credit_cap
        self._credits_remaining: int | None = None
        self._client: httpx.AsyncClient | None = None
        self._client_cm: httpx.AsyncClient | None = None
        self._ledger: Ledger | None = None

    async def __aenter__(self) -> "OddsAPIPoller":
        # Enter httpx.AsyncClient as context manager so mock patches work correctly.
        # self._client_cm is the context manager object; self._client is the active client.
        self._client_cm = httpx.AsyncClient(base_url=ODDS_API_BASE, timeout=10.0)
        self._client = await self._client_cm.__aenter__()
        return self

    async def __aexit__(self, exc_type: object, exc_val: object, exc_tb: object) -> None:
        if self._client_cm is not None:
            await self._client_cm.__aexit__(exc_type, exc_val, exc_tb)
            self._client_cm = None
            self._client = None

    def _active_client(self) -> httpx.AsyncClient:
        """Return the open client or fail safely when lifecycle usage is invalid."""
        if self._client is None:
            raise RuntimeError(
                "OddsAPIPoller requests require an active async context manager"
            )
        return self._client

    def _reserve(self, cost: int, sport: Literal['nfl', 'nba']) -> None:
        """Fail closed before I/O; leave two scheduled prop checks reserved."""
        if not settings.analytics_database_url:
            raise BudgetExhaustedError('Shared analytics credit ledger is required')
        if settings.odds_rolling_credit_limit > 450:
            raise BudgetExhaustedError('Rolling allowance exceeds the approved 450 credits')
        width = len(PROP_MARKETS[sport])
        holdback = 2 * width if self._daily_credit_cap >= 3 * width else 0
        if self._ledger is None:
            self._ledger = Ledger()
        if (type(cost) is not int or cost < 1
                or not self._ledger.reserve_api_credits(
                    cost, self._daily_credit_cap, holdback=holdback)):
            raise BudgetExhaustedError('Shared Odds API allowance or pregame reserve exhausted')

    @staticmethod
    def _game_cost(regions: str, markets: str) -> int:
        """Bound legacy game odds to the one approved region and three markets."""
        names = markets.split(',') if isinstance(markets, str) else []
        if (regions != 'us' or not names or len(names) != len(set(names))
                or not set(names) <= {'h2h', 'spreads', 'totals'}):
            raise ValueError('Unsupported legacy game-odds request scope')
        return len(names)

    async def fetch_nfl_odds(
        self,
        regions: str = "us",
        markets: str = "h2h,spreads,totals",
    ) -> list[dict]:  # type: ignore[type-arg]
        """Fetch current NFL odds from The Odds API.

        Raises:
            BudgetExhaustedError: If the shared ledger or provider remaining
                balance cannot cover the request and pregame reserve.
                No HTTP call is made in this case.
            httpx.HTTPStatusError: If the API returns a non-2xx status.

        Returns:
            Parsed JSON list of event dicts from the Odds API.
        """
        cost = self._game_cost(regions, markets)
        if self._credits_remaining is not None and self._credits_remaining < cost:
            raise BudgetExhaustedError(
                f"Odds API daily credit cap reached. "
                f"credits_remaining={self._credits_remaining}, "
                f"daily_credit_cap={self._daily_credit_cap}"
            )

        client = self._active_client()
        self._reserve(cost, 'nfl')

        response = await client.get(
            f"/v4/sports/{NFL_SPORT_KEY}/odds",
            params={
                "apiKey": self._api_key,
                "regions": regions,
                "markets": markets,
                "oddsFormat": "american",
            },
        )
        response.raise_for_status()

        self._credits_remaining = int(
            response.headers.get("x-requests-remaining", "0")
        )

        log.info(
            "odds_api_fetched",
            credits_remaining=self._credits_remaining,
            sport_key=NFL_SPORT_KEY,
        )

        return response.json()  # type: ignore[no-any-return]

    async def fetch_nba_odds(
        self,
        regions: str = "us",
        markets: str = "h2h,spreads,totals",
    ) -> list[dict]:  # type: ignore[type-arg]
        """Fetch current NBA game odds from The Odds API.

        Raises:
            BudgetExhaustedError: If the shared ledger or provider remaining
                balance cannot cover the request and pregame reserve.
                No HTTP call is made in this case.
            httpx.HTTPStatusError: If the API returns a non-2xx status.

        Returns:
            Parsed JSON list of event dicts from the Odds API.
        """
        cost = self._game_cost(regions, markets)
        if self._credits_remaining is not None and self._credits_remaining < cost:
            raise BudgetExhaustedError(
                f"Odds API daily credit cap reached. "
                f"credits_remaining={self._credits_remaining}, "
                f"daily_credit_cap={self._daily_credit_cap}"
            )

        client = self._active_client()
        self._reserve(cost, 'nba')

        response = await client.get(
            f"/v4/sports/{NBA_SPORT_KEY}/odds",
            params={
                "apiKey": self._api_key,
                "regions": regions,
                "markets": markets,
                "oddsFormat": "american",
            },
        )
        response.raise_for_status()

        self._credits_remaining = int(
            response.headers.get("x-requests-remaining", "0")
        )

        log.info(
            "odds_api_fetched",
            credits_remaining=self._credits_remaining,
            sport_key=NBA_SPORT_KEY,
        )

        return response.json()  # type: ignore[no-any-return]

    async def fetch_player_props(
        self,
        sport: Literal["nfl", "nba"],
    ) -> list[dict]:  # type: ignore[type-arg]
        """Fetch current player prop odds via two-step event-list + per-event call.

        Step 1: GET /v4/sports/{sport_key}/events — retrieve list of live events.
        Step 2: For each event, GET /v4/sports/{sport_key}/events/{id}/odds with
                prop markets. The ledger reserves up to seven credits before
                each per-event call.

        Args:
            sport: "nfl" or "nba" — determines sport_key and prop market set.

        Raises:
            BudgetExhaustedError: If the shared ledger or provider remaining
                balance cannot cover the event list or a seven-market call.
            httpx.HTTPStatusError: If any API call returns a non-2xx status.

        Returns:
            List of raw per-event prop response dicts (one dict per event).
        """
        client = self._active_client()
        if sport not in ('nfl', 'nba'):
            raise ValueError('Unsupported legacy prop sport')

        sport_key = NFL_SPORT_KEY if sport == "nfl" else NBA_SPORT_KEY
        prop_markets = NFL_PROP_MARKETS if sport == "nfl" else NBA_PROP_MARKETS

        # Step 1: reserve one credit conservatively for the event list.
        if self._credits_remaining is not None and self._credits_remaining < 1:
            raise BudgetExhaustedError('Provider allowance exhausted')
        self._reserve(1, sport)
        events_response = await client.get(
            f"/v4/sports/{sport_key}/events",
            params={"apiKey": self._api_key},
        )
        events_response.raise_for_status()
        self._credits_remaining = int(
            events_response.headers.get("x-requests-remaining", "0")
        )
        events: list[dict] = events_response.json()  # type: ignore[assignment]

        log.info(
            "prop_events_fetched",
            sport=sport,
            event_count=len(events),
            credits_remaining=self._credits_remaining,
        )

        # Step 2: per-event prop odds
        results: list[dict] = []  # type: ignore[type-arg]
        cost = len(prop_markets.split(','))
        for event in events:
            # Budget guard before each per-event call
            if self._credits_remaining is not None and self._credits_remaining < cost:
                raise BudgetExhaustedError(
                    f"Odds API daily credit cap approaching. "
                    f"credits_remaining={self._credits_remaining}, "
                    f"daily_credit_cap={self._daily_credit_cap}"
                )

            self._reserve(cost, sport)
            event_id = event["id"]
            props_response = await client.get(
                f"/v4/sports/{sport_key}/events/{event_id}/odds",
                params={
                    "apiKey": self._api_key,
                    "regions": "us",
                    "markets": prop_markets,
                    "oddsFormat": "american",
                },
            )
            props_response.raise_for_status()
            self._credits_remaining = int(
                props_response.headers.get("x-requests-remaining", "0")
            )
            results.append(props_response.json())

        log.info(
            "player_props_fetched",
            sport=sport,
            results_count=len(results),
            credits_remaining=self._credits_remaining,
        )

        return results
