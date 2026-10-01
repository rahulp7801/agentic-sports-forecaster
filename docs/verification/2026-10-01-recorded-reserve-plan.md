# Recorded pregame reserve plans

Database connectivity recovered on the October1 UTC follow-up. The failed production jobs for PR273 were rerun without collecting quotes and all seven production CI jobs passed. Frozen prospective audits completed with no invalid receipts and no qualifying paper selections yet; detailed evidence stays private.

The worker already records per-event next_reserve_release_at when preserving staged pregame credits. The public pipeline projection previously dropped these times. A stale scan consequently lost both its explanation and its recorded next opportunity for collection.

Expose a separately labeled recorded budget plan and earliest reserve release. Keep the existing stale/failed/running state and quote freshness unchanged. This is a recorded planning time, not a scheduled execution guarantee, refreshed quote, or qualified pick.

Only bounded, timezone-aware release times with complete matching reserve reasons, unique event IDs, valid count relationships, and release-before-start chronology qualify. Failed, future-dated, contradictory and more-than48-hour-old plans are suppressed. A passed release explicitly awaits a new scan. Internal event identifiers and unknown budget reasons are not exposed.

The worker, quota limits, reserve, model versions and frozen evaluation code are unchanged. No new quote calls, paid services, or bets. Regression tests cover stale-state preservation, elapsed releases, incomplete/duplicate/invalid events, and contradictory scan reports. Browser verification covers mobile/desktop rendering and no overflow.
