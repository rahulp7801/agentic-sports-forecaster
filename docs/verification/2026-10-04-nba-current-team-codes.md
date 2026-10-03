# NBA current-team form across ESPN and NBA abbreviations

The captured injury/roster source uses ESPN's NBA team abbreviation. The
historical game-log view contains official NBA abbreviations, including
ESPN supplemental rows mapped by the exact team crosswalk. The consumer
current-form matcher compared these two codes literally. That made some
players' recorded games appear to be from another team and could state
that no current-team game was present in the last 30 days.

A read-only comparison of the free official ESPN team directory and the
installed NBA team directory on 2026-10-04 found 30 teams in each, with
six abbreviation differences:

ESPN roster -> NBA game log
GS -> GSW
NO -> NOP
NY -> NYK
SA -> SAS
UTAH -> UTA
WSH -> WAS

The LA Clippers name differs between the directories but its LAC code
matches. The consumer matcher now maps only those six NBA aliases before
comparing an exact player-ID game log to the captured roster team. The
existing NFL LAR/WSH aliases remain sport-specific; CFB codes are not
rewritten. Current form remains descriptive, bounded to source records
available by the forecast's recorded time, and never changes a model
probability or qualification gate.

Official sources:
- https://site.api.espn.com/apis/site/v2/sports/basketball/nba/teams
- https://www.nba.com/teams

No paid API, quote collection, source ingestion, model cohort or frozen
evaluation changed. Focused tests cover every discrepant NBA abbreviation,
exclude a different team and player ID, and keep CFB's identical-looking
code separate. Protected deployment and a live NBA player with a recent
verified game are still needed to confirm consumer rendering.

Local verification: all 304 frontend tests pass, including 25 adjacent
current-form tests; TypeScript, changed-file ESLint and the production
Next.js build pass. The backend code is unchanged from the prior
2,029-passing full backend run (72 optional skips). This patch remains
private and unmerged until hosted CI and protected deployment can run.
