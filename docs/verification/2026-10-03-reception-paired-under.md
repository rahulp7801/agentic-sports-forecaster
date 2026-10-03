# Paired game check of the advertised reception accuracy

This is a read-only analysis of the **published retrospective fixed 4.5-reception research test**, using the existing at-least-60%-on-the-called-side filter. It changes no model, threshold, pick, stake, frozen evaluator or market receipt. Run:

```powershell
py docs/verification/2026-10-03-reception-paired-under.py
```

| Cohort | Games | Selected calls | Model correct | Always Under correct | Paired model minus Under | Descriptive whole-game bootstrap range |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| 2025 Weeks 1–2 | 26 | 213 | 180 | 181 | -0.47 percentage points | -6.28 to +5.00 pp |
| 2026 Week 1 | 15 | 122 | 100 | 94 | +4.92 percentage points | -0.77 to +10.43 pp |

The 2026 result improves on constant Under on these same selected rows by six calls, but its whole-game resampling range includes zero. Only 12 of 122 selected 2026 calls were Over; nine were correct across eight games. In 2025, 29 of 213 selected calls were Over and 14 were correct across 20 games. The high overall rates therefore mostly reflect selected Under outcomes, and the varying Over result is too thin to support a direction-specific edge. Of the 15 games, the model beat Under in six, tied in seven and trailed in two. The 2025 sample favored Under by one call. This analysis resamples whole games with replacement 50,000 times using seed 20261003 and recomputes the row-weighted paired difference each time. The percentile ranges are descriptive for these selected games and do not correct for trying other research ideas.

These rows have no historical matched sportsbook prices, so this is **not a backtest of accepted picks, profit, closing-line value, or a prospective betting edge**. Correlated player calls within a game do not become independent wagers. The immediate research decision is to keep the existing frozen policy in paper evaluation and await independently recorded post-freeze prices and authenticated settlements. Do not promote this headline accuracy to a user-facing edge claim.

