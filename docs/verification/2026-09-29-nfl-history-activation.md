# Corrected NFL receiving history activation

New model: `empirical-jeffreys-v4-nfl-history-v1`. Input policy: `nfl-explicit-receiving-v1`. Prospective cutoff: `2026-09-29T05:45:00+00:00`.

Production NFL receiving queries with a source cutoff use the effective history view; prior games, last-40 selection, empirical Jeffreys probability and all qualification thresholds are preserved. Passing and rushing remain primary-source inputs. Both observation and insertion must precede the prediction cutoff. The restricted consumer history projection uses the same records. Passing and rushing outcomes in recovered receiving rows remain unknown.

A matching primary row takes precedence without duplication. Conflicting primary receiving values block effective history for that player pending review. Supplemental games require their exact stored schedule identity. Settlements retain and reproduce the composite source manifest, stat digest, exact game and participation proof.

Historical v4 predictions remain unchanged and valid as retained records. The new cohort has a separate frozen prospective evaluator with the existing 50 paired games, 100 decided recommendations and 30 recommendation games evidence minimums. It never auto-promotes. The original workload and role experiments reject the new baseline as unsupported; their source, implementation and retained results remain unchanged. A future role experiment against the corrected baseline requires a new protocol.

No new collection, paid requests, threshold changes, budget changes, or performance claims are introduced.
