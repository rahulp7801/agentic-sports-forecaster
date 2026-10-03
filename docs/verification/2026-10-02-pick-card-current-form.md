# Current-team form on pick and recorded-lean cards

The consumer card now reads the existing public as-of game-log view for the exact captured player ID. It uses the same one-day game cutoff, forecast capture timestamp, 20-row bound, and 30-day current-team window as the evidence panel. The roster team must have been confirmed at capture. A later player profile cannot substitute for that team. The card reports observed stat count, available-game count, mean, line, latest date, and the 20-row limit when relevant. Missing or invalid source history yields an unavailable message, never a zero or inferred hit rate.

At most three suggested picks or three recorded leans render these cards. The read uses the existing cached `/api/gamelogs` endpoint, no paid provider or additional quote collection, and its dependency key stays fixed across the dashboard's five-second clock rerenders. This is descriptive context only; it changes no model probability, qualification threshold, stake, archived forecast, or edge assessment.

Verification: exact-player and cutoff tests, missing and cross-team history tests, the full frontend test suite, lint, TypeScript, and production build. After deployment, inspect a card with retained as-of rows and a card without them on desktop and mobile, and compare the card to its evidence panel. No positive betting edge is implied by this display change.
