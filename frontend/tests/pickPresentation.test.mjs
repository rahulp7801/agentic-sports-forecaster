import test from 'node:test';
import assert from 'node:assert/strict';
import {pickCardPresentation,pickDisplayState,shortlistPresentation,evidenceDecisionStatus} from '../lib/pickPresentation.ts';
import {base,now} from './fixtures/qualifiedSignal.mjs';

test('only an unretained signal is presented as an actionable live price',()=>{
  assert.equal(pickDisplayState({}),'live');
  assert.deepEqual(pickCardPresentation({},1),{
    state:'live',actionable:true,callLabel:'Suggested pick',rankLabel:'Top suggested pick',status:'Live price',
    priceLabel:'Current price',returnLabel:'Model-estimated net per $100',
  });
  assert.equal(pickCardPresentation({},2).rankLabel,'Suggested pick #2');
});

test('recorded and locked picks never expose the actionable presentation',()=>{
  const recorded=pickCardPresentation({board_state:'recorded'},1);
  assert.equal(recorded.actionable,false);assert.equal(recorded.status,'Price expired');
  assert.equal(recorded.priceLabel,'Recorded price');assert.equal(recorded.returnLabel,'At recorded price');
  assert.equal(recorded.callLabel,'Recorded selection');
  const locked=pickCardPresentation({board_state:'locked'},2);
  assert.equal(locked.actionable,false);assert.equal(locked.status,'Locked T−60');
  assert.equal(locked.priceLabel,'Locked price');assert.equal(locked.rankLabel,'Locked pick #2');
  assert.equal(locked.callLabel,'Locked selection');
});

test('shortlist copy states exactly whether prices are live or historical',()=>{
  assert.deepEqual(shortlistPresentation(3,0),{
    state:'live',eyebrow:'Suggested picks',title:'Suggested picks you can check now',
    description:'Player-history estimates screened against the captured price, roster, injury reports and risk limits. One line per player.',count:'3 live',
  });
  assert.deepEqual(shortlistPresentation(0,2),{
    state:'recorded',eyebrow:'Recorded board',title:'Last approved picks',
    description:'These exact captures passed every gate earlier. Prices shown are historical.',
    count:'0 live · 2 to reprice',
  });
  assert.equal(shortlistPresentation(0,0).title,'No current suggested pick available');
});

test('incomplete current verification hides live and retained main-board cards',()=>{
  for(const [live,retained] of [[1,2],[0,2],[0,0]]) {
    const result=shortlistPresentation(live,retained,false);
    assert.equal(result.state,'unavailable');
    assert.equal(result.count,'Unavailable');
  }
});

test('evidence panel distinguishes capture-time approval from a live qualification',()=>{
  assert.equal(evidenceDecisionStatus(base,now).kind,'current');
  for(const board_state of ['recorded','locked','final']) {
    const status=evidenceDecisionStatus({...base,board_state},now);
    assert.equal(status.kind,'recorded');
    assert.match(status.label,/when recorded/);
    assert.doesNotMatch(status.label,/current/);
  }
  const stale=evidenceDecisionStatus(base,now+6*60_000);
  assert.equal(stale.kind,'recorded');
  assert.match(stale.detail,/requalified/);
  assert.match(evidenceDecisionStatus(base,now+61*60_000).detail,/one-hour pregame pick lock/);
  assert.equal(evidenceDecisionStatus(base,now+121*60_000).detail,
    'This game is no longer pregame. The displayed decision is historical.');
  assert.equal(evidenceDecisionStatus({...base,gated:true,gate_reason:'stale_quote'},now).kind,'gated');
});
