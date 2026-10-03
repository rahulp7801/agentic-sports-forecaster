# Current game-log explorer freshness

The public game-log API used the archive CDN policy for every request: 15
minutes fresh plus up to 60 minutes stale during revalidation. An unbounded
player search in the consumer explorer could therefore keep a newly ingested
game out of the visible recent-form sample for over an hour even after the
database had it.

Requests without `observed_before` now use the research cache (five minutes
fresh plus five minutes stale). A valid past `observed_before` keeps the
archive policy because it replays the player history available at an older
forecast cutoff; a future cutoff also uses the shorter policy. The browser
still bypasses its own cache. The explorer labels when its response was
loaded and explains that source publication can lag. Its existing Refresh
button requests again, subject to the bounded CDN policy.

This changes delivery freshness only. It does not backfill a missing source
row, alter a model input or probability, change a pick gate, fetch paid odds,
place a bet or establish an edge. The cache-policy boundary test and full
frontend suite pass **317/317**; changed-file ESLint, TypeScript and the
production Next build pass. Protected CI and deployment remain necessary
before the live consumer sees this behavior.
