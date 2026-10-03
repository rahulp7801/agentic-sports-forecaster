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

The separate `kalshi_stat_only_prior20_eval` scorer checks the original
pregame receipt hash, fixed 144 forecasts and 70 decisions, the pinned source
preflight, and the full 452-contract authenticated result wrapper. It then
compares model versus strict last-20 Brier and log loss on the same verified,
two-sided-price subset. Its game/player intervals describe uncertainty only;
its edge, qualified-pick, ROI and CLV fields remain unavailable or false.
The original v1 `paired_prior_brier` key refers to the broader retained
history comparator. Do not conflate these two baselines or promote the new
diagnostic into the live decision rule.

```powershell
$env:PYTHONPATH='src'
.\.local\team-share-venv\Scripts\python.exe docs\verification\2026-10-04-kalshi-stat-only-prior20-control.py `
  --output .local/kalshi-stat-only-fixed-prior20-control-20261004.json --verify
```

Only after the full authenticated settlement receipt exists and the October 6
06:15 UTC gate has passed, run to a **new ignored output path**:

```powershell
.\.venv\Scripts\python.exe -m sportsbet.quant.kalshi_stat_only_prior20_eval `
  --pair .local/verified-timely-pair-20261003/pair.json `
  --market .local/verified-timely-pair-20261003/market-archive.json `
  --forecast .local/kalshi-stat-only-probabilities-20261004.json `
  --quotes .local/kalshi-stat-only-quotes-20261004.json `
  --decisions .local/kalshi-stat-only-ask-decisions-20261004.json `
  --source-dir .local/verified-timely-pair-20261003/sources `
  --schedule .local/team-share-sources/games.parquet `
  --settlements .local/stat-only-settlement-20261006.json `
  --control .local/kalshi-stat-only-fixed-prior20-control-20261004.json `
  --output .local/stat-only-strict-prior20-after-result.json
```

An actual pinned-input dry run before the gate refused the nonexistent
settlement path before reading it and wrote no report. Focused tests cover
the same-price subset, changed identities, nonbinary results and the gate.

## Outcome-blind comparison on the original paper decisions

Using only the 13:15 UTC strict-control receipt, original pregame forecast,
fixed 70-decision receipt and each decision's original displayed ask, the
side-adjusted strict prior is `prior20_over_probability` for YES and its
complement for NO. This does not select new contracts or read outcomes.

| Original fixed group | Decisions / games | Mean model win probability | Mean strict last-20 win probability | Mean original ask | Strict last-20 probability at least 5 points above ask |
|---|---:|---:|---:|---:|---:|
| All paper decisions | 70 / 15 | 65.59% | 62.93% | 50.34% | 52 / 70 |
| Original model probability at least 75% | 11 / 8 | 80.14% | 72.94% | 52.45% | 11 / 11 |

Within the fixed 70, the simple baseline clears that raw ask-margin test on
20/25 YES and 32/45 NO contracts. The model exceeds the simple baseline on
42/70 decisions, including all 11 high-model-probability decisions. This is
**not** an independent winning selection rule: the original 70 were chosen
using the model, the asks were captured well before kickoff, and the groups
share players and games. It shows that the model's apparent ask margin is not
uniquely attributable to teammate or recent-form context. The model's
additional 7.19 percentage points on the original high-probability group
needs the same authenticated outcome, market, fee and persistence checks as
the primary claim. No raw margin here is a realized return or a qualified
consumer pick.

The first naturally scheduled prelock observation, received at 12:15 UTC
for the 13:30 kickoff, authenticated exact later asks for all four original
decisions in that one game. On those **unchanged four**, mean frozen model
win probability was 68.08%, strict last-20 was 64.29%, and mean later
displayed ask was 41.75%; both probability sets cleared a raw five-point
margin on 4/4. This calculation replayed the original pinned market,
forecast and decision receipts and the retained raw prelock receipt through
the existing exact-ask verifier. It was computed after kickoff but used no
outcome and made no new provider request. Fee-aware hypothetical costs,
quote chronology and receipt hashes are in the
[prelock fee note](2026-10-04-kalshi-stat-only-prelock-fees.md). One correlated
game and unfilled displayed asks cannot prove calibration or an edge.

## Second natural prelock group, before 17:00 UTC kickoff

The 15:43 UTC fee and 15:45 UTC exact-quote Windows tasks completed normally
on October 4. The fixed 17:00 group contains **36 original decisions in eight
games**. All 36 later asks passed the exact-contract and clock replay; 14
fee events were observed. The prelock asks moved down for 11 positions, stayed
unchanged for 18, and moved up for 7. The mean side ask change was
`-0.0005555555555555555555555555556`, so this group did not show a large
average price move in either direction. These are displayed asks, not fills
or a closing-line-value measurement.

The separate offline `kalshi_stat_only_prelock_prior20` diagnostic replays
the original hash-pinned pair, forecast, quotes and decisions, the committed
strict last-20 control, and the raw prelock exact-quote receipt. It never
reads results or changes the 36-candidate membership. At **15:49:52 UTC**,
before kickoff, it found:

| Fixed 17:00 group | Model side probability | Strict last-20 side probability | Later displayed ask | Raw five-point margin at later ask |
|---|---:|---:|---:|---:|
| Same 36 decisions / eight games | 66.23% mean | 63.10% mean | 51.78% mean | Model 35/36; simple prior 24/36 |

Combining this group with the earlier fixed four gives **40/70** original
decisions with both later quote and modeled one-contract fee evidence. The
model clears the raw five-point later-ask test on 39/40; the simple prior
clears it on 28/40. The other 30 fixed decisions remain in four later
scheduled groups and are not replaced. The model-minus-prior probability
difference is a prospective hypothesis to grade after authenticated venue
results; neither margin count is a win, executable price edge, or 75% rate.

The ignored second-group raw fee and quote SHA-256 values are respectively
`4c1b27d5913542bf5ad15e4df5e26fde480181207de06beac50c9ee23e1cc957`
and `435ba1e4d2996982fab1196a974cf89481e80c4ffac16646ff526c55aeeeae1c`.
The ignored strict-prior diagnostic SHA-256 is
`f2bbca489d38ca88a5e6595f27cd883f96c2f26c10fea34d9b0119f19a89a145`.
All were copied byte-identically to the workspace's ignored
`.local/stat-only-prelock-20261004T1700-backup/` directory. The full fixed
70-decision fee/quote replay reports 40 modeled costs and 30 missing later
groups; full-cohort profit, ROI, CLV, fills, outcomes and qualified picks
remain unavailable or false. Its ignored report SHA-256 is
`b15e48df75cb1293c3d047092eccdfa50cff78e99a9832799c2b350d43514230`.

For another fixed kickoff group, rerun the same offline module with its
existing raw `--prelock` receipt and a new ignored `--output` path. It
requires the same original `--pair`, `--market`, `--forecast`, `--quotes`,
`--decisions`, `--source-dir`, `--schedule` and `--control` inputs shown above.

No provider request, paid credit, card, order, bet, consumer pick, model fit,
qualification threshold or frozen decision changed.
