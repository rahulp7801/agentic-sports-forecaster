# October 4 stat-only pregame remote-proof preservation

The original NFL stat-only paper cohort remains fixed at 70 decisions in 15
games. Its model probabilities, first exact asks, later prelock asks, fee
receipts and strict last-20 control are local ignored evidence whose SHA-256
values were declared in the private repository before the relevant games.
This note preserves the **Git objects** behind those declarations after
subsequent amended pushes to release PR #345. It reads no results and does not
change a model, decision, price, qualification gate or order path.

| GitHub server push (UTC) | Pregame commit | Before kickoff | Contents pinned in that commit | Preserving private ref |
|---|---|---|---|---|
| 2026-10-04 13:17:40 | `5ead9ccdf7be9c859f5371aa6f47cf4591acb9ad` | 13:30 UTC | Original source/model/quote/70-decision hashes, strict prior-20 control, and first prelock/fee receipts | `research/20261004-stat-only-pregame` |
| 2026-10-04 16:30:49 | `2031053fac3c2e61f5546530c4ed432b274018df` | 17:00 UTC | Second 36-decision prelock/fee receipts and fixed 40-of-70 net/prior-20 diagnostic hash | `research/20261004-1700-prelock-proof` |

The timestamps and commit OIDs came from GitHub's `HeadRefForcePushedEvent`
timeline for private PR #345, not from client-controlled Git author or
committer dates. The exact commits were independently served by GitHub's Git
commit API and the two private branch refs were verified to point to those
OIDs. **The preservation refs were created after the kickoffs.** They keep
the previously pushed objects available; they do not themselves prove
pregame publication. The server-dated PR events provide that chronology.
The first preserved commit contains the original receipt hash declarations
already documented in `2026-10-04-kalshi-stat-only-forward.md`; the second
contains the 17:00 group and combined diagnostic declarations in
`2026-10-04-kalshi-stat-only-net-prior20.md`. The local ignored original
quote, first prelock and combined diagnostic bytes were also checked against
separate D-drive backups and matched byte for byte.

Later scheduled groups still require their own timely raw receipts and
chronology evidence. This preservation does not authenticate venue outcomes,
prove fills or net returns, supply 50 independent games, establish a betting
edge, or justify a consumer qualified pick. Preserve each future v4 marker's
exact Git object under a private ref when the `kalshi_stat_only_remote_anchor`
tool has verified the server-dated push, so later release-PR amendments do not
orphan the object it needs to replay.
