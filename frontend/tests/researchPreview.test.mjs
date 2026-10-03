import test from 'node:test';
import assert from 'node:assert/strict';
import {researchPlayerPreview} from '../lib/bestPicks.ts';
test('player previews retain the displayed watchlist side instead of the last opposite line',()=>{
 const best={id:'best',sport:'nfl',player:'Austin Hooper',direction:'over',line:0.5};
 const opposite={...best,id:'opposite',direction:'under'};
 const other={...best,id:'other',player:'Christian Watson'};
 const input=[best,opposite,other];
 assert.deepEqual(researchPlayerPreview(input),[best,other]);
 assert.deepEqual(input,[best,opposite,other]);
 assert.deepEqual(researchPlayerPreview(input,1),[best]);
 assert.deepEqual(researchPlayerPreview([]),[]);
});

test('research previews preserve distinct same-name athlete receipts',()=>{
 const first={id:'first',sport:'nfl',player:'Shared Name',player_id:'00-0000001'};
 const second={...first,id:'second',player_id:'00-0000002'};
 const alias={...first,id:'alias',player:'Updated Name'};
 assert.deepEqual(researchPlayerPreview([first,second,alias]),[first,second]);
});
