# NFL tracking source chronology

The scanner passes its selection timestamp to the existing Next Gen Stats evidence loader. The loader excludes source observations after that timestamp before selecting its latest eight eligible weeks. It rejects incomplete source commitments, invalid sample counts and any returned source timestamp later than the requested cutoff. The emitted evidence retains that observation cutoff.

The source-time filter supplements the existing exclusive game-week cutoff. It does not infer missing weeks or change the forecast probability. The optional no-cutoff loader interface remains for legacy callers; new scanner captures always supply the aware timestamp.

## Consumer boundary

New forecast snapshots retain their actual capture timestamp. Public tracking evidence requires a valid pregame forecast capture and a source observation no later than that capture. If an explicit source cutoff is retained, the source must precede it and it must precede capture. A quote may legitimately precede source availability and inference, so quote time is not substituted for forecast capture.

Older snapshots without a valid capture anchor retain their forecasts but omit tracking evidence that cannot satisfy this check. Existing pick-board records already carry capture timestamps. Public projection retains the timestamp so repeating projection cannot strip otherwise valid evidence. Invalid tracking evidence never changes the primary probability or acceptance gates.

## Verification

- Unit checks for aware timestamps, late receipts, incomplete sources and window binding.
- PostgreSQL regression proving late records are excluded before the eight-week limit and current game weeks stay excluded.
- Public-boundary tests for data arriving between quote and forecast, post-capture data, invalid capture timing and repeat projection.
- No provider collection, historical forecast rewrites, model/evaluation version changes or threshold changes.
