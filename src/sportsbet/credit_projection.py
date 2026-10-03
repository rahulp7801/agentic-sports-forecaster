"""Read-only estimate of when existing Odds API usage could age out.

This module stays outside the frozen prediction/evaluation dependency graph.
It does not reserve credits or promise that a later scan can collect quotes.
"""
from __future__ import annotations

from datetime import date, datetime, timedelta, timezone

from sportsbet.config import settings
from sportsbet.ledger import Ledger


def next_rolling_credit_release(ledger: Ledger, cost: int, *,
                                now: datetime | None = None) -> datetime | None:
    """First UTC midnight when current recorded usage alone permits one cost."""
    if type(cost) is not int or cost < 1 or cost > settings.odds_rolling_credit_limit:
        return None
    now = now or datetime.now(timezone.utc)
    if now.utcoffset() is None:
        raise ValueError('Credit projection requires an aware clock')
    today = now.astimezone(timezone.utc).date()
    with ledger.connect() as db:
        rows = db.execute(
            'SELECT risk_day, credits FROM api_usage WHERE risk_day>=? AND risk_day<=?',
            ((today-timedelta(days=30)).isoformat(), today.isoformat()),
        ).fetchall()
    usage = [(date.fromisoformat(day), credits) for day, credits in rows]
    if sum(credits for _, credits in usage) + cost <= settings.odds_rolling_credit_limit:
        return None
    for days in range(1, 32):
        candidate = today + timedelta(days=days)
        earliest = candidate - timedelta(days=30)
        if sum(credits for day, credits in usage if day >= earliest) + cost <= settings.odds_rolling_credit_limit:
            return datetime.combine(candidate, datetime.min.time(), timezone.utc)
    return None
