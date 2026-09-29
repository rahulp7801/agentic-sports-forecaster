# Matched-side model attribution research

This offline experiment asks whether a model-selected side outperforms constant-side controls at the exact same retained game/player/market/line/book/source response. It changes no production model, qualification gate, frozen evaluator, collector, quota, paper recorder or dashboard.

## Research basis

- Walsh and Joshi, [Machine learning for sports betting: should model selection be based on accuracy or calibration?](https://arxiv.org/abs/2303.06021), examines calibration-based model selection using NBA match outcomes. Its findings motivate calibration checks; its results cannot be transferred to our player props.
- Bailey, Borwein, Lopez de Prado and Zhu, [The Probability of Backtest Overfitting](https://www.davidhbailey.com/dhbpapers/backtest-prob.pdf), explains false discoveries from repeated strategy searches. It motivates retaining all attempted rules and avoiding a new claim of untouched confirmation. This module does not implement their PBO estimator.

## Fixed diagnostic

Use the previously committed raw-model and market-prior80 selections, without changing their thresholds or reselection. For each, require an opposite-side price from the identical line, book and source response, received before the original decision, still fresh and pregame. Reject ambiguous prices or contradictory market probabilities. Expose missing matches, pending outcomes and contradictory authenticated outcomes separately.

On paired settled records compare model returns against always-Over, always-Under and half a unit on each side, keeping one unit total exposure. Report paired differences with whole-game bootstrap intervals. Also show return implied by the contemporaneous margin-free market probability and calibration by the model's selected direction. Outcomes never enter quote matching or selection.

Controls inherit model-selected opportunities: this isolates direction choice conditional on the chosen opportunity, not the full selection pipeline. Game clustering does not correct multiple strategy search or repeated players. All historical outcomes have already been inspected. Results are exploratory, private and cannot promote a candidate. Detailed reports, especially CFB/team-context results, must not be published to GitHub.

## Reproduce

`python -m sportsbet.quant.edge_matched_controls --ledger-path PRIVATE_SNAPSHOT.sqlite3 --output PRIVATE_REPORT.json`

Input is read-only. The output includes the input, implementation, selection and source-filter hashes. No network or database writes are required.

## Price-only coverage correction (protocol v2)

The initial diagnostic reused the frozen probability-observation filter for controls. That excludes a first-arriving side with no independent no-vig baseline at its own receipt, even when its source-verified price is available by the later selected decision. Version 2 validates these original price records directly, then requires their combined implied probabilities to reproduce the selected forecast's already-verified baseline. No quote timestamp, source check, selected candidate or frozen probability filter is changed. Original v1 results remain private for traceability.

## Embedded price evidence (protocol v3)

Newer records retain a hash-verified opposite price directly in the original forecast. Version 3 also accepts that existing evidence after reproducing its source hash and no-vig baseline. It labels the leg as embedded price evidence, never a new forecast. The same already-authenticated final statistic settles both sides of a half-line; pending labels stay pending. Conflicts with separate receipts reject the comparison. Version 1 and 2 outputs remain private for traceability. This completes format support without changing the selected cohort or outcomes.
