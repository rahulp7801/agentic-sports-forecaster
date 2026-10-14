import assert from 'node:assert/strict';
import test from 'node:test';
import {scanRailRows} from '../lib/scanRail.ts';
import {scanStatus} from '../lib/scanStatus.ts';

const empty=scanStatus(null);
const statuses={nba:empty,nfl:empty,cfb:empty};

test('scan rail keeps every published league and selects the requested sport',()=>{
  assert.deepEqual(scanRailRows(statuses)?.map(([sport])=>sport),['nba','nfl','cfb']);
  assert.deepEqual(scanRailRows({nfl:empty},'nfl')?.map(([sport])=>sport),['nfl']);
  const legacy={...empty};
  delete legacy.rolling_release_at;delete legacy.rolling_release_passed;
  assert.equal(scanRailRows({nfl:legacy},'nfl')?.[0][1].rolling_release_at,null);
  assert.equal(scanRailRows({nfl:legacy},'nfl')?.[0][1].rolling_release_passed,false);
});

test('malformed successful scan responses show unavailable instead of a blank rail',()=>{
  for(const payload of [null,[],{}, {nfl:empty,cfb:empty},
    {nba:empty,nfl:null,cfb:empty},
    {...statuses,cfb:{...empty,state:'made_up'}},
    {...statuses,cfb:{...empty,eligible:-1}},
    {...statuses,cfb:{...empty,updated_at:'not-a-date'}},
    {...statuses,cfb:{...empty,label:''}},
    {...statuses,cfb:{...empty,reserve_release_passed:'false'}},
    {...statuses,cfb:{...empty,rolling_release_passed:undefined}}]) {
    assert.equal(scanRailRows(payload),null);
  }
  assert.equal(scanRailRows({},'nfl'),null);
});
