import test from 'node:test';
import assert from 'node:assert/strict';
import {createHash} from 'node:crypto';
import {FORECAST_DISPLAY_PROTOCOL} from '../lib/forecastDisplayAuthority.ts';
import {canonicalForecastDisplayJson,FORECAST_RECORD_BINDING_PROTOCOL,readForecastDisplayPacket,
  validForecastDisplayRequest} from '../lib/forecastDisplayPacket.ts';
import {bindForecastDisplayPacket} from '../lib/forecastDisplayPacketProducer.ts';

const request={sport:'nfl',view:'library',offset:0,limit:100,revision:null,player:''};
const revision='a'.repeat(64),stamp='2026-10-16T00:00:00Z';
// Synthetic empty output exercises the transport contract without model data.
const page={search_player:'',generated_at:stamp,games:[],signals:[],
  display:{protocol:FORECAST_DISPLAY_PROTOCOL,evaluated_at:stamp,revision,view:'library',
    complete:true,invalid_signals:0,rows:[]},invalid_signals:0,total_count:0,
  pagination:{offset:0,next_offset:null,revision,complete:true},research_window:'Synthetic request test'};

test('request validation accepts primitive sport and view enums, including an unfiltered sport',()=>{
  for(const sport of [null,'nba','nfl','cfb']) {
    for(const view of ['library','qualified','candidates']) {
      assert.equal(validForecastDisplayRequest({...request,sport,view}),true);
    }
  }
});

test('request enums reject non-string values without invoking coercion',()=>{
  for(const [field,expected] of [['sport','nfl'],['view','library']]) {
    let calls=0;
    const coercible={toString(){calls++;return expected;}};
    for(const value of [[expected],Object(expected),coercible,undefined,true,1]) {
      assert.equal(validForecastDisplayRequest({...request,[field]:value}),false,field);
    }
    assert.equal(calls,0);
  }
  assert.equal(validForecastDisplayRequest({...request,view:null}),false);
});

test('packet production rejects array-valued request enums',()=>{
  for(const invalid of [{...request,sport:['nfl']},{...request,view:['library']}]) {
    assert.throws(()=>bindForecastDisplayPacket(page,invalid),/Invalid forecast display request/);
  }
});

test('a matching digest does not legitimize an array-valued request',async()=>{
  assert.notEqual(await readForecastDisplayPacket(bindForecastDisplayPacket(page,request),request),null);
  const invalid={...request,sport:['nfl']};
  const binding={protocol:FORECAST_RECORD_BINDING_PROTOCOL,resource:'signals',request:invalid,
    payload_sha256:createHash('sha256').update(canonicalForecastDisplayJson({
      protocol:FORECAST_RECORD_BINDING_PROTOCOL,resource:'signals',request:invalid,payload:page,
    })).digest('hex')};
  assert.equal(await readForecastDisplayPacket({...page,binding},invalid),null);
});
