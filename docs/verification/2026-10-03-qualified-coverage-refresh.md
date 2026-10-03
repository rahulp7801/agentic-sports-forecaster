# Qualified coverage and research refresh, October 3

The client previously treated a legacy forecast response with no pagination
metadata as complete, even for the qualified view. That response did not prove
that the whole eligible snapshot window was checked. The qualified fetch now
requires an explicit pagination receipt; a missing receipt fails the current
check, so the dashboard withholds suggestions. The research archive retains
its rolling-deployment compatibility.

The overview also cleared a failed qualified or watchlist refresh but retained
research cards when the full history refresh failed. It now clears those cards,
their count, and pagination state on failure. The error notice stays visible.
The overview already remounts per sport in `TerminalApp`; no league-switch
change was needed.

Verification: all 276 frontend tests pass, including a missing-coverage
regression; eslint and TypeScript pass; the production frontend build passes.
No forecast model, qualification threshold, source collection, API quota,
payment, or bet changed. The release remains unmerged until hosted required
checks can run. These safeguards do not establish a prospective edge.
