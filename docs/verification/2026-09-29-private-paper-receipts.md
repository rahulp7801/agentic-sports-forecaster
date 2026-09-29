# Private pregame paper-selection receipts

The frozen cross-book replay alone does not establish that a selection was recorded while an offer was fresh. The new paper receipt policy is a separate operational cohort, `cross-book-paper-v1`, beginning no earlier than the existing September 30, 00:00 UTC freeze. It records the frozen candidate during existing event collection, after its source forecasts are committed. It makes no provider requests, purchases or bets and changes no qualified dashboard picks, model thresholds, source checks, staged reserves or API limits.

## Evidence lifecycle

Each receipt retains the exact offer, other-book references and relevant immutable forecast inputs for that player/game. Existing frozen selector code and dependency hashes are reused unchanged. Settlement fields and unrelated explanation/shadow blobs are excluded from the selection commitment. Source/model identities, quotes, baseline evidence, timing and probabilities remain committed. A future report joins these inputs to authenticated ledger settlements without altering the receipt.

The database owns the recorded timestamp through an insert trigger. The receipt must precede kickoff and the five-minute expiry of every required quote. Database checks re-evaluate timing after connection/lock waits; client-supplied backdating cannot rescue an expired offer. The primary key permits one receipt per protocol/sport/player/game, and retries cannot replace it. The worker receives SELECT/INSERT only. Dashboard, anonymous and authenticated browser roles have no access. Receipts and reports are never added to public snapshots or GitHub artifacts.

The report replays the committed source inputs at the server receipt time, compares them to current immutable ledger evidence, rejects changed/late/duplicate records, and scores only authenticated outcomes observed by the report time. Pending outcomes remain pending. It compares reference probabilities against the matching offered-book no-vig market and reports flat-stake hypothetical ROI with game-cluster uncertainty. The existing evidence requirements remain: 50 paired settled games, 100 decisions, 30 selection games, positive lower ROI bound and negative upper Brier difference bound. Passing still requires review and never promotes picks automatically.

Research recording has a bounded database timeout and cannot remove committed forecasts. The existing scanner invokes it directly; no additional collection schedule is introduced. Errors log only their class. A changed implementation invalidates this cohort and requires a distinct protocol rather than silently combining versions.

## Private audit

Run `python -m sportsbet.quant.cross_book_paper --output PRIVATE_REPORT.json` using the existing hosted audit configuration. Reads use a repeatable-read read-only snapshot and retrieve only forecast IDs referenced by paper receipts. Keep the resulting research report private, including all CFB/team-context output.

## Verification

88 focused tests pass, with one PostgreSQL-only test skipped locally. Genuine paired quote fixtures verify selection replay, pending outcomes, forged/changed receipt rejection, expiry, duplicate exclusion and nonfatal research failures. The real PostgreSQL CI suite additionally exercises concurrent first-write-wins, server timestamps, expired backdating rejection, payload hashes, forecast foreign keys and restricted reader/worker privileges. Migration tests verify browser-role isolation across upgrades and downgrades. No production evidence is fabricated for testing.
