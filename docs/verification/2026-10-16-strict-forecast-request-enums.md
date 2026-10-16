# Strict forecast request enums

## Observed defect

The forecast display request type guard converted the sport and view fields
with `String(...)` before checking their enum values. Arrays such as
`sport: ['nfl']` and `view: ['library']`, boxed strings and coercible objects
could therefore satisfy a contract that promises primitive string fields.
The sport field also supports an explicit `null` for unfiltered requests.

## Correction

Require primitive strings before comparing the sport and view enum values.
The existing packet producer and reader both use this guard, so a matching
payload digest cannot legitimize an incorrectly typed request. Valid scalar
requests and the explicit null sport retain their existing behavior.

This is request-contract validation. No live access bypass was demonstrated.
The separate owner OAuth configuration and private-engine activation review
remain outstanding.

## Verification

Four synthetic regression tests cover valid sport/view combinations, rejection
without object coercion, producer refusal and reader refusal of a malformed
request with a matching digest. The focused Node 24 run passed **16 tests**,
including the existing forecast fetching and packet-bounds tests. Fresh required
CI and CodeQL remain release gates.
