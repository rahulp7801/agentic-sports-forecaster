# CFB game-log access and request recovery

## Reproduced gaps

The sanitized game-log API already serves CFB outcomes, but the terminal route allowlist rejected the view, sport switching sent it back to Picks, navigation hid it, and the display parser explicitly rejected CFB. Two regression tests reproduce the parser and route failures before the fix.

The all-sport game-log browser also had no timeout or retry control. Changing its player filter left old rows and their descriptive over rate visible until the next debounced fetch began. Requests and responses now use the existing bounded game-log validators.

## Changes

CFB Game logs is available through its direct terminal link and More tools; switching among NBA/NFL/CFB preserves that view. CFB shows only supported categories: passing, rushing and receiving yards and receptions. Missing statistics remain missing, including unsupported passing touchdowns. Existing offensive receiving zeros remain explicit zeros. The mobile CFB dock retains four main entries plus More tools, with Markets and Game logs inside the menu.

All three sports have Refresh/Retry, a 15-second request timeout and cancellation of obsolete requests. Editing the player filter immediately clears old rows and derived rates. Names are trimmed and normalized using the existing API rules; invalid filters make no request. Invalid responses fail closed and offer Retry. Historical counts remain descriptive and do not update any forecast probability.

## Verification

Six focused parser/navigation tests pass, including the two failing-before cases. TypeScript and focused ESLint pass. Browser checks at 320, 390 and 1440 pixels verify the existing public game-log records, sport-specific columns, CFB direct links and More tools, league switching, HTTP failure/retry, malformed responses, invalid-filter rejection without requests and whitespace-normalized search. A deliberately stalled request becomes retryable after 15.6 seconds. No document overflow or page errors occurred. The actual mobile CFB screenshot was inspected.

These checks read existing public API records and inject failures only in the local browser. No provider requests, historical record changes, new predictions, model/evaluation changes, qualification changes, extra credits or bets are introduced. No private CFB/team-context research is published; PR #194 is excluded. Repeat live consumer checks after green CI and deployment.
