# NFL stat-only fixed-candidate prelock ask observation

This adds a **later, separate** read of the 70 already frozen paper decisions
from the October 4 stat-only cohort. It does not change their model
probabilities, original asks, selected sides, consumer picks, or qualification
thresholds. Each request is an unsigned public Kalshi exact-ticker `GET`; no
Odds API credit, Kalshi key, order, bet, card, or subscription is involved.

The collector first replays the pinned original pair, market archive, source
files, stat-only forecast, original quote and fixed decision policy through
`kalshi_stat_only_forward_eval.preflight`. It partitions only the **70 fixed
candidates** by their already recorded kickoff and makes one observation in
the window 90 to 70 minutes before that kickoff, stopping ten minutes before
the one-hour board lock. Six kickoff groups contain 4, 36, 5, 15, 6 and 4
candidate tickers, respectively; at most seven public `/markets` batches
cover all 70. An existing output file blocks a repeat. A prospective
two-host HTTP Date check must pass before any market request, and the proof is
retained with raw response pages, request/receipt times and a receipt hash.
Unreturned, failed, closed, undersized, identity-changed and invalid quotes
remain in the fixed denominator. The scorer reports movement of the chosen
side's **displayed ask** from its original frozen ask, weighting games
separately as well as contracts. The report explicitly leaves fills, a true
closing line, ROI, CLV, edge and qualified picks unverified. A later ask
change is useful market feedback, not proof that a contract could be bought
or profitably sold at either displayed price.

From the private repository root, with the ignored original artifacts retained:

```sh
python -m sportsbet.quant.kalshi_stat_only_prelock \
  --pair .local/verified-timely-pair-20261003/pair.json \
  --market .local/verified-timely-pair-20261003/market-archive.json \
  --forecast .local/kalshi-stat-only-probabilities-20261004.json \
  --quotes .local/kalshi-stat-only-quotes-20261004.json \
  --decisions .local/kalshi-stat-only-ask-decisions-20261004.json \
  --source-dir .local/verified-timely-pair-20261003/sources \
  --schedule .local/team-share-sources/games.parquet \
  --kickoff 2026-10-04T13:30:00+00:00 \
  --output .local/stat-only-prelock-20261004T1330.json \
  --report .local/stat-only-prelock-20261004T1330-report.json
```

Other fixed kickoff instants are 2026-10-04 17:00, 20:05 and 20:25 UTC,
2026-10-05 00:20 UTC, and 2026-10-06 00:15 UTC. The single-attempt midpoint
of each permitted window is 75 minutes before kickoff. A missed window is
recorded as missing evidence, never backfilled with a later quote. The local
Windows clock remains unsynchronized; the two-host HTTP Date proof improves
prospective timing evidence but is not cryptographic venue attestation.

Six one-time local Windows tasks named `SportsbetStatOnlyPrelock*` were
registered at those midpoints under the current user's **limited** token.
Their execution times are October 4 at 05:15, 08:45, 11:50, 12:10 and 16:05,
and October 5 at 16:00, in the workstation's Pacific timezone. They request
Windows wake timers but do not elevate privileges, repeat, or run under GitHub
Actions. They still require an interactive logged-in session and AC power; a
powered-off or logged-out PC can miss a window, and a wake request is not a
guarantee. A harmless scheduled-task probe wrote an ignored local marker and
returned success under that same principal. The actual future network requests
have not run. Each task's output and report remain in the ignored private
`.local/` directory,
and its final `LastTaskResult` plus receipt hash must be inspected after the
trigger. Raw player quotes are not tracked in Git.

## Full-denominator no-network audit

`sportsbet.quant.kalshi_stat_only_prelock_series` replays the same pinned
original sources and accepts zero to six repeated `--receipt` paths. It
rejects duplicate, unselected, or future-dated captures and independently
scores every supplied raw receipt. Each missing group stays `not_yet_due`
before its window, `window_open` during it, or `missed_capture` after it. A
missing or invalid market in an observed group also remains in the **70**
candidate denominator. The report never treats a pending group as a zero
price movement. It computes contract and equal-game mean ask movement only
on valid later exact asks, and cannot mark the full observation complete until
all 70 candidates are matched. It still leaves fills, a true closing line,
ROI, CLV, qualified picks and edge unverified.

Use the same `--pair`, `--market`, `--forecast`, `--quotes`, `--decisions`,
`--source-dir` and `--schedule` arguments shown above, omit `--kickoff`, and
pass each ignored `stat-only-prelock-<kickoff>.json` receipt as its own
`--receipt` argument. Set a new exclusive `--output` path under `.local/`.
The initial no-receipt replay on the real pinned files at 2026-10-04
01:53:54 UTC reported **70 `not_yet_due`, 0 observed groups and 0 matched
candidates**, with report SHA-256
`f122a224b02600fa6a0b08fb7fca5c7aa34b9bc2daa7fbab444fd31b5ad9de08`.
No later price was inferred from that dry run.
