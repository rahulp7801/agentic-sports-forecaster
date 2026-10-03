# Public prediction market snapshot expiry

Kalshi game and Polymarket event research previously retained a provider
snapshot in the server cache, CDN, and open browser tab. Even after an event's
reported start time, its old bid, ask and displayed liquidity could remain
beside text describing open markets. Neither researcher creates a model pick,
and the captured `observed_at` timestamp remains visible for context.

The API now projects cached listings against request time and excludes events
at or after their reported start. Polymarket detail returns 410 without a
cached quote once the event starts. The CDN fresh and stale lifetimes end
before the earliest event boundary. The two open researcher tabs recheck their
already loaded listings every five seconds and on focus/visibility change;
started events and their prices disappear without another provider request.
The selected detail must still match its selected event identity.

This is an expiry rule for consumer research snapshots, not a new odds read,
verified fill, closing price, qualified pick or edge. It does not change the
fixed prelock collection schedule, paid Odds API usage, cap, reserve, model,
probability or frozen prospective cohorts. Exact-start and CDN-boundary tests
pass; the full frontend suite passes **316/316**, changed-file ESLint and
TypeScript pass, and the production Next build passes. Production behavior
still requires the protected release to pass hosted CI and deploy.
