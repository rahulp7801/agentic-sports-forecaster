# Profile metadata bound to captured athlete identity

## Reproduced failures

Current roster profiles were selected by player name at three public boundaries: embedded signal profiles, paginated forecast enrichment and pick-board enrichment. An individually valid profile for a different ESPN athlete could replace presentation metadata when its player name matched. A source URL and profile hash do not establish that it is the athlete in this forecast.

The profile publisher also indexed `player_image_url` whenever availability returned a valid athlete ID. Availability correctly preserves verified roster IDs without photos; three no-photo or rejected-photo cases therefore raised `KeyError` during profile refresh.

## Changes

All profile projection paths require an exact match with the forecast's validated captured ESPN roster athlete ID. Missing or conflicting identity withholds optional presentation metadata while retaining the forecast and its historical availability evidence. NFL GSIS and NBA.com model IDs are deliberately not compared with ESPN IDs. Current metadata cannot alter historical team context, availability, probability, qualification or stake.

The publisher treats a roster identity without an accepted photo as an unavailable presentation profile. Other players continue through the existing refresh loop and existing last-successful-snapshot behavior remains in place. No extra provider or quote requests are introduced.

## Verification

Before the fix, three frontend integration tests fail across the three projection paths, and three Python cases reproduce the missing-photo exception. After the fix, 59 focused frontend tests and 81 profile/availability tests pass, along with TypeScript and focused lint. Cases cover matching and conflicting identity, missing captured identity, all three supported sports, different model-ID namespaces and unchanged probability/stake fields.

A bounded read-only live check of the first 100 NFL library forecasts found 100 profiles already matching their captured roster identity. This sample does not establish that every retained profile was correct, and no historical misattribution is claimed. After deployment, repeat public projection checks and verify existing valid profiles remain bound. A naturally occurring no-photo roster entry can verify the worker path without triggering a redundant profile collection.

No frozen model/evaluation, qualification threshold, credit limit, pregame reserve or settlement changes are included. Private inputs and evidence files remain local. PR #194 remains excluded.
