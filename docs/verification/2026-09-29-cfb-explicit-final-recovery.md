# Explicit CFB final-result recovery

## Problem

The regular CFB box-score release can omit an athlete's receiving category even when the athlete appears in rushing statistics. Missing category rows are not observed zeroes. Treating omission as zero would change results and historical inputs without evidence.

## Evidence contract

A manually archived version-1 bundle identifies exact ESPN athlete and event IDs and retains UTF-8 response text, source URL, observation time, and SHA-256 for each response. The parser accepts only the fixed public CFB summary and athlete game-log URLs for those identities.

The final summary must establish a completed regular-season event, unique home/away teams, season/week, kickoff time, and Eastern slate date. The athlete game log must be observed after that final summary and match event ID, kickoff, teams, scores, season, week, and league. Named stat columns must be unique and complete. Receiving values must be explicit integer strings; zero receptions with nonzero yards is rejected.

A separate final box-score rushing or receiving entry must identify the same athlete and team and show positive offensive activity, with its count and yards matching the athlete game log. Roster membership, a missing category, a missing game, or unconfirmed participation cannot establish a result or automatic void. Conflicting sources fail closed.

## Recovery boundary

`python -m sportsbet.quant.cfb_final_recovery --bundle PATH` previews unresolved exact receiving selections using a read-only database snapshot. It performs no network collection. Application requires `--apply --expected-count N` with a positive reviewed count.

The atomic writer locks all affected predictions, verifies unchanged payloads and unresolved outcomes, checks for conflicting primary statistics, reproduces the existing settlement-proof contract, and verifies the write count. It preserves immutable forecasts, accepted flags, prices, model versions, and prior outcomes. It does not update historical game logs or change the production probability model. Existing NFL recovery retains its default sport behavior; mixed-sport plans are rejected before database access.

## Verification and release

Tests cover explicit zeroes, midnight UTC/Eastern identity, original-side settlement, contradictory or malformed evidence, missing participation, duplicate identities, stale/future receipts, immutable forecast preservation, and replay rejection. Disposable PostgreSQL integration exercises the locked update and retained proof. Release requires all CI gates before a reviewed bundle can be applied.

A wider historical completeness audit is still needed before supplementing model inputs. This recovery path does not assume that observed-category history is a complete participation census and does not establish predictive edge.
