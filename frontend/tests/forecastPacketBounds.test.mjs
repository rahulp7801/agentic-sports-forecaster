import test from 'node:test';
import assert from 'node:assert/strict';
import {forecastPage,forecastRequest} from '../lib/forecastPage.ts';
import {canonicalForecastDisplayJson} from '../lib/forecastDisplayPacket.ts';

const now=Date.parse('2026-09-30T12:00:00Z'),stamp=new Date(now).toISOString();
const injuryUrl='https://site.api.espn.com/apis/site/v2/sports/football/nfl/injuries';
const revision='a'.repeat(64);
const reports=Array.from({length:64},(_,index)=>({player:`Context Player ${index}`,status:'Active',position:'WR',
  reported_at:stamp,...(index<8 ? {team:'KC',relationship:'teammate',unit:'offense',
    source_url:injuryUrl,source_sha256:'a'.repeat(64)} : {})}));
const active={games:1,mean:200,hit_rate:1},absent={games:0,mean:null,hit_rate:null};
const sampleWindow={cutoff:'2026-09-30',active:{oldest:'2026-09-29',newest:'2026-09-29'},absent:null,unknown:null};
const splits=reports.slice(0,8).map(report=>({player:report.player,status:report.status,position:report.position,
  team:report.team,relationship:report.relationship,unit:report.unit,source:'nflverse_snap_counts',
  participation:'recorded unit snaps',evidence_version:'recorded-participation-v3',unknown_games:0,
  active,absent,sample_window:sampleWindow,recent_window:{version:'participation-recent-30d-v1',
    since:'2026-08-31',cutoff:'2026-09-30',active,absent,unknown_games:0,sample_window:sampleWindow}}));
const base={id:'A',player:'Archive Player',team:'KC',opponent:'BUF',sport:'nfl',
  home_team:'Kansas City Chiefs',away_team:'Buffalo Bills',game_id:'game',prop_type:'pass_yds',
  line:249.5,direction:'over',true_prob:.6,american_odds:100,push_probability:0,sportsbook:'draftkings',
  model_version:'empirical-jeffreys-v4-nfl-history-v1',history_policy_version:'nfl-explicit-receiving-v1',
  sample_size:40,mean_stat:260,confidence_interval:[.55,.65],kelly_fraction:.01,gated:false,
  forecast_cutoff:'2026-09-30',trade_plan:[],injury_flags:{},market_type:'player_pass_yds',
  snapped_at:stamp,history_observed_before:stamp,captured_at:stamp,
  game_start_time:new Date(now+2*3_600_000).toISOString(),
  availability:{status:'observed',roster_confirmed:true,subject_status:'Not listed on injury report',
    probability_adjusted:false,captured_at:stamp,team:'KC',teammates:reports,context_splits:splits,
    source_url:injuryUrl,source_sha256:'a'.repeat(64),
    roster_source_url:'https://site.api.espn.com/apis/site/v2/sports/football/nfl/teams/12/roster',
    roster_source_sha256:'b'.repeat(64)}};
const metadata={generated_at:stamp,signals:[],games:[]};
const records=Array.from({length:100},(_,index)=>({...base,id:`context-${index}`}));
const nodeCount=value=>1+(value&&typeof value==='object'
  ? Object.values(value).reduce((sum,item)=>sum+nodeCount(item),0) : 0);

test('high-context archive pages honor both packet bounds and continue every original row',()=>{
  const delivered=[];
  let offset=0,complete=false,pages=0;
  while(!complete) {
    const params=new URLSearchParams({sport:'nfl',view:'library',offset:String(offset),limit:'100'});
    if(offset) params.set('revision',revision);
    const request=forecastRequest(new URL('https://example.test/api/signals?'+params));
    const data={rows:records.slice(offset,offset+request.limit).map(signal=>({payload:{...metadata,signals:[signal]}})),
      profiles:{},total_count:records.length,revision,metadata,invalid_envelopes:0,window_complete:true};
    const packet=forecastPage(data,request,now);
    assert.equal(packet.invalid_signals,0);
    assert.ok(Buffer.byteLength(JSON.stringify(packet))<=1024*1024-4096);
    assert.ok(nodeCount(packet)<=50_000);
    assert.doesNotThrow(()=>canonicalForecastDisplayJson(packet));
    assert.equal(packet.pagination.offset,offset);
    assert.equal(packet.pagination.revision,revision);
    for(const signal of packet.signals) {
      assert.equal(signal.availability.teammates.length,64);
      assert.equal(signal.availability.context_splits.length,8);
      assert.deepEqual(signal.availability.context_splits[0].recent_window,splits[0].recent_window);
      delivered.push(signal.id);
    }
    pages++;
    complete=packet.pagination.complete;
    if(!complete) {
      assert.ok(packet.pagination.next_offset>offset);
      assert.equal(packet.pagination.next_offset-offset,packet.signals.length);
      offset=packet.pagination.next_offset;
    } else assert.equal(packet.pagination.next_offset,null);
    assert.ok(pages<=100);
  }
  assert.ok(pages>1);
  assert.deepEqual(delivered,records.map(signal=>signal.id));
});
