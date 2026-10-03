# Strict prior-20 control on the fixed NFL paper cohort

The frozen `kalshi-nfl-stat-only-forward-score-v1` calls its unfitted
historical comparator `prior20` in two report keys. The original pregame
forecast receipt actually computed
`(hits_in_the_retained_20_to_40_games + 0.5) / (retained_games + 1)`.
That is a valid broader Jeffreys history baseline, **not** a strict last-20
baseline. The v1 scorer, original forecast, decisions, model and prices remain
frozen; a future v1 result must be described as model versus the full retained
history despite the old key name. No 75% or market-edge claim may rely on
calling it strict prior-20.

The separate [outcome-blind control script](2026-10-04-kalshi-stat-only-prior20-control.py)
replays the five original hash-pinned pregame receipts and their source,
schedule, player identity and per-forecast history commitments. For each
original forecast it computes
`(hits_in_the_last_20_prior_played_games + 0.5) / 21` at the **same line**.
It verifies the stored broader comparator, retains all 144 original forecast
identities and the same 70 paper-decision tickers, and neither selects nor
reprices a contract. Missing or changed source evidence fails closed.

The exclusive private receipt was written at **2026-10-04 13:15:00 UTC**,
before the first selected kickoff at 13:30 UTC. It contains exact per-ticker
probabilities only in ignored local storage:

- Receipt: `.local/kalshi-stat-only-fixed-prior20-control-20261004.json`
- Receipt SHA-256: `8b052035e6ebc3b4aaa27f00aea5d03e601cfd414e93fcaee9248634082fa3ff`
- Sorted forecast-row SHA-256:
  `aa123f0f87a88a1d0d886f9f29eb8d7409118591f3f7e06ca5f6a2aee4302047`
- Original forecasts: 144; unchanged paper decisions: 70.

The same source/receipt replay succeeded immediately with `--verify`,
without rewriting the receipt. A byte-identical ignored backup is retained
under the original D-workspace `.local/kalshi-stat-only-prior20-control-20261004/`
directory. The generated timestamp is a local-clock
assertion; this remote pregame commit supplies a second chronology marker.
Neither marker proves a fill, current roster participation, result or edge.

After the authenticated full-452 exact-contract result gate on October 6,
score this pinned strict prior-20 value on the **identical verified forecasts
and games** as the original market/model/full-history comparison. Missing
outcomes remain in the fixed denominator. Keep the original v1 report intact
and label its baseline accurately. The additional comparison is a diagnostic;
the 15 shared games cannot satisfy the existing 50-game skill gate.

```powershell
$env:PYTHONPATH='src'
.\.local\team-share-venv\Scripts\python.exe docs\verification\2026-10-04-kalshi-stat-only-prior20-control.py `
  --output .local/kalshi-stat-only-fixed-prior20-control-20261004.json --verify
```

No provider request, paid credit, card, order, bet, consumer pick, model fit,
qualification threshold or frozen decision changed.
