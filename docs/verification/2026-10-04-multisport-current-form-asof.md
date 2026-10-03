# Model-selection-time current form across sports

The scanner already passed a point-in-time history cutoff into NFL and CFB
model queries and retained that timestamp in new-version immutable
forecasts. The public signal and pick-board projections omitted it, so
descriptive game-log requests used the later forecast write time.
A source row arriving during inference could therefore appear in the
consumer's recent-form explanation even though it had not informed the
recorded probability.

New NFL and CFB signals and accepted pick-board records now retain that
existing cutoff only when their exact version and policy match. The
browser preserves it and requests game logs as of model selection for
those records, as it does for the new NBA version. The evidence panel
identifies whether it has a model-selection cutoff or the older
forecast-capture fallback. Older football boards that never retained
the cutoff remain readable with their original forecast-capture window.
A malformed or later-than-capture cutoff cannot produce a current-form
claim. The old v4 population cannot acquire a new source cutoff through
publication.

No model input, probability, recommendation eligibility, quote, source
collection, frozen evaluator, API credit, bet, cap or reserve changed.
This makes the descriptive context faithful to the actual model timing.
It does not demonstrate prediction accuracy, a profitable edge, or a
75% win rate. Local focused board/scan tests and browser projection,
history and card tests cover NFL/CFB source-time retention and legacy
fallback. Production still requires protected CI, deployment, fresh
scan receipts, and matching-price prospective outcomes.

Local verification on the combined private patch: 2,029 backend tests passed,
72 skipped (including optional disposable PostgreSQL tests); 302 frontend
tests passed; changed-file ESLint and the production Next.js build passed.
Focused new tests cover both football sports' signal projection, accepted
board cutoff retention, current-form request, and historical fallback.
## Public player-profile source-time correction, October 4

A read-only live NFL pick-board response exposed a later-profile attachment to
an older forecast. The historical Kenneth Walker III record
`c06ae5f692363a518909ba6a25e769bdb586a14104cf4fdc5781f72baf76c937`
was forecast-captured on **September 26 01:24:24 UTC** for a September 27
17:00 UTC game. Its returned player profile said **October 3 14:49:23 UTC**,
even though the pick board itself said it was generated October 3 12:40:25 UTC.
A bounded read-only audit at 06:32 UTC found **5/8** NFL history rows with
attached profiles, all five captured after both forecast and board generation;
all **100/100** profiles on the first NFL research archive page were later than
their forecasts. The sampled CFB history (2 rows) and NBA history (0 rows) had
no attached profiles. No availability or tracking timestamp on those sampled
pick rows postdated its forecast. Replaying the exact live NFL responses through
the corrected private projection retained all 8 history rows, their recorded
probabilities and results, and all 100 research rows and probabilities, while
removing all 5 and 100 late profiles respectively. This bounds the observed
problem; it does not certify every archived page.

The display helper already rejected that profile for captured context, but the
public API still attached it to the historical record. A consumer or downstream
client could mistake this later roster/profile snapshot for pregame evidence.

The private projection now requires a profile's source capture to be no later
than the forecast capture, with the exact captured roster athlete and team.
This applies to embedded profiles, pick-board enrichment, and paged research
forecasts. A valid historical profile is checked relative to forecast time, so
it remains usable when the archive is viewed more than 14 days later. Missing
or late profile evidence stays absent; the recorded probability, availability,
settled result, qualification gates, and source cutoff do not change. The live
API still serves the earlier release until protected CI and deployment run.