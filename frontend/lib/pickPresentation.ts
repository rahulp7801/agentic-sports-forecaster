import type {EVSignal} from './types';

export type PickDisplayState='live'|'recorded'|'locked';

type BoardLike={board_state?:unknown};

export function pickDisplayState(value:BoardLike):PickDisplayState {
  return value.board_state==='recorded' || value.board_state==='locked' ? value.board_state : 'live';
}

/** An earlier approval must not become a claim of current qualification. */
export function evidenceDecisionStatus(signal:EVSignal,now:number) {
  if(signal.gated) return {kind:'gated' as const,label:'Not recommended.',
    detail:null};
  const boardState=(signal as EVSignal & {board_state?:unknown}).board_state;
  const quote=Date.parse(signal.snapped_at),start=Date.parse(signal.game_start_time ?? '');
  const availability=signal.availability;
  const observed=Date.parse(availability?.captured_at ?? '');
  const started=Number.isFinite(start) && start<=now;
  if(boardState==='final' || started) return {kind:'recorded' as const,
    label:'Passed gates when recorded.',detail:'This game is no longer pregame. The displayed decision is historical.'};
  if(Number.isFinite(start) && Number.isFinite(now) && now>=start-3_600_000) return {
    kind:'recorded' as const,label:'Passed gates when recorded.',
    detail:'The one-hour pregame pick lock has passed. Recheck the exact line before use.'};
  if(boardState==='recorded' || boardState==='locked' || !Number.isFinite(now)
    || !Number.isFinite(quote) || quote>now+60_000 || now-quote>300_000
    || !Number.isFinite(start) || !availability || availability.status!=='observed'
    || !availability.roster_confirmed || !Number.isFinite(observed)
    || observed>now+60_000 || now-observed>3_600_000) return {
      kind:'recorded' as const,label:'Passed gates when recorded.',
      detail:'The current price and availability have not been requalified. Recheck the exact line before use.'};
  return {kind:'current' as const,label:'Passed current research gates.',
    detail:'A model estimate is uncertain and is not a guarantee of an outcome.'};
}

export function pickCardPresentation(value:BoardLike,rank:number) {
  const state=pickDisplayState(value),safeRank=Number.isSafeInteger(rank) && rank>0 ? rank : 1;
  if(state==='live') return {
    state,actionable:true,callLabel:'Suggested pick',rankLabel:safeRank===1 ? 'Top suggested pick' : `Suggested pick #${safeRank}`,
    status:'Live price',priceLabel:'Current price',returnLabel:'Model-estimated net per $100',
  } as const;
  if(state==='locked') return {
    state,actionable:false,callLabel:'Locked selection',rankLabel:safeRank===1 ? 'Top locked pick' : `Locked pick #${safeRank}`,
    status:'Locked T−60',priceLabel:'Locked price',returnLabel:'At locked price',
  } as const;
  return {
    state,actionable:false,callLabel:'Recorded selection',rankLabel:safeRank===1 ? 'Top recorded pick' : `Recorded pick #${safeRank}`,
    status:'Price expired',priceLabel:'Recorded price',returnLabel:'At recorded price',
  } as const;
}

export function shortlistPresentation(liveCount:number,retainedCount:number,currentVerified=true) {
  if(!currentVerified) return {
    state:'unavailable' as const,eyebrow:'Verification unavailable',title:'Current pick check unavailable',
    description:'Current qualification could not be fully verified. Recorded selections remain in the research view.',
    count:'Unavailable',
  };
  if(liveCount>0) return {
    state:'live' as const,eyebrow:'Suggested picks',title:'Suggested picks you can check now',
    description:'Player-history estimates screened against the captured price, roster, injury reports and risk limits. One line per player.',
    count:`${liveCount} live`,
  };
  if(retainedCount>0) return {
    state:'recorded' as const,eyebrow:'Recorded board',title:'Last approved picks',
    description:'These exact captures passed every gate earlier. Prices shown are historical.',
    count:`0 live · ${retainedCount} to reprice`,
  };
  return {
    state:'empty' as const,eyebrow:'Suggested picks',title:'No current suggested pick available',
    description:'See the last recorded scan and quote coverage below. A current pick requires a fresh line and complete player evidence.',count:'0 live',
  };
}
