# Consumer request recovery and mobile navigation

## Reproduced failures

Past results offered no retry after a failed request, and a stalled response could leave results loading indefinitely. Player history likewise lacked a retry action. On narrow screens, seven navigation entries occupied a five-column, fixed-height dock, pushing the final entries outside the visible bar.

## Changes

Results and history expose explicit refresh/retry controls with a 15-second request timeout. Component cleanup cancels obsolete requests. A failed results refresh retains the previously loaded board with a visible warning and publication timestamp. The parent components already remount on league or selected-forecast changes, keeping previously loaded evidence bound to its original identity and cutoff.

NFL/NBA mobile navigation retains four main views plus More tools; Markets and Backtesting move into that menu alongside Game logs and Stake calculator. CFB retains its five supported main views. Desktop navigation remains unchanged. No collection, model, probability, evaluation, settlement or qualification rules change.

The README is aligned with deployed NBA/NFL/CFB collection, frozen model versions, 20 daily / 450 rolling credit ceilings and the staged reserve. It distinguishes initial database backfill from routine production refresh and prohibits redundant collection or activating billing.

## Verification protocol

Use installed headless Chromium against the local application and unchanged responses from the public read-only APIs. Intercept requests only inside the test browser to reproduce a 503 or a stalled response; no provider requests or production mutations are involved.

- Results: desktop and mobile initial failure, retry success, failed refresh retaining rows, retry recovery, bounded stalled-response timeout and unchanged results.
- Player history: initial failure and retry, exact-player pre-forecast history, Last 10 / Last 20 controls and mobile layout.
- Navigation: 320/390-pixel NBA/NFL layouts and 390-pixel CFB layout; five visible dock entries within the viewport; More tools navigation and menu closure; desktop 1440-pixel navigation without duplicate visible entries.
- Inspect screenshots, check horizontal overflow and browser runtime errors, then repeat the consumer checks after production deployment.

TypeScript and focused component lint checks are required locally, followed by normal repository CI before merge. Local screenshots and response fixtures remain private. Development tooling can add a footer outside the application shell; production viewport dimensions are checked separately.

## Remaining evidence checkpoints

Request recovery does not establish forecast profitability. Frozen prospective comparisons still require their minimum independent game evidence and matching market prices. Missing source participation data must remain unavailable until the provider publishes it. Continue natural scheduled collection without extra quote requests or weakened thresholds. PR #194 remains excluded.
