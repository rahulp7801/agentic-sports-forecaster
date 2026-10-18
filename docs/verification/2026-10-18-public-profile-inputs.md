# Public profile inputs — October 18, 2026

## Failure

The scheduled profile refresh read only recent forecast signals. A public data
refresh can collect player identities without producing new forecast signals, so
its players never reached the profile reader. An empty input result did not prove
provider availability or current profile coverage.

The profile wrapper also omitted the sport argument to the availability reader.
That reader defaults to NFL, including its athlete and image validation rules.

## Change

Use the existing `kalshi-props:{sport}` and `slate:{sport}` snapshots alongside
recent signal identities. Decode the database JSON representation explicitly.
Validate the handoff digest, completeness, source clocks, player/team receipts,
and exact home/away/start join to the ESPN event before requesting a roster.
Reject ambiguous identities and require the resulting roster to match the
captured team side. Pass the requested sport through profile validation.

Bound input bytes, containers, players and event requests. Deduplicate identities
before fetching free roster data. Retain the prior snapshot and its capture time
when nothing can be verified. Keep original identity-source capture times
separate from the new roster capture.

The CLI reports source identity counts, selected event/player counts and whether
public inputs were observed, missing or rejected. Zero profiles no longer stands
alone as a provider coverage diagnostic. Inputs are limited to 16 MiB per snapshot;
the combined sources select at most 20 events, 200 distinct names and 50 names per
event before roster requests.

This changes presentation metadata. It does not request quotes, alter forecasts
or qualification, enable the paid pipeline, change dashboard access, or establish
an edge. Partial, stale or invalid handoffs cannot become verified profile input.

## Verification

Local fixtures use invented snapshots, mocked database results and mocked roster
responses. They cover the serialized database response, exact sport/team/game
identity, stale/corrupt inputs, production-sized bounds, request limits, empty
capture retention and the NBA sport argument. Release CI supplies the full test,
database, image, secret-scan and CodeQL checks.

The local relevant suite passed **168 tests** across player profiles, public
identity inputs, availability, cross-venue contracts and market collection. The
large synthetic fixture contains 2,932 compact quote rows and exceeds 2 MB; the
daily-slate fixture includes its actual eight source URLs. Tests ran against this
checkout using the existing complete Python runtime with bytecode writes disabled.
No source or model files in that runtime's checkout were changed.

Production coverage remains unverified until an ordinary scheduled profile job
consumes the new reader. No manual collection or provider call was used for local
verification. A consumer frontend deployment remains subject to its separate
production configuration gate.
