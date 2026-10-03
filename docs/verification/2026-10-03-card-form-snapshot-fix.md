# Pick-card current-form snapshot repair

The previous current-form recency change made `forecastHistory` require a
valid forecast capture and future game start. The card hook intentionally
passed a small, stable forecast snapshot to avoid fetching history again on
every clock rerender, but that snapshot omitted both timestamps. As a result,
the card formatter would throw and display “Recorded current-team form is
unavailable” even when its as-of game-log query returned valid rows.

The hook now uses one stable, serialized `pickCardFormSnapshot` shared with
the formatter. It retains exact player identity, forecast cutoff, quote time,
forecast capture, game start, target line/direction, and the captured roster
team and time. Its key changes when any of those inputs change, while ordinary
clock rerenders reuse the result. The calendar form separately requires that
the roster capture precede the forecast before naming a current-team cohort.
The card makes no history request if that roster chronology fails.

Focused tests pass for a previous-day as-of row through the same snapshot
shape used by the hook, and reject missing forecast capture and later roster
capture. The historical query still enforces exact athlete ID, exclusive
target game date, and source receipt by forecast capture. No provider request,
odds collection, model, probability, qualification threshold, or API limit
changes. Production rendering remains unverified until the protected release
can deploy.

The consumer card now states how many calendar days its newest **observed
stat** precedes the target game. A more recent recorded game with a missing
stat is disclosed separately; it cannot make an older value look current.
When the latest observed stat is more than 14 days old, or no stat is observed,
the card says this does not establish current form. The detailed history panel
likewise separates its latest recorded game from its latest observed stat.
This is a presentation warning; it does not change the as-of query, model
estimate, eligibility, or risk gates. Tests cover the 14/15-day boundary,
the 23-day-old observation, and a recent game with a missing stat followed
by a 22-day-old observed value.
