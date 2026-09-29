# Exact participant identity for NFL availability context

## Reproduced failure

Historical teammate/opponent participation context inverted the current roster's ID-to-name map into a name-to-ID dictionary. When two IDs shared a name, iteration order silently selected one participant. A partial ESPN-to-PFR crosswalk could also turn the same ambiguous roster into either a comparison or no comparison depending on order.

## Change

Require exactly one current roster ID matching the reported player's name before resolving its PFR identity. Ambiguous names never reach historical SQL. Continue to show the reported injury and apply the existing acute-teammate baseline gate; withholding an unverified historical comparison must not hide the risk or qualify a pick. Other uniquely identified participants remain available.

This changes descriptive context identity resolution only. It does not change frozen prediction or evaluation implementations, probabilities, qualification thresholds, API allowances or collection. Existing forecasts and their captured context are not rewritten. PR #194 remains excluded.

## Verification

Seven regression cases cover both roster orders, a partial or complete crosswalk, unaffected unique teammates, retained injury gating and rejection before any history query. Before the fix, five cases fail and two happen to pass due to ordering. After the fix, all pass. The focused context, availability and frozen-role suites pass all 141 tests locally; required repository CI must pass before merge.

Historical impact is not inferred from names in published summaries, which do not retain the full roster-to-participant resolution. At the next natural capture, verify context comparisons are linked only through unique roster identities. No new quote collection is needed for deployment verification.
