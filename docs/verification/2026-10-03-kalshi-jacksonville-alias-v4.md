# Forward Jacksonville identity repair

The normal Kalshi NFL research quote labels Jacksonville `JAC`; the pinned
nflverse weekly stat and snap releases label it `JAX`. The v3 shadow compared
those strings literally, so it withheld otherwise supported forecasts. The
forward v4 shadow maps nflverse JAX rows to JAC only when the selected, frozen
quote cohort uses JAC. It rejects mixed JAC/JAX selected quote aliases. The
original v1/v3 implementation and frozen pair are unchanged.

An offline diagnostic used the **exact six prequote source files** from the
ignored, hash-manifested October 3 pair artifact and its original market
archive. The original v3 pair replays exactly with **308 of 452** selected
contracts and 15 games. Recomputing today with v4 yields **319 of 452** and
15 games, including **11 Jacksonville forecasts**. The 11 recovered
contracts reduce `insufficient_current_team_role` from 27 to 16;
`fewer_than_20_offensive_games` remains 98 and
`missing_or_ambiguous_identity` remains 19. All six source hashes agree
with the frozen manifest. The private original pair SHA256 is
`8df6075f9794837f9c99772cf70d5dbdfb7954a07421ebfda0345494637e9acb`;
the matching archive SHA256 is
`05b2c78304cb80c7923bf530e1b2a8a9b3e30ce9f19d1d164d72944c878f29fc`.

This **post-freeze diagnostic is not a prospective v4 decision**. Do not
replace the saved v3 forecast, count the 11 contracts as precommitted picks,
or score them as such. Future natural captures with staged prequote source
manifests use v4. The artifact, policy, and paired evaluators dispatch by
the saved model protocol, so prior v3 receipts still replay under v3.
The v4 paired evaluator uses its own v5 report protocol. The probability
formula, comparator, timing, roster gate, and qualification threshold are
unchanged. Neither version establishes an edge or qualified consumer pick.

Local validation: full Python suite 1,933 passed/71 skipped before the
final evaluator-protocol distinction; focused evaluation suite 13 passed
after it. The saved v3 pair replayed exactly from its hash-matching six
assets. No paid or redundant provider collection occurred.
