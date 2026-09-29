# Settlement cache model boundaries

## Reproduced failure

NFL receiving settlement selects the primary stat table for older forecasts and the effective receiving view for the current NFL model. The per-run cache previously keyed only game, teams, player and prop. A result or a missing row could therefore be reused across frozen model versions. Depending on forecast order, this could resolve a forecast from the other version's evidence source or suppress an otherwise resolvable result.

## Fix

Include the retained model version in the settlement stat cache key. Repeated price captures from the same model still share one source lookup. Source authentication, final-game identity, evidence proofs, forecast values, qualification rules and frozen model/evaluation implementations are unchanged. No quote collection, API quota, reserve or workflow change is included. PR #194 remains excluded.

## Verification

Eight regression cases fail before the fix and pass after it. They use actual primary/effective SQL lookups with both receiving props, both forecast orders and each possible missing source. Existing duplicate-price batching remains covered. All 51 settlement tests pass locally; required repository CI must pass before merge.

Inspect the retained production ledger read-only for model-version coverage before claiming historical impact. Do not rewrite outcomes or forecasts merely because this cache defect existed. Live evidence and aggregate research artifacts remain local.
