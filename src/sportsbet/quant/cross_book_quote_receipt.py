"""Source-committed alternate sportsbook pairs from an already fetched event."""
from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal

from sportsbet.ingestion.prop_odds import (
    PlayerPropSnapshotCreate, prop_quote_evidence_valid,
)
from sportsbet.model_contract import PROP_MARKETS
from sportsbet.quant.vig import american_to_raw_prob, remove_vig_multiplicative

VERSION = 'cross-book-quote-receipt-v2'
MAX_REFERENCES = 16


def capture(offer: PlayerPropSnapshotCreate, quotes: list[PlayerPropSnapshotCreate]) -> dict:
    """Keep exact opposite-side pairs from other books in the same response."""
    result = dict(version=VERSION, references=[])
    if not prop_quote_evidence_valid(offer):
        return result
    by_book: dict[str, list[PlayerPropSnapshotCreate]] = {}
    for quote in quotes:
        if (quote.sport, quote.game_id, quote.player_name, quote.prop_type,
                quote.line, quote.source_provider, quote.source_sha256,
                quote.game_start_time) != (offer.sport, offer.game_id,
                offer.player_name, offer.prop_type, offer.line,
                offer.source_provider, offer.source_sha256,
                offer.game_start_time):
            continue
        by_book.setdefault(quote.sportsbook, []).append(quote)
    own = by_book.pop(offer.sportsbook, [])
    # An ambiguous price from the offered book cannot become a paper trade.
    if (len(own) != 2 or {q.side for q in own} != {'Over', 'Under'}
            or own[0].snapped_at != own[1].snapped_at
            or sum(q.source_record_sha256 == offer.source_record_sha256 for q in own) != 1):
        return result
    if len(by_book) > MAX_REFERENCES:
        return result
    for book, items in sorted(by_book.items()):
        if len(items) != 2 or {q.side for q in items} != {'Over', 'Under'}:
            continue
        over, under = sorted(items, key=lambda q: q.side == 'Over', reverse=True)
        if (over.snapped_at != under.snapped_at
                or not all(prop_quote_evidence_valid(q) for q in items)):
            continue
        try:
            remove_vig_multiplicative([over.implied_probability, under.implied_probability])
        except (ArithmeticError, ValueError):
            continue
        result['references'].append(dict(sportsbook=book,
            quote_time=over.snapped_at.isoformat(),over_odds=over.price,
            under_odds=under.price,
            over_record_sha256=over.source_record_sha256,
            under_record_sha256=under.source_record_sha256))
    return result


def verified_references(payload: dict, *, decision_at) -> dict[str, float] | None:
    """Rebuild each committed quote and filter to fresh, pregame references."""
    from sportsbet.ledger import quote_evidence_valid, utc_timestamp

    receipt = payload.get('cross_book_quote_receipt')
    if (not quote_evidence_valid(payload) or not isinstance(receipt, dict)
            or receipt.get('version') != VERSION
            or not isinstance(receipt.get('references'), list)
            or len(receipt['references']) > MAX_REFERENCES):
        return None
    try:
        market, = (key for key, value in PROP_MARKETS[payload['sport']].items()
                   if value == payload['prop_type'])
        decision = (decision_at.astimezone(timezone.utc) if isinstance(decision_at,datetime)
                    and decision_at.utcoffset() is not None else utc_timestamp(decision_at))
        start = utc_timestamp(payload['game_start_time'])
        source = payload['quote_source_sha256']
        books = set()
        result = {}
        for ref in receipt['references']:
            book = ref['sportsbook']
            if (not isinstance(book, str) or not book or book == payload['sportsbook']
                    or book in books):
                return None
            books.add(book)
            observed = utc_timestamp(ref['quote_time'])
            quotes = []
            for side in ('Over', 'Under'):
                odds = ref[side.lower() + '_odds']
                if type(odds) is not int:
                    return None
                quote = PlayerPropSnapshotCreate(sport=payload['sport'],
                    game_id=payload['game_id'], player_name=payload['player'],
                    sportsbook=book, prop_type=market,
                    line=Decimal(str(payload['line'])), price=odds,
                    implied_probability=american_to_raw_prob(odds),
                    game_start_time=start, source_provider='the_odds_api',
                    source_sha256=source,
                    source_record_sha256=ref[side.lower() + '_record_sha256'],
                    snapped_at=observed, side=side)
                if not prop_quote_evidence_valid(quote):
                    return None
                quotes.append(quote)
            if 0 <= (decision-observed).total_seconds() <= 300 and decision < start:
                result[book] = float(remove_vig_multiplicative(
                    [q.implied_probability for q in quotes])[0])
        return result
    except (KeyError, TypeError, ValueError, ArithmeticError):
        return None
