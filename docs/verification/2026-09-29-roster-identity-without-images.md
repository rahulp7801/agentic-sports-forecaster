# Roster identity independent of player images

## Reproduced failures

Availability evidence populated an NFL athlete ID through the portrait map. A player with a verified, uniquely matched roster ID and crosswalk could therefore become unavailable to the frozen recent-role candidate solely because an optional headshot was missing.

The public projection also returned an athlete ID only alongside an exact image URL. For a CFB name alias without a photo, a second projection then lost the required history-to-roster identity and withheld availability.

## Change and boundaries

Derive the optional ESPN athlete ID from a unique exact roster-name/ID binding with the expected sport-specific roster URL and SHA-256 commitment. Keep the ID when the photo is absent. Missing, null or malformed optional photo metadata cannot make the entire roster response unavailable. If a portrait points to another athlete, omit the image and retain the roster-bound identity. Public projection independently validates numeric IDs and exact ESPN image URLs.

Existing roster freshness, subject and teammate gates, probability estimates and stake thresholds remain unchanged. This repairs the input producer; the frozen recent-role model, source artifact, receipt verifier and evaluator remain unchanged. No historical captures are recreated and no missing image is synthesized or fetched. No paid collection, budget, reserve or workflow changes; PR #194 remains excluded.

## Verification

Tests reproduce both failures before the change. Mocked provider-to-availability tests cover all three sports with and without images. Candidate tests pass the actual produced evidence into the unchanged recent-role verifier. Ambiguous IDs, unknown names, invalid commitments and conflicting portraits are covered. Public tests enforce image allowlists, ID namespaces and round-trip identity preservation.

A local projection audit checks existing snapshots for unchanged forecast values, current gates and repeat projection. It found no historical output changes in the audited snapshot; this repair is not claimed to recover historical candidate captures. Live artifacts remain local.

At the next natural capture, verify roster IDs in availability and candidate receipt coverage regardless of photo availability. Do not collect new paid quotes or alter frozen cohorts for this check.
