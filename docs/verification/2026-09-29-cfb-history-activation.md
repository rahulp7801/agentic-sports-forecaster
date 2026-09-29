# CFB effective-history activation

PR #245 continues the staged supplement release. Source bodies and aggregate research reports remain private.

## Production changes

- CFB prop queries read `cfb_effective_gamelogs`; a bound aware timestamp excludes source receipts and supplement inserts after model input capture. Date and sample filters remain unchanged.
- Migration 0032 directs the CFB dashboard history projection to the same effective rows. Restricted raw-source access and dashboard SELECT-only access remain intact. Downgrade restores the primary projection.
- Composite settlement proofs retain the supplement manifest and reproduce original and effective stat hashes, primary asset commitments, exact source identities and receipt chronology.
- New CFB forecasts use `empirical-jeffreys-v4-cfb-history-v1`, input policy `cfb-explicit-receiving-v1`, and retain `history_observed_before`. NBA/NFL remain v4. Previously recorded picks remain readable across deployment overlap.
- `sportsbet.quant.cfb_history_edge` freezes a separate CFB cohort beginning 2026-09-29 04:15 UTC. The prior multisport and shadow protocols are untouched. Confidence gates and evidence minimums are unchanged; this release does not establish an edge.

## Release gates

Focused backend and consumer regressions, real PostgreSQL migration/view/settlement checks, full CI, hosted schema/access/readiness verification, and read-only production checks are required before deployment is claimed. Do not reapply already-staged supplements or trigger paid quote collection for verification.

## Next evidence checkpoint

After deployment, verify primary and forecast payload commitments remain unchanged, model/public history agree, composite manifests validate, and the new prospective cohort excludes prior forecasts. Inspect the next natural scheduled scan for the new model and history cutoff. Inspect free history refresh and authenticated outcomes after 2026-09-29 10:45 UTC; keep all research reports local.

No money, new credits, bets, quota increases or staged-reserve changes are authorized. PR #194 remains excluded.
