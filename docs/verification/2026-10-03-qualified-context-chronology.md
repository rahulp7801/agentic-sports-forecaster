# Qualified context must precede the forecast

The public forecast sanitizer previously accepted an observed roster when the
forecast had no valid `captured_at`. A fresh saved price and that roster could
therefore survive the consumer availability gate without proof that the roster
was known before inference. It also tolerated an individual injury report up
to 60 seconds after the roster capture, even though the producer requires each
report date to be no later than its capture. A future-dated questionable
opponent report could appear as captured context without blocking the pick.

Observed availability now requires a valid forecast capture between quote
capture and game start, with roster capture no later than the forecast. Every
individual report must be dated no later than its roster capture. Invalid
chronology withholds observed availability and gates the suggestion as
`availability_unavailable`; the retained model probability is not changed.
Research records remain available with their source status. The normal worker
already records the required times, so this enforces its source contract at
the consumer boundary. It does not relax the qualification threshold or add
a probability adjustment for recent form, injuries, or teammates.

The new regressions check the sanitizer and the actual suggested-pick
shortlist for missing forecast capture and future teammate reports. Existing
fixtures representing valid forecasts now include their actual capture time.
Verification: focused chronology/shortlist tests pass; full frontend suite
275 tests passes, lint and TypeScript pass, and the optimized Next.js build
succeeds. No provider request, paid credit, bet, model promotion, or market
edge claim follows from this change. Hosted CI and production rollout still
require the protected private PR gates.
