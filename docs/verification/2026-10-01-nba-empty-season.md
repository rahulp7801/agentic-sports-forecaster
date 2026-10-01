# NBA empty opening-season refresh

The 2026-27 NBA regular season had no game-log rows on 2026-10-01. A free, read-only NBA.com `PlayerGameLogs` probe returned zero rows with all required schema fields present. The live daily worker previously treated this valid empty batch as `ValueError` because row and batch provenance hashes require at least one actual stat row. NBA refresh was marked failed and the scan was blocked.

Ingestion now records a zero-row, `empty` season coverage result without inserting a fabricated stat row or batch hash. Missing schema still fails. The daily pipeline can proceed to scan while source coverage explicitly says the new season has no rows; any pick still must pass the existing history, source, current-context, quote and qualification gates. No model, probability, threshold, provider quota, reserve or betting behavior changes.
