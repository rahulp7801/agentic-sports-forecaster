# Exact ESPN Utah identity for NBA profile metadata

## Supported input and reproduced defect

The [official ESPN Utah team endpoint](https://site.api.espn.com/apis/site/v2/sports/basketball/nba/teams/26)
was read once at `2026-10-19T19:52:19.223169+00:00`. It returned team ID `26`,
display name `Utah Jazz` and abbreviation `UTAH`. The bounded 20,063-byte response
had SHA-256 `1493560fea5e6136f08855831b8d3bd388d12761f771000952f0c2532d1a4476`.
Only the public team identity fields, byte count and hash were retained locally;
the raw response was not saved. This was one free team-metadata request, with no
market quote collection or API-credit use.

The schedule producer preserves ESPN abbreviations. The profile consumer
previously required every slate abbreviation to match `[A-Z]{2,3}`, before
filtering irrelevant or completed events. A legitimate `UTAH` entry therefore
rejected the entire profile input, including other valid joined games.

Synthetic regressions reproduce this for home/away Utah and for a Utah game
unrelated to the joined player. The source identity and existing roster consumer
use the raw `UTAH` abbreviation; changing it to a normalized `UTA`
would break the exact captured-team comparison.

## Narrow correction

Accept the additional pair only when the sport is NBA, the abbreviation is
exactly `UTAH`, and the corresponding captured team name is exactly `Utah Jazz`.
Preserve the original slate, raw abbreviation/name pair, source clocks, hashes,
target UUIDs and team joins. No roster fetch, quote request or source replay is
added. Wrong names, sports or case, arbitrary four-letter abbreviations,
malformed identities and ambiguous team/event joins remain rejected.

The statistics-provider alias helper and historical rows are not changed by
this presentation-metadata fix. They require their own provider mapping evidence.
No model, forecast, qualification threshold, source chronology or frozen study
version changes.

## Live evidence limits

Scheduled [run 39311125860](https://github.com/rahulp7801/agentic-sports-forecaster/actions/runs/39311125860)
was an actual `public_daily` selected from cron `37 13 * * *`. Its NBA profile
input was rejected at `event/identity`. That category also covers other event
fields, and the exact failed field/slate bytes were not retained in the log.
The supported-input defect is independently verified; this does not identify
the actual run's rejection cause.

The same run reported failed NFL/NBA histories, blocked settlements, an NFL
profile timeout, and failed main/CFB database receipt reads (`08006`). Its four
validated producer receipts are not four independently verified database
receipts. The UI verifier was not reached. This fix does not establish database
recovery, current accepted picks, authenticated outcomes or an edge.

## Required verification

Before the correction, the focused Utah regressions produced four expected
failures and four passing rejection cases. After correction, 41 focused
synchronous identity/presentation checks passed, with 22 asynchronous cases
deselected locally. A broader Windows run stopped making progress and was
interrupted; no full local-suite pass is claimed. The complete asynchronous and
schedule tests remain unchanged in required Linux CI. Independent review found
the exception and regression scope preserves the existing identity boundary.

Run profile identity/presentation regressions and the real required CI,
PostgreSQL, schema and CodeQL gates. The next ordinary scan must independently
show its exact head, original selected operation/cron, current NBA input result,
source capture strings and completed database receipt counts. No manual quote
collection is needed to force that checkpoint. Missing evidence remains missing.
