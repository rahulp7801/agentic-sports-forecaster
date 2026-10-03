# Optional participation context cannot erase an event scan

The scanner first screens the complete captured injury-report set for acute
offensive teammate absences and retains that gate with each forecast. It then
runs historical participation comparisons for consumer explanation. Previously,
an exception from that later optional query could abort the entire event, so
no forecast or gate was retained despite a completed model and market quote.
Several sequential comparisons could also consume the remaining quote or
availability freshness window.

The descriptive comparison now has an eight-second total timeout per first
player/line explanation. An exception or timeout logs
`historical_context_unavailable` with its exception type and leaves
`context_splits` absent. The report evidence and full acute-teammate gate stay
in place. Admission still rechecks game start, T-60 lock, quote age and
availability age after this work, including the database reservation check.
The public panel states that a supported participation comparison is
unavailable; it does not invent an absent or active cohort.

All scanner-focused and injury-context modules pass **96 tests**, including
exception, timeout, and Out-teammate cases in NFL and NBA. This change makes
an already computed forecast durable when optional descriptive context fails;
it does not adjust a model probability, remove injury screening, increase API
use, establish an edge, or create a qualified pick from stale evidence.
