# Bounded player archive search

## Verified consumer gap

The public forecast library starts with 36 records and allows loading at most 1,000 rows from the latest 100 stored game snapshots. Player-name filtering previously ran only in the browser. A read-only snapshot found 4,363 NFL forecast rows covering 239 players; 151 players had no records in the first 1,000 rows and were unreachable through that workflow. The independent qualified shortlist was not affected.

## Change

Accept a canonical, bounded player-name substring for the library view only. Parameterized SQL filters the existing latest-100-snapshot archive before pagination. Preserve the 100-row API page limit, 1 MiB page bound, 1,000-row browsing cap, five-second database timeout, input validation and qualification selection. Qualification and candidate requests reject player filters.

Search text is part of the server cache key, snapshot revision and client continuation identity. The client verifies echoed search scope and returned player names. Changing search cancels obsolete requests; only the current request can release the UI loading lock. The player board debounces valid input, keeps search controls available, shows the archive scope, and avoids displaying a prior search's results as a new search. No new forecasts or quote requests are generated.

## Verification

- Node tests validate canonical Unicode names, size/punctuation bounds, qualification isolation, mismatched rows/responses and continuation across a stable search scope.
- The disposable PostgreSQL test places matching records beyond the first 1,000 archive rows, verifies filtered counts and disjoint pages, and checks query-specific revisions and empty results.
- A production read-only transaction returned identical unfiltered output before and after the query change. Exact search recovered 22 rows each for Aaron Rodgers and Baker Mayfield. Observed search-query times were 0.234 to 0.813 seconds; this bounded check is not a load test or capacity claim.
- Local Chromium uses sanitized projections of those retained query results. It verifies previously unreachable-player discovery, replacing a stalled search, empty results, invalid-input rejection without a request, clearing search and mobile width. Screenshots were inspected; no browser application errors or horizontal overflow occurred.
- TypeScript, focused lint and the 19-test forecast/request suites pass locally. Required CI, deployed API pagination and normal live browser search must pass before considering this change deployed.

Private source rows, query fixtures, screenshots and aggregate CFB/team-context research remain local. Models, historical context, probabilities, qualification, settlement, quotas and staged reserve are unchanged. PR #194 remains excluded.
