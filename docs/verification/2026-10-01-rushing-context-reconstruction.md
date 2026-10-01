# NFL rushing paper-context reconstruction

The read-only `individual-rushing-context-audit-v1` module inspects **original** NFL raw-model paper selections in the rushing-yards market. It authenticates the immutable paper receipt and matching price with the frozen verifier before showing a diagnostic. It never selects a later quote or promotes a pick.

For each selection, the retained source snapshot must predate the forecast's history cutoff. Every game row must have a source commitment and an observation time no later than that cutoff. The reconstructed baseline must exactly match the recorded model sample size, mean, and probability. The roster must have been observed before capture, and the latest source game must have a unique date and match the roster team. Ambiguous binding, duplicate games, insufficient samples, stale rosters, and later sources leave context unavailable.

The report shows last-ten and current-season hit counts and carries as **descriptive diagnostics**. It explicitly marks the rushing history as reconstructed and participation completeness as unverified. No original rushing input bundle was committed with these forecasts, so the reconstruction cannot certify a current-role probability. A pending or unauthenticated result never enters decided coverage. This is not a preregistered accuracy study or evidence that the system achieves a 75% individual-pick win rate.

Private retained paper inputs and source snapshots may be passed to `audit(receipts, predictions, snapshot, now)` in an offline read-only run; generated reports remain private. Future scans need prospective source-backed rushing participation receipts before a rushing-role model can be evaluated or deployed. The receiving shadow and frozen paper selector are unchanged.
