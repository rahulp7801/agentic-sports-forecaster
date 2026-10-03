# Versioned repair of the October 8 prospective fixture replay

## Actual scheduled failure

The original local collector ran at October 8 17:00:01 UTC and exited 0. It
completed its source/model/quote inputs and original commitment by 17:01 UTC.
The companion publisher ran at 17:25:01 UTC and exited 1, leaving no teammate
study receipt, remote anchor or local recovery archive. No collector was
restarted and no new quote request was made.

An offline reproduction passed the original model/history, receiving source,
price decision, recent-gap receipt and capped-role receipt checks, then raised
`KeyError: details` in the independent-series fixture mapper. Every one of the
15 selected games has the required details inside the authenticated `milestone`
object. The mapper incorrectly indexed the outer source envelope. The existing
series/study tests mocked this mapper, so they did not exercise the actual
archive structure. The earlier source schema audit did not cover this envelope.

## Explicitly versioned correction

The original v1 series, recent-gap, capped-role and teammate-study files remain
byte-for-byte unchanged. Existing captured receipts, candidate membership,
probabilities, market prices, source observations, model artifacts and cutoffs
are preserved. The actual capture remains 234 original market contracts, 188
original role forecasts, 80 stat-only forecasts and **47 paper candidates in
15 fixtures**. Its original fixed recent-gap groups remain **19 uplift / 28
other**; all 188 capped-role forecasts retain their original capture receipt.
These are research records, not qualified consumer picks or verified outcomes.

- The separate `kalshi_stat_only_next_series_v2.py` reads each selected game's
  nested milestone, using the unchanged strict fixture-key verifier first.
  Duplicate identities, ambiguous fixtures, changed start times and same-team
  fixtures still reject. No game or candidate is dropped to make replay succeed.
- Separate v2 recent-gap/role evaluation modules delegate original receipt
  validation to their frozen v1 implementations. They preserve the existing
  ownership, matching-price, complete-result, 50-game and game/player Brier and
  log-loss rules, while naming and hashing the corrected evaluation explicitly.
  Their manifests/report protocols are distinct from the frozen v1 receipts.
- The separate teammate study v2 preserves the original membership and support
  policy, records its actual later pregame preparation time and binds the v2
  source graph plus the frozen helpers. Its private hash-only marker has a
  distinct `next-nfl-context-v2-<stamp>-anchor.json` name. It does not backdate a
  receipt or pretend the scheduled v1 publisher succeeded.
- The existing publisher now prepares the versioned study with the corrected
  mapper. The launcher admits the explicitly named v2 offline commands; no task,
  trigger, collection quota, staged reserve or provider request is added.

This versioned implementation correction was prepared before the original first
kickoff, October 9 00:15 UTC. It is not a post-result change to selection or a
consumer model promotion. Frozen v1 evaluation reports must not be silently
relabelled or mixed with v2 reports. The original declared policy still governs
whether any later paired result supports a probability improvement.

## Verification before publication

The corrected map reproduces exactly the original strict verifier's entire
15-fixture set. A second actual offline publisher dry-run passed all original
source/model/receipt checks and versioned context preparation, with zero network
reads or original-file writes. The initial affected publisher, source launcher,
role/recent/context/series and local-recovery suite passed **176 tests**.
Additional v2 ownership/scoring/CLI verification is recorded below once complete.
No frontend/runtime/schema source changed; no additional dashboard build or
production acceptance is claimed.

A local original-byte manifest retains all **25 original files / 15,622,152
bytes**, including every source/context asset and original research receipt.
Detailed raw files, manifest and offline diagnostic scripts remain ignored and
local. Only aggregate findings and commitment hashes enter the private review.

## Original evidence checkpoints

The first selected kickoff remains **October 9 00:15 UTC**. A recovered hash
publication must verify GitHub's actual server push before that time; local file
modification clocks or the original scheduled-task time are not substitutes.
All three study receipts and markers must agree in the preserved private commit.
The recovery package must report `local_verified`, full hash/readback verification
and `remote_backed_up: false`, or an explicit local failure.

The original entire cohort's first eligible settlement remains **October 13
06:15 UTC** (six hours after the latest selected kickoff). Do not collect early
partial results or backfill prices to replace this gate. The next already
scheduled capture/publisher remains October 10 17:00/17:25 UTC. The Saturday
Questionable-context window can qualify fixtures that were outside Thursday's
unchanged 48-hour context window; later coverage cannot replace an earlier
eligible fixture owner.

The account CI refusal, required private CodeQL, missing owner OAuth and protected
waitlist provisioning still govern production deployment. Existing dashboard
containment remains active. No edge, 75% win rate, causal teammate adjustment,
execution, ROI, CLV, spending or production activation is claimed.

The final v2-specific suite passes **26 tests**, including the actual nested
source envelope, contradictory outer fields, all original fixture rejection
cases, frozen receipt delegates, earliest-owner/missing-price/nonbinary coverage,
50-game and both-comparator/cluster support rules, no promotion, and the CLI's
original full-cohort result-read gate. Existing controlled policy regression
inputs are reused against the new report paths; those scoring cases still mock
sources/results and are not real performance evidence. The actual 15-fixture map
and complete saved-input dry-run are separate real-input checks. Cached pinned
Bandit passes all four versioned modules, publisher and source launcher.


## Completed pregame recovery

The single recovery of the saved October 8 17:00 capture succeeded. GitHub
verified the private hash-only publication at **October 8 20:34:52 UTC**, before
the original first selected kickoff. The actual v2 teammate-study receipt was
prepared at **20:34:23.631915 UTC**; the original collection and prices retain
their 17:00 chronology. The failed 17:25 scheduled publisher is not relabelled
as successful.

The original commitment digest remains
`955398aec9b50fddf75209c5359c6a241ae650fea9b9ebba1547780bf196b5b1`.
The preserved private research ref
`research/next-nfl-stat-only-20261008T1700-anchor` points to
`253fe7c9856972054171c129f7c51c82bfda1bb3`, containing all three hash-only
markers. The two earlier fixed-prelock research refs remain unchanged. Later
review-branch amendments must not move this research ref or substitute their
push times for the original pregame ownership proof.

After publication, every one of the **25 original files / 15,622,152 bytes**
was rehashed against the pre-recovery manifest and matched exactly. The local
recovery archive contains **27 files**, including the new study and remote
anchor receipts. Its SHA-256 is
`7e4187281ae5e874ff642cc099960c94de6315d63d4cf62163dcb73b83fbd387`.
The package reports `local_verified`, `every_file_readback_verified: true`
and **`remote_backed_up: false`**; archive hash and ZIP integrity were checked
again. The user's instruction to keep future raw evidence local remains in
force. No recurring raw upload, additional collection, result request, paid
storage or spending occurred.

The next evidence checkpoint is still **October 13 06:15 UTC** for the entire
original cohort. Retrieve authenticated venue outcomes only after that gate,
retain the entire denominator, and evaluate the explicitly named v2 series,
recent-gap, capped-role and teammate reports using this preserved anchor. Keep
frozen v1 receipts and versions separate. Until those paired outcomes satisfy
the existing independent-game and game/player comparator rules, this is
prospectively committed research, not a verified edge or a consumer promotion.


## Source-safe full-cohort result follow-up

The existing `kalshi_stat_only_next_settlement_capture` was missing from the
local paper-task launcher's explicit allowlist. It is now admitted through the
same checkout-source inspection used by the scheduled captures. The underlying
collector remains unchanged: original commitment/source/model replay precedes
the entire-cohort October 13 06:15 UTC gate, independent clock attestation and
unsigned exact-contract outcome reads. Existing outputs still refuse overwrite.
No result task or additional recurring collection was scheduled.

The affected launcher and future settlement tests pass **18 tests**. New CLI
cases prove premature gates, altered commitments and existing outputs reject
before clock attestation or opening the venue reader. Source inspection tests
cover the next collector and all four v2 evaluation commands despite a foreign
`PYTHONPATH`. Cached pinned Bandit passes the launcher change. All **19** files
bound by the current pregame teammate implementation and all **25** original
capture files were separately rehashed and remain unchanged.

The ignored local checkpoint
`.local/next-nfl-stat-only-20261008T1700-result-checkpoint.json` holds exact
argument arrays for the one existing outcome collector and four independent
v2 reports. Its four manifests are stored directly below `.local`, so all
capture paths remain inside each manifest's permitted root. Existing pregame
paths were checked; the future outcome file is deliberately absent. All four
manifests use the preserved `253fe7c9856972054171c129f7c51c82bfda1bb3`
anchor, the original primary marker and distinct v2 report protocols. They are
prepared commands, not evidence of collection or completed evaluation. They
must be executed only after the original full-cohort gate, using
`.venv/Scripts/python.exe ops/run_paper_task.py --module <module> <arguments>`.
Raw evidence, result receipts and eventual reports remain local; no new
provider quote collection or raw evidence publication is authorized.


An actual source-safe CLI check used every original October 8 input, source
directory and commitment. It completed the original offline preflight and
exited **2** with `Before full-cohort venue result gate; no venue read was made`.
The independently inspected collector source SHA-256 was
`309f0fb91fa16c4b69134a36f35c496f149c78dcd4a706948ff54b56f5a3ed5d`.
Neither the outcome receipt nor audit output was created. This expected refusal
is evidence that the current saved cohort obeys its gate, not a settlement,
performance result or production deployment.


## October 12: restored evidence and private push containment

After the original D: drive returned, all 25 original capture files and all
19 frozen implementation hashes matched. The recovery archive's SHA-256 and
ZIP integrity also passed. The restored source-safe launcher resolved the
capture, publisher and result modules to this checkout. The actual original
offline preflight replay completed and returned the expected premature gate
refusal, without creating outcomes or reading the venue. The unchanged gate is
October 13 06:15 UTC (October 12 11:15 PM Pacific).

A metadata check found the repository public. The assistant interpreted the
owner's private-alpha instruction too broadly and changed the whole repository
to private at October 13 04:49:02 UTC. The owner subsequently clarified that
the platform repository should be public and only the alpha should be hidden.
Follow-up checks found only the owner collaborator, zero pending invitations,
zero current forks and anonymous repository HTTP 404. The beginning of the
public interval and any copies made during it are unknown. Restoring private
visibility cannot revoke copies.

The existing publisher binds original inputs and verifies server push timing,
but does not check repository visibility before its Git pushes. The separate
`ops/private-pre-push.sh` hook and standard-library `ops/verify_private_push.py`
guard address this operational gap without changing any frozen implementation
or study version. Install the shell script as `.git/hooks/pre-push` in the
dedicated private checkout, retaining an existing hook if one is present.
The hook checks the actual push destination against the approved GitHub
repository and reads current repository identity, private visibility, owner
administrator access, collaborators and invitations immediately before Git
transfers new objects. Public, different, shared, malformed and unavailable
metadata reject the push. The GitHub hostname is explicit, responses and
requests are bounded, and provider errors are redacted.

This is a local Git safeguard, not a GitHub account policy: a setting can change
after verification, hooks can be disabled, and other checkouts do not inherit
this installation. Do not use `--no-verify` or disable the hook to bypass a
refusal. The guard does not change visibility automatically, change access,
upload raw evidence, collect quotes, spend money, relax an evaluation threshold
or promote a pick. Existing CI and production authorization gates still apply.

The final guard and source-safe launcher suite passes **62 tests**. It includes
an actual Git pre-push rejection against an isolated local bare repository:
the approved-looking URL is redirected locally, the hook rejects the rewrite,
and the receiving repository retains zero refs and zero loose/packed objects.
No real provider or remote is contacted by that test. Public visibility,
incorrect identity, extra collaborators, pending invitations, malformed data,
bounded provider errors and timeouts also reject. Cached pinned Bandit passes.
The installed hook independently passed against current owner-private metadata.
Hook line endings are pinned to LF for Windows checkouts. The installation is
only in this dedicated checkout; the outer user checkout was not changed.

## October 12: corrected public-code and private-alpha boundary

The owner selected restoring the original repository URL **after reviewing the
required cleanup**. Keeping the whole platform repository private is not the
final requirement. The existing checkout and its push guard currently protect
unseparated private research; they are not a policy against public platform code.
The autonomous follow-up instructions now preserve this corrected distinction,
consolidate related commits and keep future raw evidence local.

The authenticated metadata inventory found 192 branches (33 under `research/`),
347 pull requests, 2,701 workflow runs, 52 retained Actions artifacts and ten
releases. One draft release contains the earlier 7,751,995-byte evidence backup.
The release tree includes 136 quant files and 238 verification files; PR #345
alone has 50,787 characters of release notes. These are review surfaces, not a
claim that every counted item contains alpha. Comments, attachments, all
historical blobs and build outputs have not yet received a complete content audit.

The ignored `.local/public-repository-cleanup-review-20261012.json` records the
concrete original-URL handoff proposal and its inventory. Preserve the existing
repository ID, research commits, PRs and evidence privately under a reviewed
engine name; publish only reviewed platform code with clean history at the
original owner/name. This would create a new public repository ID and requires
explicit remote, scheduled-publisher, guard, deployment and CI binding updates.
Reusing the original name removes GitHub's old-name redirects, so those updates
must precede the handoff. The proposed engine name returned authenticated 404;
its availability must be checked again before an approved rename.

A same-ID history rewrite is not an equivalent safe shortcut: it changes frozen
commit identities and does not remove GitHub's read-only PR refs or cached
commits. GitHub documents that its Support team will not remove non-sensitive
data. Publishing the current repository would also expose Actions history/logs.
See [visibility changes](https://docs.github.com/en/repositories/managing-your-repositorys-settings-and-features/managing-repository-settings/setting-repository-visibility),
[history removal limitations](https://docs.github.com/en/authentication/keeping-your-account-and-data-secure/removing-sensitive-data-from-a-repository)
and [repository rename behavior](https://docs.github.com/en/repositories/creating-and-managing-repositories/renaming-a-repository).

The proposed public surface contains reviewed UI, public landing/demo/waitlist,
typed output contracts and a thin authenticated boundary. Forecast/context
algorithms, model artifacts, qualification rules and research remain private.
Private engine code must not be imported into browser bundles, public CI or
public build artifacts. No repository rename, history rewrite, deletion,
new public repository, publication or production change was performed for this
review. Existing frozen sources, quotas, reserve and access gates remain intact.

## October 13: security patches and completed original result checkpoint

Next.js and eslint-config-next are pinned to **16.3.8**. The installed patch
passes all 343 frontend tests, 62 release-script tests, lint, TypeScript and
the production Webpack build. The unchanged production dependency audit reports
zero vulnerabilities. The full audit still reports five high findings from the
development-only braces dependency chain; npm's suggested major downgrade is
not applied and the advisory is not dismissed. The maintainer currently lists
no patched braces version. Sources: [Next.js advisory](https://github.com/advisories/GHSA-cjq9-62q9-8jv4)
and [braces advisory](https://github.com/advisories/GHSA-vfj7-8cjw-p6xm).

The lock changes Mako **1.4.1 to 1.4.2**. An isolated locked migration environment
passes offline SQL compilation through 0048. A controlled local Windows fixture
demonstrates the actual regression: all three drive/path traversal forms reach
the sentinel with 1.4.1, and all three are rejected with 1.4.2; the legitimate
template renders in both environments. No unrelated files are used. The original
research virtualenv is deliberately unchanged. See the [Mako advisory](https://github.com/advisories/GHSA-5639-2j2p-m4mx).

All 32 actual HTTP checks pass against the patched local production build:
public landing, private terminal redirects, anonymous no-store API rejection,
CSRF/PKCE/state, synthetic owner admission and nonowner/expired rejection.
The disposable database is unavailable after the PC restart, so this check
explicitly verifies two valid waitlist requests return **503**, never a saved
success. It does not repeat or claim durable waitlist persistence or a real
GitHub OAuth round trip. Earlier evidence files are preserved under their
original names; this run writes distinct October 13 local receipts.

After the original October 13 06:15 UTC gate, the collector initially refused
a clock request exceeding its unchanged two-second bound, before venue reads.
A separate clock probe passed. One unchanged-collector retry then retained fresh
two-host clock proof at **07:31:01 UTC**, all **234** original venue contracts
and **15** original games: **233** binary venue-verified results, one nonbinary
result kept excluded. Capture record commitment:
`4bb18842cc425b98016506c7d22731602c11e2dd1cb3f0eb3ae21b2b1e53aa44`.
No result or quote recollection is required. Raw outcomes and all reports stay local.

All four original v2 report commands exposed the same `KeyError`:
`paired_prior_log_loss`. The reused frozen scorer supplies bucket log loss and
top-level Brier fields but omits the top-level retained-history log loss expected
by the next evaluator. The frozen files and failed report paths are preserved.
The separate `kalshi_stat_only_next_eval_v2` adds exactly that aggregate using
the same verified binary results, exact two-sided prices and frozen prior
probabilities, checks its paired denominator and retains every original source,
clock, settlement and strict-prior gate. Four explicit v3 report forks use it;
their reports bind both the original 19-file implementation and five new repair
files. Original marker protocols, policies, candidate membership and thresholds
are unchanged. The original input manifests are preserved; the v3 manifest and
checkpoint paths are distinct and exclusive.

All four v3 replays complete with verified original pregame anchors. The primary
cohort contains **80/80** verified and two-sided paired model forecasts across
15 games. The original paper picks win **20/47 (42.55%)**; the fixed >=75%
probability subset wins **4/7 (57.14%)** across five games. These are paper
outcomes, not executed bets. On all 80 paired forecasts, model-minus-market
equal-game Brier is **+0.06436** and log loss **+0.14588**. Both game- and
player-cluster 95% intervals are above zero for both metrics: this cohort favors
the matching market probabilities. The fixed recent-uplift group wins 7/19;
the capped-role report has 187 paired binary forecasts and no supported
prospective improvement. The teammate study retains one eligible fixture,
38 outside-window candidates and the original unavailable primary membership;
no missing context is repaired from later sources. None meets its support gate,
establishes an edge or promotes a consumer pick.

Final focused verification covers 33 report-schema/ownership/support checks
and 68 source-safe launcher/private-push/settlement checks. Cached pinned Bandit
passes the five new report files and launcher. All **25** original capture
hashes and **19** frozen implementation hashes were reverified unchanged.
The ignored v3 checkpoint records SHA-256 hashes of all six local outcome/report
files. The next existing capture remains **October 17 17:00 UTC / 10:00 AM
Pacific**, with original anchor publication at 17:25 UTC / 10:25 AM Pacific.
Verify that capture's timing, exact context coverage and original frozen study
receipts; retain earliest eligible ownership and never backfill the missed
October 10 pregame window. Public repository cleanup still awaits the owner's
requested review. CI, protected deployment, real OAuth and production waitlist
provisioning remain unverified; no visibility change, merge, spending or wager
was performed in this checkpoint.

## October 13: authenticated engine read adapter

The public-source import review found private qualification/ranking dependencies
reachable from client modules and qualification markers in the local production
terminal chunk. The review is module-level; it does not assert that the older
current production deployment serves this release. Twenty dependency-closed
auth/waitlist/layout/output-contract candidate sources were copied locally with
matching hashes and a clean approximately 47 KB secret scan. They are a partial
source review, not a buildable public export or publication approval.

The next implementation adds a server-only owner wrapper and bounded display
transport with no forecast, qualification, database or Python imports. The
existing encrypted owner-session check precedes configuration and upstream
access. Resource/path/query admission, a configured HTTPS origin, service-only
headers, redirect refusal, a stream-inclusive deadline, response byte bounds,
strict envelope protocol/revision/expiry and mandatory public projection protect
the boundary. Expiry is checked again after projection; private error bodies,
cookies and the configured service credential cannot enter the public reply.
All replies retain no-store containment.

This is an adapter prepared for the reviewed split. Existing routes are not
switched, no private engine service/configuration is created, and the current
frontend still requires the client/import separation identified by the review.
Focused verification passes **21** owner/access/request/transport tests, including
actual encrypted local owner cookies, synthetic upstream responses, streamed
cancellation, expiry during projection and credential reflection rejection.
Full-project TypeScript checking and adapter/test lint pass. This does not claim
a live engine round trip or repeat the earlier full frontend production build.
The [platform boundary contract](../platform-engine-boundary.md) specifies the
remaining producer, projection, bundle, OAuth/waitlist and protected release
gates. Original frozen sources, outcomes, chronology receipts and qualification
thresholds are untouched; no new quote requests, spending or raw uploads occur.

## October 13 Pacific: public historical demo source separation

The original D: checkout is available again at the unchanged starting head
`df939f65bc5357193b45da62ce5ae4dbdde24411`. All 25 original October 8 capture
files and six completed result/report files match their retained byte hashes.
The three remote frozen research refs are unchanged. October 17 capture and
publisher executables and working directories exist, with their original
10:00/10:25 AM Pacific schedule. No collection or result evaluation was repeated.

The public walkthrough now imports a fixed display fixture instead of full
historical input and browser model reconstruction. All three recorded model
probabilities, thresholds, samples, final stats and source commitments match
the retained retrospective export. Descriptive counts, medians, latest five
rows and date ranges independently match the original history. Correct and
missed examples remain; no pick or profit is produced. The UI distinguishes
observed frequency from recorded probability, identifies September 18 retrieval
after the target games and older history rather than current form, and replaces
the private game-log API link/dashboard CTA with the public waitlist.

All **356 frontend tests**, full-project TypeScript, changed-file lint and the
production Webpack build pass. An actual anonymous loopback GET returns HTML
200. The rendered default example and all **eight referenced browser scripts**
pass the revised chronology/navigation checks and scans for the original demo
reconstruction explanation, full-history metadata and tested qualification/model
markers. This is local production-build evidence, not deployed production proof
or an interactive browser audit. The loopback server was stopped after the check.

The source import inventory now covers 129 files. The landing source closure has
zero private implementations or full-history imports; its **13 sources / 55.87 KB**
were copied locally with matching hashes and a clean secret scan. These candidates
are not a complete buildable public export, and external packages have not been
audited by that import inventory. Nine dashboard client roots still reach private
implementations, down from eleven after separating the landing and walkthrough.
Live engine routes, their domain projections and that remaining client separation
are the next independent work. The [boundary contract](../platform-engine-boundary.md)
retains the exact release requirements. No repository identity handoff, public
publication, merge, deployment, quota/reserve change, new quote request, future
raw-evidence upload, spending or edge claim occurred.

## October 13 Pacific: producer-issued display states and results source closure

The private forecast-page producer now emits `linework-forecast-display-v1`
metadata alongside its existing selected signals. Original metrics, qualification,
ranking and primary/alternate choices remain authoritative on the server. The
receipt binds ordered IDs and explicit gate flags/reasons to page revision,
requested view, completeness and invalid-row count. It distinguishes qualified
live rows, gated watchlist rows and library research. Expired primaries withhold
their alternatives; surviving groups keep their original ranks. No watchlist or
library row can become a live action. The original inclusive source-age limits
and exact T-60 exclusion are preserved on the integer-millisecond clock.

Review reproduced a response-size regression before commit: a valid multibyte
archive fixture was **1,043,518 bytes** without new metadata but **1,065,344 bytes**
with it, exceeding the one-MiB transport bound while advertising complete
coverage. Page accounting now includes display rows, signal content, games and
reserved envelope/array overhead before advancing the cursor; oversized final
responses fail closed. The regression verifies a bounded first page and exact,
lossless continuation of all 100 original synthetic rows. No source collection
or real forecast count is inferred from that fixture.

Neutral labels, simple display math, calendar classification and output-only
board types now reside in separate public modules. All four extracted helper
functions, both moved board type declarations and private board/terms/gating
function bodies retain their previous implementations. The results component's
complete runtime and type import closure contains eight reviewed display sources
and no private qualification, ranking or board implementation. The output type
module emits no runtime logic. Remaining client roots reaching private logic are
eight, down from nine. The whole frontend is still not a clean public export.

All **371 frontend tests**, changed-file lint and the full production Webpack
build including TypeScript pass. The focused producer/page regression suite
passes **27** checks, including malformed flags/states, page binding, exact source
deadline and lock boundaries, expiry without alternate promotion, watchlist and
archive separation, incomplete coverage, metadata projection and byte/cursor
integrity. The broader untouched gate, board and slip suites also pass.

This is staged producer metadata. Existing browser qualification/ranking remains
in place. A complete public signal projector and record/envelope binding are
still required before replacing those client checks; retained locked/final boards
need a separate contract. No private engine service is configured and no real
engine/OAuth round trip or production deployment is claimed. The reviewed
repository identity handoff remains pending. Original frozen studies, source
files, chronology anchors, thresholds, caps and staged reserve are unchanged.
No new quote requests, result reevaluation, raw uploads, purchases, bets or
spending occurred. Next existing capture/publication remains October 17 at
10:00/10:25 AM Pacific, with original status coverage and ownership checks.

## October 13 Pacific: full forecast packet binding and public fetching

Added an explicit public signal/game projection that copies supplied metrics,
opaque model versions, source dates, uncertainty, gate flags and bounded nested
availability/participation/tracking/profile outputs. It performs no qualification,
ranking, source-policy dispatch or probability calculation. Exact producer/output
parity passes across all three sports and views, rich nested evidence, unavailable
states and the empty archive response. Unknown private fields do not enter its
returned record; malformed fields, getters and sparse/exotic collections fail
closed.

The existing owner signals API now issues a full request/resource/page integrity
binding. Canonical SHA-256 covers the exact request, serialized signals and games,
display metadata, coverage, revision, search identity and pagination. Same-ID
changes to price, line, probability, uncertainty, stake, sample or game start
cannot reuse a receipt. Correctly hashed packets for another resource/request
also fail admission. This is integrity metadata issued by the authenticated API,
not an independent signature or a verified private-engine round trip.

`fetchForecasts` no longer imports private signal qualification or ranking. It
uses supplied primary/alternative order and withholds expired approvals without
promotion. Inclusive source-age equality and the exact T-60 exclusion are
preserved. A stale watchlist remains gated and descriptive until its issued
lock; library rows never become live approval. Incomplete/invalid qualification
coverage yields no picks. The unsigned compatibility fallback was removed;
stable archive revisions, bounded continuation, search identity, cancellation
and verified partial-page recovery remain tested.

Review found and reproduced another availability failure: a context-heavy page
could fit the byte budget but exceed the retained 50,000-node JSON bound, causing
503 instead of continuation. Per-row accounting now includes canonical nodes
before consumption. A 100-row synthetic fixture retains all 64 teammate reports
and eight accepted dated/recent context groups per row, stays within both bounds
on every page and recovers all original IDs in order across continuation.

All **394 frontend tests**, changed-file lint and the production Webpack build
including TypeScript pass. The 23 new checks cover output parity/malformed
projection, packet tampering and expiry, dense-context continuation and actual
runtime/type source closure. The strict public fetch/decoder/Arbitrage union has
six runtime sources and seven including declaration-only types. Existing
qualification/ranking seeds reach six client roots, down from eight, but a
broader history/context review identifies **nine** unfinished client roots.
These counts have different scopes; the full public export is not ready.
The expanded local source inventory covers 138 files and 20 entrypoints.

The next concrete boundary is server-produced descriptive history: resolve an
immutable forecast by ID, preserve its selected-source and capture cutoffs,
and issue bound ten/twenty-game, last-five/previous-five, calendar/team and
participation display summaries. Model-specific cutoff decisions and historical
cohort reconstruction remain private. Recorded/locked/final boards still need
their distinct contract. No live route has been switched to an unconfigured
engine, and real service/OAuth/deployment verification remains pending.

No model, evaluator, qualification threshold, immutable anchor, source receipt,
quota/reserve or workflow was changed. No collection, outcome reevaluation,
future raw upload, purchase, bet or spending occurred. The reviewed repository
handoff is still pending; the next original evidence capture/publication remains
October 17 at 17:00/17:25 UTC. Inspect exact timing, retained context/status
coverage and earliest eligible whole-fixture ownership without reconstructing
the missed October 10 capture. Local contract tests do not establish an edge.

## October 13 Pacific: bound descriptive-history contract and participation separation

Prepared a private history-output producer and public
`linework-forecast-history-display-v1` decoder. The producer wraps the unchanged
history, recent/calendar form and card-summary helpers. It emits ten/twenty-game
windows, disjoint five-game comparisons, roster-team/calendar summaries and
existing participation wording. Original calculations, selected-source rules,
identity handling, signed yardage, PRA component requirements, missing stats,
ties, team aliases and retrieval-limit disclosures retain their previous behavior.

Every output requires the exact expected revision, normalized public forecast
record commitment, forecast ID, athlete/terms and original source/capture scope.
Missing timing, mismatched source-read cutoffs, duplicate/malformed or ambiguous
records return unavailable history without calculated/card output. Known missing
stats remain null. These are descriptive records; the contract has no live pick
approval, execution or settlement state.

Review reproduced malformed admission in the new decoder: zero rows could carry
nonzero win/loss/tie/missing totals and a 100% direction rate. Public validation
now checks supplied label/count/null/date coherence while preserving means,
rates and probabilities as supplied values. It does not regrade a numeric stat
against a line, calculate a new probability or select a cohort. The contradiction
is rejected, and exact private-helper parity remains passing.

Both participation formatter bodies were moved verbatim into a public module.
The three private validation functions and compatibility exports retain their
original implementations. The evidence panel now imports those formatters
directly. Its PlayerHistory/history reconstruction chain still reaches private
code; no complete client separation or new history endpoint is claimed.

The immutable integration boundary was checked against actual schema and role
definitions. Scanner/board IDs map to `analytics.predictions.id`, protected by
the 0039 raw payload/DB-receipt commitment. The dashboard role cannot read that
table; no credential or grant was widened. An eventual private resolver must
verify the raw TEXT commitment and original DB timestamp, then derive exact
athlete/stat, terms, roster and both cutoffs from that stored record.

The public canonical record digest is distinct from the raw ledger digest and
can include approved presentation enrichment. Current snapshot-window revision
is not an immutable pregame receipt. The available local legacy ledger export
does not include DB receipt columns or selected-source timestamps; it cannot be
upgraded into receipt proof, nor does its omission prove current DB nulls.
Existing history views retain selected forward source versions rather than all
original model inputs. A matching source-read descriptor is an assertion from
a trusted private read, not independent per-row availability proof. Actual
resolver/SQL/commitment and service integration remain required before switching
history consumers. Earlier-version gaps must stay unavailable.

All **417 frontend tests**, changed-file lint and the production Webpack build
including TypeScript pass. The 23 new checks cover exact producer/helper parity,
record/scope binding, malformed and contradictory outputs, source-cutoff
mismatches, availability/null states and actual public runtime/type closure.
The expanded source inventory has 141 files and 20 entrypoints; nine client
roots still reach private history/qualification code. A transient local
execution-helper setup-refresh failure delayed commands; the privileged host
path recovered and the original production build completed. The final ignored
history-display checkpoint supersedes the pending failure checkpoint.

No original
forecast/helper, model, evaluator, source receipt, chronology anchor, threshold,
quota/reserve or workflow was changed. No real history reader, engine service,
OAuth flow or deployment was activated. The reviewed repository handoff remains
pending. No collection, result reevaluation, raw upload, purchase, bet, spending
or edge claim occurred. The next existing capture/publication remains October 17
at 17:00/17:25 UTC with original timing, context/status and ownership checks.

## October 13 Pacific: private immutable forecast receipt and precise history scope

Prepared a private reader for the exact retained database row and a resolver
that derives its original as-of history query. The reader hashes original UTF-8
payload TEXT before parsing, binds ID and raw SHA-256, requires non-null receipt
fields and retains all six database timestamp digits. Reformatting, missing
legacy receipts, `Date` conversion, changed identity/hash, malformed JSON,
getters and byte/depth/node excesses remain unavailable.

The resolver accepts exactly ID and raw payload commitment. Its parameterized
SQL independently checks the stored TEXT hash and returns the receipt timestamp
as six-digit UTC text. It projects original athlete/stat, terms, source/capture
times, model policy, game-date cutoff and captured roster context. The raw
payload, private model metrics and research are not returned. No full EVSignal
is fabricated from ledger fields that lack public presentation metrics.

The existing version-to-source-policy mapping and legacy capture fallback are
retained. Precise chronology checks quote, selected source, generation, capture,
DB receipt and kickoff before preparing exact stable-ID history SQL. Original
offset strings survive unchanged; NFL passing/rushing uses the existing primary
source-version view. Caller-provided athlete, sport, line, direction or cutoff
replacement cannot widen the request. ID/hash descriptors are captured once
before the reader callback; getters and later request mutation cannot alter the
retained binding.

Synthetic review reproduced two concrete failures before commit. Valid capture,
receipt and kickoff within one millisecond were incorrectly rejected by a legacy
millisecond comparison; the new resolver compares microseconds and rejects
genuinely reversed or at-kickoff receipts. Array-valued sport/stat/status fields
could coerce into strings, select the wrong source view and bypass policy checks;
primitive enum admission now rejects them. The original history/helper, model,
source policy implementation and schema files remain unchanged. Project type
checking also caught BigInt literal syntax incompatible with the existing target;
using BigInt constructors preserves precision without changing that target.

All **440 frontend tests** pass, including **23 new receipt/resolver checks**.
The final 23 focused checks, full-project TypeScript and changed-file lint pass
after the compatibility fix. No new full production build is claimed for this
unreferenced private-helper increment. The preceding successful production build
at `ba19bf991c55d834462a1c40e5ce88739a2e1cea` retains its original scope; existing
route/component/runtime inputs were not changed.

This is tested private preparation, not an actual database query, source reader
or live service integration. Dashboard credentials and role grants remain
unchanged. The next adapter must pair a verified immutable record with an
independently resolved approved public record, preserve their distinct hashes,
read history with the derived scope and reuse the per-row source commitments.
The existing history-output helpers still use millisecond chronology and need
a precise private adapter before consuming this resolver. Historical source-view
gaps cannot be upgraded into complete model-input or pregame performance proof.

The release remains one consolidated private commit. Original 25 capture files,
six completed outcome/report files, cleanup review and three frozen remote
anchors retain their commitments. Public handoff, configured private engine,
owner OAuth/waitlist acceptance and CI/schema/deployment gates remain pending.
No quote/result collection, raw upload, spending, model/threshold change, reserve
bypass, merge, deployment or edge claim occurs in this increment. The next
existing capture/publication remains October 17 at 17:00/17:25 UTC; verify actual
timing, context/status coverage and earliest whole-fixture ownership. The missed
October 10 capture must not be reconstructed.

## October 14 Pacific: immutable forecast to descriptive-history output

Prepared a private bridge from verified immutable receipts to the existing
public history DTO. It independently reads a revision-bound approved public
record, verifies its separate canonical commitment and matches original
history-relevant identity, terms, source/capture timestamps, policy and retained
roster state. Raw ledger and public record hashes are never interchangeable.
Approved numeric forecast metrics remain independently supplied; this bridge
does not certify their raw-to-public parity or issue a new probability.

The bridge snapshots the exact request and reader callbacks before awaits.
Own-data copying rejects getters, exotic/sparse collections and nonfinite or
excessive JSON, with incremental UTF-8 byte/node/depth bounds. No receipt, raw
payload, source row, SQL or upstream error appears in the returned display.
Unresolved participation split provenance yields no participation labels, so
later approved-record enrichment is not presented as original captured context.

Only the immutable resolver's derived SQL/parameters reach the history reader.
At most twenty exact row wrappers are accepted. Missing/foreign athlete IDs,
at/after-cutoff dates and duplicate games are unavailable rather than silently
filtered into empty evidence. Passing/rushing rows pass the unchanged NFL
source-commitment check before log projection. A successful empty read retains
empty windows and null rates; failed or malformed reads contain no form/card
outputs. As-of source availability still relies on the trusted SQL predicate;
returned rows do not independently prove their availability timestamp or a
complete original model-input archive.

A separate private calculation path retains original stat/outcome summaries,
ten/twenty-record windows, disjoint five-game comparisons, calendar/team aliases,
missing stats, ties, signed yards, PRA requirements and card wording. It consumes
the precisely admitted context without revisiting the frozen millisecond guard
or changing source timestamps. Original history/card/source helpers remain
unchanged. Full integration now accepts the valid same-millisecond pregame
receipt that the older helper rejects, while rejecting a receipt at kickoff.

All **475 frontend tests** pass, including **35 new checks**: 24 bridge checks
and 11 calculation checks covering 32 sport/prop/direction parity combinations.
Full-project TypeScript and changed-file lint pass. The test reporter's existing
module-type warning is not a failure. No fresh production build is claimed for
this unreferenced private-helper increment; the successful ba19bf9 build retains
its original scope and existing runtime/route inputs are unchanged.

This is injected-reader preparation, not a real database or private-service
round trip. No route/UI consumer, role grant, credential, live qualification,
model, frozen evaluator, source receipt or threshold is changed. The next step
is a version-bound approved-record resolver and trusted source reader, then
private-service/domain-envelope integration before switching browser consumers.
Missing retained versions must remain unavailable; no latest-row substitution
or reconstructed pregame capture is allowed.

The release stays one consolidated private commit. Original capture/result
commitments and frozen anchors are preserved, future raw evidence stays local,
and the reviewed public repository handoff remains pending. CI/schema/deployment
gates and real owner OAuth/waitlist verification remain required. No collection,
outcome reevaluation, spending, quota/reserve change, merge, deployment or edge
claim occurs. The next existing capture/publication remains October 17 at
17:00/17:25 UTC, with actual timing, context/status and whole-fixture ownership
verification.
