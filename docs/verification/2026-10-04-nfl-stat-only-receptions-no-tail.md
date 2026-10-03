# Receptions-only 75% NO tail: exploratory replay and prospective checkpoint

This is a **separate, untraded diagnostic**, chosen after inspecting earlier
2025 outcomes. It does not modify the 2026 frozen stat-only model, the original
452 market contracts, 144 forecasts, 70 paper ask decisions, 11 high-probability
subset, sportsbook consumer picks, or any qualification threshold. No additional
market quote, API credit, order or bet is made.

## Retrospective corrected-history stress test

The existing [corrected played-game replay](2026-10-03-nfl-stat-only-exploratory.md)
uses hash-verified free 2024-25 player statistics, snap counts, crosswalk and
game schedule; the original aggregate report remains **byte identical**, SHA-256
`a72ff20d2b86f65f35c12e91467c8057a37e5744b1e159c7394f2a6731a0f396`.
The extended script writes a separate aggregate tail report under ignored
`.local/nfl-stat-only-corrected-tail-20261004.json`, SHA-256
`1ab6e8cfa7f7c660e879a32e11a3aea3679528f4448ad9a4fcedfd7d3e4bdfa3`.
It selects NO forecasts with the already selected model probability at least
0.75, using synthetic higher lines from strictly prior played games, November
2025-or-later target games and 2026 quoted player/prop identities. No
coefficient is refitted on these target outcomes.

| 2025 corrected-history slice | Picks | Games | NO wins | Row win rate | Mean model NO | Equal-game win rate | Game-cluster 95% |
|---|---:|---:|---:|---:|---:|---:|---|
| Receptions, snap-backed zeros included | 112 | 77 | 91 | 81.25% | 81.57% | 83.55% | 76.18%-90.92% |
| Receptions, explicit target stat | 110 | 77 | 89 | 80.91% | 81.56% | 83.55% | 76.18%-90.92% |
| Receiving yards, snap-backed zeros included | 19 | 19 | 13 | 68.42% | 78.52% | 68.42% | 45.40%-91.44% |

For the 112 receptions examples, the candidate-minus-prior-20 Brier difference
is -0.00977, but its game-cluster interval is [-0.01968, +0.00015] and its
player-cluster interval is [-0.02085, +0.00131]. The high-confidence subgroup
therefore does **not** establish superiority even to that simple probability
baseline. The 2025 source files were corrected after target games, historical
pregame injury and bookmaker quotes are absent, the 2026 quoted-player universe
is selected, and this 0.75 slice was examined after the historical outcomes.
These intervals are descriptive, unadjusted for repeated research and not an
untouched holdout. The 81.25% result is not a verified live win rate, a
fee-adjusted return, or a profitable market edge.

Reproduce the two aggregate reports without network access:

```powershell
$env:PYTHONPATH='src'
.\.local\team-share-venv\Scripts\python.exe docs\verification\2026-10-03-nfl-stat-only-corrected-transfer.py
```

The script refuses to rewrite the original report if its exact pinned bytes
would change. Raw player rows stay in ignored local source files.

## Before-kickoff fixed forward subgroup

The subgroup was identified at 2026-10-04 06:50 UTC, before the first
October 4 13:30 UTC kickoff. The separate forward diagnostic
`kalshi_stat_only_receptions_no_tail.py` pinned the **8 original NO receptions
paper candidates** with frozen model win probability at least 0.75. They span
**6 games**; their mean model probability is 0.80208 and mean displayed,
unfilled ask is 0.5400. The selected ticker-list digest is
`ed073d479d79c870a7b11c1bdc81460a89076704572aa48c668e6ec9bd058ee7`.
An offline replay of every pinned source/model/quote/decision input produced
`.local/kalshi-stat-only-receptions-no-tail-20261004.json`, file SHA-256
`3c721e8817f68f9965631f6e77903f609da64db5ce0c6d2abdc928dc4047ceff`.
No game result was used or requested. An outcome-blind, exact-ticker join to the
already frozen [teammate-context receipt](2026-10-04-kalshi-stat-only-teammate-context.md)
matched all eight. That receipt has record SHA-256
`0fce75d466db103ace59f5adf4034c1e5a60e2fad6795d28a57eec51c269b31a`
and file SHA-256
`733dc3f4a1b4d5fc85aeb32ce5f8117d264976e33a1f51933da883735484c792`.
Four of the eight have an Out/Doubtful skill-position teammate accounting for
>25% of their team's weeks 1-3 targets; one has (10%,25%], one (0%,10%],
one has only a Questionable teammate, and one has no reported skill-teammate
risk. All eight forecast subjects are absent from the dated injury *listing*,
which does not prove they were active at kickoff. No selected row has an acute
quarterback teammate. This concentration is a specific overconfidence risk for
NO receptions forecasts. The context split was observed before results, but it
is not an independent calibration experiment, a causal effect estimate, or a
reason to change the frozen eight, prices, model, or threshold.

The original eight recorded positive displayed sizes from 13.00 to 7,201.63
and their prices were received 63.57-63.72 seconds before the paper decision.
Their arithmetic model-minus-ask gross margins range from 0.1767 to 0.3499.
Those asks were captured many hours before kickoff, with no fill or fee proof.
The separately scheduled unsigned exact-ticker prelock observations are the
next test of price persistence; they cannot retroactively replace the asks.

The separate 11-candidate context diagnostic retains its own fixed denominator and grader.
The original 11-pick high-probability report and 70-pick primary cohort retain
their own denominators; this subgroup cannot replace them after results.

The [offline cross-check](2026-10-04-nfl-stat-only-receptions-context-crosscheck.py)
verifies the context receipt's file and record digests, pregame timing, complete
70-row identity, and each selected decision's game, side, probability, ask, displayed depth and quote age
before printing only anonymous aggregate counts:

```powershell
$env:PYTHONPATH='src'
.\.venv\Scripts\python.exe docs\verification\2026-10-04-nfl-stat-only-receptions-context-crosscheck.py
```

```powershell
.\.venv\Scripts\python.exe -m sportsbet.quant.kalshi_stat_only_receptions_no_tail `
  --pair .local/verified-timely-pair-20261003/pair.json `
  --market .local/verified-timely-pair-20261003/market-archive.json `
  --forecast .local/kalshi-stat-only-probabilities-20261004.json `
  --quotes .local/kalshi-stat-only-quotes-20261004.json `
  --decisions .local/kalshi-stat-only-ask-decisions-20261004.json `
  --source-dir .local/verified-timely-pair-20261003/sources `
  --schedule .local/team-share-sources/games.parquet `
  --historical-tail .local/nfl-stat-only-corrected-tail-20261004.json `
  --output .local/kalshi-stat-only-receptions-no-tail-replay.json
```

After **October 6 06:15 UTC**, only if the independently scheduled full
452-contract unsigned result receipt exists and verifies, run the same command
with `--settlements .local/stat-only-settlement-20261006.json` and a new ignored
output path. Missing or invalid results remain in the eight-contract subgroup
denominator; the full-group win rate and gross displayed-ask profit stay null
until all eight are venue-verified. The scorer keeps fills, fees, ROI, CLV,
edge and consumer qualification unset. Eight decisions across six games
cannot establish the requested repeatable 75% individual-pick performance or
an executable edge.