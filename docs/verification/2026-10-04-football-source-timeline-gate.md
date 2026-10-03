# Current football pick source timeline

The scan already records `history_observed_before` at model selection for
current NFL and CFB forecasts. It also persists the quote time, forecast
write time and game start. The backend forecast ledger checks the football
source time against generation and capture. The consumer projection previously
enforced this timeline only for the NBA source-asof version. A current NFL or
CFB snapshot missing its selection time, or claiming history observed after
the forecast, could therefore pass the frontend qualification check if its
other fields were intact.

The public qualification gate now applies the same chronology to the exact
current version of each sport: version freeze <= source selection time,
quote time <= source selection time <= forecast capture < game start, with
capture no more than one minute ahead of the request clock. A missing or
contradictory source time yields `source_chronology_unavailable`, zero displayed
stake and no qualified pick. The recorded probability is retained for research
and is never recomputed. Existing pre-version research archives keep their
historical display path. The scan producer already writes the source time on
current football signals, so a valid current scan has the evidence needed to
pass this check.

Focused tests cover both NFL and CFB with a valid ordering, missing source,
source before quote, source after forecast, source at kickoff, and missing
forecast capture. A qualified-page fixture retains a coherent source time
when advancing to the exact T-60 board lock. Full frontend: **318 passed**;
TypeScript, changed-file ESLint and optimized Next build passed locally.

This protects the chronology of a consumer suggestion. It does not establish
player-current-form accuracy, a profitable edge, a 75% win rate, a new
qualified pick or a production deployment. No provider request, paid credit,
card, order, wager, model probability, threshold or scheduled capture changed.

## Form card uses the same selection cutoff

The separate player-history panel and pick card previously allowed a current
NFL or CFB model version with a missing `history_observed_before` to substitute
the later forecast-write time when requesting game logs. That could include
records which arrived after model selection, while the card described them as
context behind its prediction. Current versioned NBA, NFL and CFB form now
requires the recorded selection cutoff. If it is missing or contradictory,
the card makes no history request and states that timing evidence is
unavailable. Only older, unversioned archive research may use the forecast
capture as its descriptive fallback. The current scan already writes the
selection time, so valid current cards keep their source-backed recent form.

Focused history/card tests 25/25, full frontend 318/318, TypeScript,
changed-file ESLint and optimized Next build passed locally. The recorded
probability, selected price, injury report, pick gate and research archive
remain unchanged; no provider request or monetary action occurred.
