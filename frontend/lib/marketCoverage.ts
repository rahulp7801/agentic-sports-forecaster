export interface MarketCoverage {
  discovered_games:number;
  attempted_games:number;
  observed_games:number;
  quoted_games:number;
  failed_games:number;
  event_failed_games?:number;
  market_failed_games?:number;
  sample_complete_games?:number;
}

export interface PropQuoteCoverage {
  prop_structured_quote_markets:number;
  prop_yes_ask_quote_markets?:number;
  prop_no_ask_quote_markets?:number;
  prop_two_sided_quote_markets?:number;
  prop_one_sided_quote_markets?:number;
  prop_unquoted_markets?:number;
}

export interface PropLinkageCoverage {
  prop_discovery_complete?:boolean;
  prop_linked_markets?:number;
  prop_linked_events?:number;
  prop_open_markets?:number;
  prop_open_events?:number;
}

export function sourceFailureText(reason:unknown):string|null {
  if (reason==='collection_cadence') return 'waiting for scheduled sportsbook capture';
  if (reason==='access_denied') return 'provider access denied';
  if (reason==='rate_limited') return 'provider rate limited';
  if (reason==='upstream_unavailable') return 'provider temporarily unavailable';
  if (reason==='request_rejected') return 'provider rejected the request';
  return null;
}

export function marketCoverageText(coverage:MarketCoverage):string {
  const {discovered_games:discovered,attempted_games:attempted,observed_games:observed,event_failed_games:eventFailed,
    market_failed_games:marketFailed,sample_complete_games:complete,quoted_games:quoted}=coverage;
  if ([attempted,observed,eventFailed,marketFailed,complete,quoted]
      .every(value=>Number.isSafeInteger(value))
      && eventFailed!==undefined && marketFailed!==undefined && complete!==undefined
      && attempted>=0 && observed>=0 && eventFailed>=0 && marketFailed>=0 && complete>=0
      && attempted===observed+eventFailed && observed===complete+marketFailed) {
    const sample=Number.isSafeInteger(discovered) && attempted<discovered
      ? `${attempted}/${discovered} discovered games attempted · ` : '';
    return `${sample}${observed}/${attempted} event records observed, ${eventFailed} event failures, `+
      `${complete} sampled games complete, ${marketFailed} with partial market failures, ${quoted} with quotes`;
  }
  return `${observed}/${coverage.discovered_games} discovered games inspected, `+
    `${quoted} with quotes, ${coverage.failed_games} with collection failures`;
}

function validCount(value:unknown):value is number {
  return typeof value==='number' && Number.isSafeInteger(value) && value>=0;
}

export function propLinkageCoverageText(coverage:PropLinkageCoverage):string|null {
  const {prop_linked_markets:linked,prop_linked_events:linkedEvents,
    prop_open_markets:open,prop_open_events:openEvents}=coverage;
  if (!validCount(linked) || !validCount(linkedEvents) || linkedEvents>linked
      || (linked>0 && linkedEvents===0)
      || (open!==undefined && (!validCount(open) || linked>open))
      || (openEvents!==undefined && (!validCount(openEvents) || linkedEvents>openEvents))) return null;
  const discovery=coverage.prop_discovery_complete===false ? ' · prop discovery incomplete' : '';
  if (open===undefined || openEvents===undefined) {
    return `${linked} player props linked to sampled games across ${linkedEvents} prop events${discovery}`;
  }
  if (openEvents>open || (open>0 && openEvents===0) || open-linked<openEvents-linkedEvents) return null;
  if (open===0) return `0 observed open player props across discovered series${discovery}`;
  return `${linked} of ${open} observed open player props linked to sampled games across `+
    `${linkedEvents} of ${openEvents} prop events (open totals across discovered series)${discovery}`;
}

export function propQuoteCoverageText(coverage:PropQuoteCoverage):string {
  const structured=coverage.prop_structured_quote_markets;
  const yes=coverage.prop_yes_ask_quote_markets;
  const no=coverage.prop_no_ask_quote_markets;
  const two=coverage.prop_two_sided_quote_markets;
  const one=coverage.prop_one_sided_quote_markets;
  const unquoted=coverage.prop_unquoted_markets;
  if ([structured,yes,no,two,one,unquoted].every(value=>Number.isSafeInteger(value))
      && yes!==undefined && no!==undefined && two!==undefined && one!==undefined && unquoted!==undefined
      && structured>=0 && yes>=0 && no>=0 && two>=0 && one>=0 && unquoted>=0
      && structured===two+one+unquoted && yes+no===2*two+one) {
    const rate=structured ? `${(100*two/structured).toFixed(1)}%` : 'n/a';
    return `${structured} structured top-of-book markets · ${two} two-sided (${rate}) · `+
      `${one} one-sided (${yes} YES asks, ${no} NO asks) · ${unquoted} without displayed asks`;
  }
  return `${structured} structured top-of-book markets (${two ?? 'unknown'} two-sided)`;
}
