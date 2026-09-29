# Free NFL receiving-history evidence collection

`python -m sportsbet.quant.nfl_history_collect --input coverage-input.json --cache .local/nfl-receipts --output .local/nfl-bundles`

The input uses the existing `nfl_history_coverage.audit` schema, including the pinned identity response, primary stat rows and independently committed offensive-participation rows. Collection is restricted to missing primary receiving records detected by that audit. Review existing supplements before selecting the input scope.

## Boundaries

- Free ESPN NFL scoreboard, final summary, event roster and explicit athlete game-stat endpoints only. No credentials, Odds API, billing or betting calls.
- HTTPS allowlist, no redirects, 20-second request timeout, at most 400 requests, 64 missing games and 64 players per invocation. Each decoded response is limited to 2 MB.
- Local receipt cache preserves exact response text, SHA-256 and observation time. Invalid cached commitments fail closed. Dependent roster/stat receipts older than the observed final summary are refreshed. `--offline` permits only retained receipts.
- Exact final regular-season event, GSIS/ESPN/PFR identity, team, game date, season/week, positive offensive participation and explicit full-game receiving categories must pass the existing independent evidence validator.
- Missing categories, ambiguous identity, DNPs and failed retrievals remain unresolved. Offensive participation never implies zero receptions or yards.
- One verified bundle per player, capped by the existing 25 MB import limit. A different retained bundle is never silently overwritten. Partial source receipts remain cached for inspection or a later retry.

## Applying reviewed evidence

Collection writes local artifacts only. Preview each bundle using `sportsbet.quant.nfl_history_supplements`; inspect the exact proposed rows and plan digest before using its existing explicit apply operation. That importer rechecks stored history under locks and requires the reviewed positive count and matching plan SHA-256.

The corrected-history policy makes new evidence available only after both its source observation and database insertion. Historical forecasts and prior shadow inputs are immutable. No qualification thresholds or frozen evaluation protocols are changed. Keep live research artifacts local.
