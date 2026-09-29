# Forecast history identity and recent form

## Consumer behavior

Each forecast history panel compares the latest five available games before its conservative historical cutoff with the preceding five. Both windows show observed and missing statistics, date ranges, teams, and direction matches excluding ties. Missing observations remain in their original windows. An explicit warning appears when the newest recorded game is more than 30 days before the target game.

This is descriptive context at the recorded line. It does not adjust the forecast probability, change qualification, or establish a betting edge. The window can cross seasons and teams. Available records are not a participation census, and later source corrections can appear. Existing source timing and pregame cutoff safeguards remain in effect.

## Identity and access boundary

Migration 0030 appends the sport-specific player ID to the sanitized dashboard game-log view and its payload. NBA and CFB use positive numeric IDs; NFL uses GSIS IDs, distinct from ESPN portrait IDs. Requests use bound SQL parameters and bounded, validated IDs. Exact ID lookup takes precedence over the display name so provider name changes do not split one athlete's history and namesakes cannot be combined.

The view retains its security barrier, dashboard SELECT grant, and denial of PUBLIC, anonymous, and authenticated access. No base-table permissions are broadened. Downgrade recreates the previous view without CASCADE and reapplies its access controls. Deploy schema before frontend code.

Forecasts with no valid stable identity cannot infer one from identified name matches. Older name-only records remain supported only when neither side has a stable ID. Frozen forecast records and evaluation versions are unchanged.

## Verification

- All 200 frontend tests pass, including namesakes, renamed players, malformed IDs, missing statistics, disjoint windows, small samples, and offseason gaps.
- TypeScript compilation passes.
- PostgreSQL integration test covers all three sports, identity filtering, row preservation, security-barrier and public ACL checks, downgrade, and re-upgrade; exercised by the CI PostgreSQL gate.
- Release also requires lint, production build, full CI, schema migration, and deployed desktop/mobile verification.
