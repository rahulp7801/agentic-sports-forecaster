# First accepted NFL result: source check (October 2, 2026)

This is a read-only source check for the one accepted current-version NFL
selection, Jaylen Warren under 3.5 receptions in Pittsburgh at Cleveland on
October 1. It is not an authenticated ledger settlement or an edge estimate.

The [NFL final game center](https://www.nfl.com/games/steelers-at-browns-2026-reg-4)
identifies Pittsburgh 24, Cleveland 27. The Steelers' [official gamebook](https://static.clubs.nfl.com/image/upload/steelers/cmygexqosg4m54pansqc),
linked from their homepage on October 2, identifies the same date, teams, and
Warren as an active starter; its receiving table reports 3 catches for 33 yards
on 6 targets. The downloaded PDF was checked privately with SHA-256
`02007ae5f17ebbefd8cb5f59c74b5302b86bfabbad81dd7a753234bc23d1fccc`.
The PDF itself is not included here; its notice restricts uses beyond media
coverage.

The free [nflverse 2026 play-by-play release](https://github.com/nflverse/nflverse-data/releases/tag/pbp)
was updated at 2026-10-02 04:33:24 UTC. The downloaded parquet SHA-256 was
`7d6d2371ac87184abac0ba40d51fed7bc40f49e083c152d84822018d26c599a7`.
Filtering `game_id=2026_04_PIT_CLE` and GSIS `00-0037228` in rusher or receiver
IDs yields 24 plays, including 17 rushes and 7 receiving targets. The three
completed receiver records have play IDs 411, 909, and 3502, with receiving
yards 11, 9, and 13. They independently corroborate the ESPN final athlete
record of 3 catches and 33 yards.

This makes the under-3.5 result **provisionally correct**. The frozen
`nfl-explicit-receiving-v1` automatic recovery requires exact-game published
nflverse offensive snaps; `snap_counts_2026.parquet` was last updated on
2026-09-29 11:01:26 UTC and still lacked Week 4 at this check. Play-by-play
is not represented as a snap record. Keep the dashboard selection pending until
the v1 receipt validates, then run the existing preview and exact-count apply
path. One decided selection cannot establish a 75% hit rate or market edge.

No paid odds request, bet, settlement write, model change, or threshold change
was made for this check.

## Recovery write boundary

An exceptional NFL result recovery now rechecks the retained ESPN source
commitment and the exact-game nflverse offensive-snap witness immediately
before its transaction writes an outcome. The generic stored-result verifier
and frozen evaluators retain their pinned source files. A malformed or
rehashed receipt cannot pass the recovery write merely by recalculating the
outer outcome hash. This hardening leaves the frozen settlement policy intact.

## Later free-source update

At 2026-10-02 11:01:51 UTC, the free nflverse Week 4 snap asset updated. Its
downloaded SHA-256 is
`fae0627d81f4ffa1802263ac0fad1a29f5c1986d5749a711bde7c50651498273`.
It contains one `2026_04_PIT_CLE` row for PFR `WarrJa01`, Pittsburgh, with
70 offensive snaps. A reconstructed bundle from the free ESPN exact-event,
roster, athlete-stat, nflverse identity, and snap sources passed the existing
`inspect_bundle` verifier. Against a prior read-only 58-forecast snapshot,
the unchanged recovery planner proposed 10 results for this player/game;
exactly one was accepted, with actual receptions 3 and outcome `true` for
under 3.5. The additional write-boundary source check also passed. The
reconstructed uncompressed bundle SHA-256 is
`2107071499000d018ceea42696f50033e64b1cc9825191b206dcce79effb1561`.

That is an **offline preview**, not a production settlement. The snapshot is
not a fresh hosted ledger transaction, and no exact-count apply has run. The
dashboard result remains pending until the hosted source and forecast state
are rechecked in one transaction and the result is written through the
existing recovery path.
