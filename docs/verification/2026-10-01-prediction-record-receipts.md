# Database-owned recording evidence for future forecasts

Migration 0039 stamps each new analytics.predictions row with the database clock
and a SHA-256 commitment to its original payload. Supplied timestamps and hashes
are overwritten. The prediction ID, scan ID, payload, timestamp, and digest
cannot be changed by an ordinary UPDATE; authenticated outcome fields remain
updatable for settlement. The restricted worker has no DELETE grant, while
administrators can remove synthetic or erroneous rows during maintenance. The existing scanner and frozen evaluators are
unchanged. This migration makes no provider request and changes no pick gate,
probability, quota, or pregame reserve.

Legacy rows retain NULL recording fields. A migration-time timestamp would
falsely imply those forecasts existed at their old claimed capture time. The
new fields support later prospective evidence review; they do not by
themselves prove a forecast preceded kickoff. Review must compare the database
recorded_at to the actual game start and keep the source quote, paper receipt,
and authenticated settlement checks. Do not count legacy NULL rows as
prospectively timestamped.

Disposable PostgreSQL tests verify legacy NULLs, server-owned insert stamps,
payload digest, source-record immutability, denied worker deletion, and allowed outcome-only updates.
Production schema must be migrated before any worker using this head starts.

The existing PostgreSQL recovery test no longer fabricates a changed source
payload through an ordinary UPDATE: the database now rejects that setup.
The migration test checks this rejection directly; recovery still tests
outcome and authenticated final-stat conflicts.
