# Live consumer response and open-slip expiry boundary

The private release already returns `Cache-Control: no-store` to browsers and
uses a Vercel-only 30-second edge TTL plus 30-second stale-while-revalidate
window for live API responses. [Vercel's cache documentation](https://vercel.com/docs/caching/cache-control-headers)
says the Vercel-specific header takes precedence for its CDN and a stale
response can be delivered while background revalidation runs. That is useful
for database load, but a cached `/api/picks` response could outlive kickoff:
`publicPickBoard` removes a started game only when the function runs. The
slip-builder also held its initial pick array without an advancing clock; an
open tab could keep displaying a started game.

The release now bounds the live CDN fresh **plus** stale window to finish at
least two seconds before the earliest relevant deadline. `/api/picks` uses the
earliest current game start. `/api/signals?view=qualified` uses the earliest
start, five-minute quote expiry, or one-hour availability expiry across its
returned picks. Missing or invalid deadlines and imminent expiries use
no-store at every layer. Empty live responses retain the 30+30 edge cache;
research, archive and status policies are unchanged. The browser is still
never asked to cache an actionable response.

The read-only slip-builder filters its loaded approved records against the
current time every five seconds and immediately on tab visibility/focus. At
kickoff it drops the started game from candidates and selected-leg math, even
if the board is not refetched. It still labels recorded or locked prices as
historical. This changes no source, probability, model, pick qualification,
venue transaction, Odds API credit cap, reserve, or bet path.

Local verification on the private PR head before deployment: the full frontend
suite passed **309/309**, including new earliest-deadline and open-slip kickoff
regressions; TypeScript and changed-file ESLint passed; the production Next.js
build passed. Live Vercel response-header and timing checks remain pending
until protected CI and deployment can run. Exact-head hosted CI currently fails
all five code jobs with zero executed steps under the account spending gate;
this patch is not live.
