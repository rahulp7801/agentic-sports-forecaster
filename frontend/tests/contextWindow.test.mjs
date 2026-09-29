import test from 'node:test';
import assert from 'node:assert/strict';
import {publicContextWindow,contextWindowText} from '../lib/contextWindow.ts';
const cutoff='2026-09-30',counts={active:2,absent:0,unknown:1};
const window={cutoff,active:{oldest:'2025-09-01',newest:'2025-09-08',secret:'hidden'},absent:null,
  unknown:{oldest:'2026-09-02',newest:'2026-09-02'},internal:'hidden'};
test('participation dates use exact groups and strip private fields',()=>{
  const result=publicContextWindow(window,counts,cutoff);
  assert.deepEqual(result,{cutoff,active:{oldest:'2025-09-01',newest:'2025-09-08'},absent:null,
    unknown:{oldest:'2026-09-02',newest:'2026-09-02'}});
  assert.match(contextWindowText({sample_window:result})[0],/does not establish current form/);
  assert.match(contextWindowText({sample_window:result})[1],/Unknown participation: 2026-09-02/);
  assert.match(contextWindowText({})[0],/recency is unknown/);
});
test('participation dates reject invalid calendars, reversed dates, wrong counts and cutoff',()=>{
  for(const patch of [{cutoff:'2026-10-01'}, {active:null}, {absent:window.active},
    {unknown:null},{active:{oldest:'2026-02-30',newest:'2026-03-01'}},
    {active:{oldest:'2026-09-03',newest:'2026-09-02'}},
    {active:{oldest:'2026-09-01',newest:cutoff}}, {active:['2026-09-01']}])
    assert.equal(publicContextWindow({...window,...patch},counts,cutoff),null);
});
