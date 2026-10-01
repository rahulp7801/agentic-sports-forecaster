# Snapshot cache expiry

## Failure reproduced

The installed Next.js 16.3.6 `unstable_cache` implementation returns a stale
App Router entry while refreshing in the background, including when that refresh
fails. A local isolated reproduction seeded an old successful snapshot, failed
the loader, and received the old success. The route therefore could not expose
its existing unavailable response. This is a failure-mode reproduction, not a
claim of a current production database outage.

## Change

Public snapshot reads use the existing bounded read cache with a hard 60-second
server lifetime. Expired reads wait for a successful database refresh; refresh
errors propagate and are not cached. Concurrent misses share work. Batch reads
stay one database query and use canonical copied keys. Return values are cloned.
Single reads and batches have separate cache identities.

Limits per process: 64 entries, 16 MiB total serialized size, 4 MiB per entry,
18 distinct pending reads. Oversized responses are returned without storage.
Local non-hosted reads keep bypassing the cache. Routes retain their current
error/no-store handling and Vercel CDN policies.

This bounds the server cache age, not the underlying worker publication age or
end-to-end CDN lifetime. Existing timestamp validation and stale UI states still
apply. Unlike the former persistent Next cache, sharing is per process, so cold
instances may make additional read-only database queries. No new data collection,
provider requests, database writes, or model/evaluation changes are introduced.

## Verification

- Reproduced the old stale-success behavior using the installed Next runtime.
- Five new regression tests cover exact-boundary expiry, shared failures,
  immediate recovery, foreground waiting, return-value isolation, consistent
  batches, caller-key mutation, sport/key separation, and missing publications.
- Existing cache tests cover memory/LRU bounds, oversized values and concurrency.
- All 245 frontend tests and the production build passed locally.
- Required exact-head CI, security checks and production verification must pass
  before this is treated as deployed.
