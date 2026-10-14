# Prospective alternate-book quote receipts, v2

The production scanner models one best sportsbook offer per exact player, market, line and side. This avoids redundant model work, but the frozen cross-book v1 evaluator looked for other books among recorded forecast rows. Those other books were absent by construction, even when the append-only quote archive contained them. The v1 report and its frozen sources remain unchanged; its zero selections cannot establish absence of an alternate-book price difference.

Starting with forecasts captured **after 2026-10-03 00:00 UTC**, the scanner attaches `cross_book_quote_receipt` to each private immutable forecast. It contains only exact same event, player, provider market and line, from the same provider event response as the offered quote. Each other sportsbook must have exactly one Over and one Under quote with the same source timestamp. The receipt retains both prices, timestamp and original normalized record hashes. Conflicting or incomplete pairs are excluded. A source hash change, different game/line, duplicated book, future/stale price or postgame decision fails validation or has no reference vote. The offered book is excluded from its own reference. The existing source response and quote archive are used; **no additional API request** is made.

`cross-book-receipt-forward-v2` is a separate private, fixed selection rule. It requires an eligible source-backed forecast and matching same-book no-vig baseline, a fresh offered quote and at least one fresh other-book no-vig pair (at most 300 seconds old at forecast capture). It uses the median of other books' fair Over probabilities, takes the offered side only when its implied expected return is at least 2%, and selects the earliest qualifying batch and strongest offer at that instant, at most once per player/game. Outcomes are authenticated by the existing settlement verifier and never enter selection. Settled decisions are scored and clustered by game. Minimum evidence is 50 paired games, 100 decided selections and 30 selection games. Even a positive interval is `review_required`; `promote` remains false. This is a price research signal, not a dashboard pick or a claim of profit.

The new evaluator checks the frozen v1 dependency digests and the v2 quote-capture source digest. Future changes require a new protocol version. Earlier forecast rows, including those observed during implementation, cannot enter the v2 cohort. With an existing private audit connection, run:

```powershell
python -m sportsbet.quant.cross_book_receipt_forward --sport all --output .local/cross-book-receipt-v2.json
```

The report is private. Its count of comparable offers and exclusions should be reviewed alongside accepted picks, settlement coverage and the frozen v1 reports. There is no quote-provider call, bet, model change, qualification change, reserve change or automatic public promotion in this version.
