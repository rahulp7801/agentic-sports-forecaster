# Current-form recency with source-time proof

The consumer history panel and pick-card form previously excluded every game
dated on the day before an early UTC price capture, even if its final stat
record had been received before the forecast. This could make the displayed
30-day and recent-game context older than the evidence actually available.

The date bound is now the target game's exclusive `forecast_cutoff`. Both
consumer requests still include the exact player ID and
`observed_before=captured_at`. The restricted game-log API enforces
`game_date < forecast_cutoff` and `record_available_at <= captured_at`.
The latter is backed by the NBA, NFL, and CFB as-of views. CFB selects the
latest available version so a later receiving correction cannot enter an
earlier forecast. Rows with unknown source receipt do not pass the filter.
The frontend also requires a valid pregame forecast capture before describing
the returned rows. The target game and later games remain excluded.

The existing PostgreSQL as-of tests cover a record immediately before and at
its source receipt for NBA, NFL, and CFB. Focused consumer tests now include a
source-available previous-day game and a missing forecast capture. All 276
frontend tests, lint, and TypeScript pass. This changes descriptive context
only; model probabilities, frozen cohorts, qualification, prices, and API
credit use are unchanged. Historical source corrections whose earlier
version was not retained can still leave a gap rather than an invented stat.

## Live deployment compatibility check, October 3

A read-only check against the deployed Vercel API used an existing NFL forecast's
exact athlete ID, `before` date and captured-at time. The query without
`observed_before` returned HTTP 200; the same URL with that timestamp returned
HTTP 400 `Request rejected.` from the outer proxy. Independent Node
`URLSearchParams` and PowerShell requests agreed. Fixed, no-athlete probes
with the same source-time parameter returned 400 for NFL, NBA and CFB. The
current production deployment therefore cannot serve forecast-time form,
even though the repository's request parser accepts those query shapes. The
private frontend correctly reports form unavailable; dropping the cutoff
would permit later results to masquerade as preforecast context.

The protected release readiness check now requires a successful as-of game-log
request for each league. A regression makes the deployment gate reject a 400
for any of the three, and local proxy/inner-parser tests accept all three
well-formed source-time requests. This is a rollout gate, not a retroactive
repair or a change to model probabilities. Production remains blocked by
zero-step hosted checks, so live as-of context is unverified until that release
runs and all three probes return 200. No provider or paid odds request was made.


## Deployed proxy provenance, October 3 evening

The last successful protected master CI/deploy was [run 36897840787](https://github.com/rahulp7801/agentic-sports-forecaster/actions/runs/36897840787) at 2026-10-01 17:13 UTC, head `2da3103bf2fe2031860a59f427876d3500e70f9b`. That revision's `frontend/lib/publicRequest.ts` did **not** allow `observed_before` on `/api/gamelogs`. Later master `403e241` and the private release do allow it. A fixed, no-athlete production probe on October 3 returned HTTP 200 for `/api/gamelogs?sport=nfl&player_id=00-0000001&exact=1&limit=1&before=2026-10-02`, and HTTP 400 `Request rejected.` with `observed_before=2026-10-01T23%3A00%3A00Z` added. That error string is from the outer proxy. It is consistent with the last deployed allowlist, not a game-log database failure.

The private post-deploy readiness list already requires HTTP 200 for fixed as-of probes in NBA, NFL and CFB. The next action is a protected deployment followed by those real probes; deleting `observed_before` from the consumer request would discard the capture-time boundary. Until the release passes hosted CI and branch protection, the live form panel correctly reports unavailable. No paid source call or scan was made for this diagnosis.

## NFL current-team abbreviation correction, October 4

The recorded NFL availability roster uses `LAR` and `WSH`; the verified
stat-history source uses `LA` and `WAS` for those same franchises. The model's
existing `STAT_TEAM_ALIASES` already maps these two pairs, but the consumer
30-day form grouped games by literal abbreviation. It could therefore say no
captured-team game was present for a Rams or Washington player even when an
exact-player, source-available game existed.

The descriptive history grouping now applies only those two documented NFL
aliases when comparing the captured roster team with each recorded team. It
keeps the original team labels in the history table, excludes other franchises
such as `LAC`, and still requires exact athlete ID, target-date cutoff,
source availability by forecast capture, and verified roster identity.
Model probabilities, teammate adjustments, qualification, and collection are
unchanged. The focused history/card tests passed 19/19; the full frontend
suite passed 292/292, TypeScript, targeted ESLint, and production build passed.
Production remains on the older deployment until the protected release runs.
