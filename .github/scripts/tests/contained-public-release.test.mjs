import test from 'node:test';
import assert from 'node:assert/strict';
import {spawnSync} from 'node:child_process';
import {fileURLToPath} from 'node:url';
import {containedPublicController,executionContext,waitlistConfigured,REPOSITORY,REPOSITORY_ID,
 OWNER_ID,WORKFLOW_ID,WORKFLOW_PATH,REQUIRED_JOBS,ACTION_CHECKS,CHECK_APPS,PUBLIC_REQUIRED_KEYS} from '../contained-public-release.mjs';
import {PROJECT,TEAM,ORIGIN,POLICY,PROBE_NAME} from '../private-dashboard-release.mjs';

const current='a'.repeat(40),old='b'.repeat(40),prHead='c'.repeat(40),tree='d'.repeat(40),runId='123456789';
const context={current,runId,runAttempt:1};
const baseEnv={GITHUB_ACTIONS:'true',GITHUB_EVENT_NAME:'workflow_dispatch',GITHUB_REF:'refs/heads/master',
 GITHUB_REPOSITORY:REPOSITORY,GITHUB_REPOSITORY_ID:String(REPOSITORY_ID),GITHUB_ACTOR_ID:String(OWNER_ID),
 PUBLIC_LANDING_ONLY:'true',FORCE_FRONTEND_DEPLOY:'false',GITHUB_SHA:current,GITHUB_RUN_ID:runId,GITHUB_RUN_ATTEMPT:'1'};
const rate={id:'rule_existing_rate',name:'Existing rate rule',active:true,
 conditionGroup:[{conditions:[{type:'path',op:'pre',value:'/api/'}]}],
 action:{mitigate:{action:'rate_limit',rateLimit:{limit:240,window:60,keys:['ip_address']}}}};
function fixture({fault=()=>null,access,verify}={}) {
 const state={ownerId:TEAM,projectKey:PROJECT+'#active',firewallEnabled:true,version:2,
  rules:[structuredClone(rate),structuredClone(POLICY)]};
 const repository={id:REPOSITORY_ID,full_name:REPOSITORY,private:false,default_branch:'master',owner:{id:OWNER_ID}};
 const run={id:Number(runId),run_attempt:1,event:'workflow_dispatch',head_sha:current,head_branch:'master',
  workflow_id:WORKFLOW_ID,path:WORKFLOW_PATH,
  repository:{id:REPOSITORY_ID},actor:{id:OWNER_ID},triggering_actor:{id:OWNER_ID},status:'in_progress'};
 const jobs=REQUIRED_JOBS.map((name,index)=>({id:index+1,name,head_sha:current,run_id:Number(runId),status:'completed',conclusion:'success',
  check_run_url:'https://api.github.com/repos/'+REPOSITORY+'/check-runs/'+(ACTION_CHECKS.indexOf(name)+1)}));
 const checks=ACTION_CHECKS.map((name,index)=>({id:index+1,name,head_sha:current,status:'completed',conclusion:'success',app:{...CHECK_APPS.actions}}));
 const prChecks=[...ACTION_CHECKS.map((name,index)=>({id:index+101,name,head_sha:prHead,status:'completed',conclusion:'success',app:{...CHECK_APPS.actions}})),
  {id:200,name:'CodeQL',head_sha:prHead,status:'completed',conclusion:'success',app:{...CHECK_APPS.aggregate}}];
 const pr={number:365,merge_commit_sha:current,merged:true,state:'closed',merged_at:'2026-10-18T10:00:00Z',
  base:{ref:'master',repo:{id:REPOSITORY_ID,full_name:REPOSITORY}},head:{sha:prHead,repo:{id:REPOSITORY_ID,full_name:REPOSITORY}}};
 const associated=[structuredClone(pr)],trees={[current]:tree,[prHead]:tree};
 const envs=PUBLIC_REQUIRED_KEYS.map(key=>({key,target:['production']})),calls=[];
 let deployed=old,accessCalls=0,verifyCalls=0;
 const fetcher=async(url,options={})=>{
  const parsed=new URL(url),headers=new Headers(options.headers);calls.push({url:parsed.href,method:options.method ?? 'GET',headers});
  const changed=await fault({url:parsed,options,state,repository,run,jobs,checks,prChecks,pr,associated,trees,envs,calls});if(changed)return changed;
  if(parsed.origin==='https://api.vercel.com' || parsed.origin==='https://api.github.com') {
   assert.equal(options.method,'GET');assert.equal(options.body,undefined);assert.equal(options.redirect,'error');
   assert.ok(options.signal instanceof AbortSignal);
   assert.equal(headers.get('authorization'),'Bearer '+(parsed.origin==='https://api.vercel.com'?'vercel-fixture':'github-fixture'));
  }
  if(parsed.origin==='https://api.vercel.com') {
   if(parsed.pathname==='/v1/security/firewall/config/active')return Response.json(state);
   if(parsed.pathname==='/v2/teams/'+TEAM)return Response.json({id:TEAM,billing:{plan:'hobby'}});
   if(parsed.pathname==='/v9/projects/'+PROJECT)return Response.json({id:PROJECT,rootDirectory:'frontend'});
   if(parsed.pathname.startsWith('/v13/deployments/'))return Response.json({projectId:PROJECT,readyState:'READY',target:'production',meta:{sportsbetCommit:deployed}});
   if(parsed.pathname==='/v9/projects/'+PROJECT+'/env') {
    assert.equal(parsed.searchParams.get('decrypt'),'false');return Response.json({envs});
   }
   assert.fail('Unexpected control-plane route');
  }
  if(parsed.origin==='https://api.github.com') {
   assert.equal(headers.get('x-github-api-version'),'2026-03-10');
   const prefix='/repos/'+REPOSITORY;
   if(parsed.pathname===prefix)return Response.json(repository);
   if(parsed.pathname===prefix+'/git/ref/heads/master')return Response.json({ref:'refs/heads/master',object:{type:'commit',sha:current}});
   if(parsed.pathname===prefix+'/actions/runs/'+runId)return Response.json(run);
   if(parsed.pathname===prefix+'/actions/runs/'+runId+'/jobs')return Response.json({total_count:jobs.length,jobs});
   if(parsed.pathname===prefix+'/commits/'+current+'/pulls')return Response.json(associated);
   if(parsed.pathname===prefix+'/pulls/365')return Response.json(pr);
   if(parsed.pathname.startsWith(prefix+'/git/commits/')) {
    const sha=parsed.pathname.split('/').at(-1);return Response.json({sha,tree:{sha:trees[sha]}});
   }
   if([prefix+'/commits/'+current+'/check-runs',prefix+'/commits/'+prHead+'/check-runs'].includes(parsed.pathname)) {
    assert.equal(parsed.searchParams.get('filter'),'all');const values=parsed.pathname.includes('/'+prHead+'/')?prChecks:checks;
    return Response.json({total_count:values.length,check_runs:values});
   }
   assert.fail('Unexpected repository route');
  }
  assert.equal(parsed.origin,ORIGIN);assert.equal(headers.get('authorization'),null);assert.equal(headers.get('cookie'),null);
  assert.equal(headers.get('x-private-release-probe'),null);assert.equal(options.credentials,'omit');assert.equal(options.redirect,'manual');
  return new Response(null,{status:403,headers:{'Cache-Control':'no-store'}});
 };
 const controller=containedPublicController({token:'vercel-fixture',githubToken:'github-fixture',context,fetcher,
  verifyAccess:async options=>{accessCalls++;if(access)return access(options);const response=await options.fetchImpl(options.base+'/terminal');assert.equal(response.status,403);},
  verify:async options=>{verifyCalls++;if(verify)return verify(options);const response=await options.fetchImpl(options.base+'/api/signals');assert.equal(response.status,403);}});
 return {controller,state,repository,run,jobs,checks,prChecks,pr,associated,trees,envs,calls,deploy:()=>{deployed=current;},counts:()=>({accessCalls,verifyCalls})};
}

test('public release requires one explicit owner master dispatch, not pushes, PRs or reruns',()=>{
 assert.deepEqual(executionContext(baseEnv),context);
 for(const [key,value] of Object.entries({GITHUB_ACTIONS:'false',GITHUB_EVENT_NAME:'push',GITHUB_REF:'refs/heads/review',
  GITHUB_REPOSITORY:'other/repo',GITHUB_REPOSITORY_ID:'1',GITHUB_ACTOR_ID:'1',PUBLIC_LANDING_ONLY:'false',
  FORCE_FRONTEND_DEPLOY:'true',GITHUB_SHA:'invalid',GITHUB_RUN_ID:'1;command',GITHUB_RUN_ATTEMPT:'2'})) {
  assert.throws(()=>executionContext({...baseEnv,[key]:value}),/explicit_owner_master_dispatch_required/);
 }
});

test('current origin/session/waitlist production metadata stays unique; missing OAuth keys never imply owner readiness',()=>{
 const configured=PUBLIC_REQUIRED_KEYS.map(key=>({key,target:['production']}));
 waitlistConfigured(configured);
 assert.deepEqual(PUBLIC_REQUIRED_KEYS,['NEXTAUTH_URL','NEXTAUTH_SECRET','WAITLIST_DATABASE_URL']);
 for(const key of PUBLIC_REQUIRED_KEYS) {
  for(const envs of [configured.filter(item=>item.key!==key),
   configured.map(item=>item.key===key?{...item,target:['preview']}:item),
   configured.map(item=>item.key===key?{...item,gitBranch:'review'}:item),
   [...configured,{key,target:['production']}]])assert.throws(()=>waitlistConfigured(envs));
 }
});

test('preflight and finish retain exact containment, perform only control-plane GETs and report owner auth false',async()=>{
 const f=fixture(),before=structuredClone(f.state),receipt=await f.controller.preflight();
 assert.equal(receipt.status,'prepared');assert.equal(receipt.current,current);assert.equal(receipt.previousDeployment,old);
 assert.equal(receipt.runId,runId);assert.equal(receipt.guardId,POLICY.id);
 f.deploy();assert.deepEqual(await f.controller.finish({current,receipt}),{status:'public_surface_verified',current,
  project:PROJECT,team:TEAM,containment_active:true,owner_authentication_verified:false});
 assert.deepEqual(f.state,before);assert.deepEqual(f.counts(),{accessCalls:1,verifyCalls:1});
 assert.ok(f.calls.every(call=>call.method==='GET'));
 assert.ok(!f.calls.some(call=>call.url.includes('/config?') || call.headers.has('x-private-release-probe')));
});

for(const fault of ['absent','inactive','drift','disabled','diagnostic','unrelated','version'])test('missing or changed containment stops '+fault,async()=>{
 const f=fixture();const receipt=await f.controller.preflight();f.deploy();
 if(fault==='absent')f.state.rules.pop();
 if(fault==='inactive')f.state.rules[1].active=false;
 if(fault==='drift')f.state.rules[1].conditionGroup=[];
 if(fault==='disabled')f.state.firewallEnabled=false;
 if(fault==='diagnostic')f.state.rules.push({...structuredClone(POLICY),id:'rule_unreviewed',name:PROBE_NAME});
 if(fault==='unrelated')f.state.rules[0].action.mitigate.rateLimit.limit++;
 if(fault==='version')f.state.version++;
 await assert.rejects(f.controller.finish({current,receipt}),/Contained public release:/);
 assert.equal(f.counts().verifyCalls,0);assert.ok(f.calls.every(call=>call.method==='GET'));
});

for(const fault of ['repository','private','branch','actor','triggering_actor','run_sha','run_attempt','run_event','run_status','workflow_id','workflow_path'])test('repository or current workflow mismatch rejects '+fault,async()=>{
 const f=fixture({fault:({url,repository,run})=>{
  if(fault==='repository')repository.id=1;if(fault==='private')repository.private=true;
  if(fault==='actor')run.actor.id=1;if(fault==='triggering_actor')run.triggering_actor.id=1;
  if(fault==='run_sha')run.head_sha=old;if(fault==='run_attempt')run.run_attempt=2;
  if(fault==='run_event')run.event='push';if(fault==='run_status')run.status='completed';
  if(fault==='workflow_id')run.workflow_id=1;if(fault==='workflow_path')run.path='.github/workflows/unreviewed.yml';
  if(fault==='branch' && url.pathname.endsWith('/git/ref/heads/master'))return Response.json({ref:'refs/heads/master',object:{type:'commit',sha:old}});
 }});
 await assert.rejects(f.controller.preflight(),/Contained public release:/);assert.equal(f.counts().accessCalls,0);
});

for(const fault of ['missing','failed','running','skipped','sha','run','duplicate','hidden_page'])test('all actual same-run code/schema jobs are required: '+fault,async()=>{
 const f=fixture({fault:({url,jobs})=>{
  if(!url.pathname.endsWith('/jobs'))return;
  if(fault==='missing')jobs.pop();if(fault==='failed')jobs[0].conclusion='failure';
  if(fault==='running')jobs[0].status='in_progress';if(fault==='skipped')jobs[0].conclusion='skipped';
  if(fault==='sha')jobs[0].head_sha=old;if(fault==='run')jobs[0].run_id=1;
  if(fault==='duplicate')jobs.push({...jobs[0]});
  if(fault==='hidden_page')return Response.json({total_count:101,jobs});
 }});await assert.rejects(f.controller.preflight(),/Contained public release:/);
});

for(const fault of ['missing_aggregate','neutral_aggregate','missing_analysis','wrong_app','wrong_slug','sha','duplicate','hidden_page'])test('actual reviewed-head CodeQL aggregate cannot be replaced by analysis success: '+fault,async()=>{
 const f=fixture({fault:({url,prChecks})=>{
  if(!url.pathname.endsWith('/check-runs'))return;
  if(!url.pathname.includes('/'+prHead+'/'))return;
  if(fault==='missing_aggregate')prChecks.pop();if(fault==='neutral_aggregate')prChecks.at(-1).conclusion='neutral';
  if(fault==='missing_analysis')prChecks.shift();if(fault==='wrong_app')prChecks.at(-1).app.id=15368;
  if(fault==='wrong_slug')prChecks.at(-1).app.slug='github-actions';if(fault==='sha')prChecks[0].head_sha=old;
  if(fault==='duplicate')prChecks.push({...prChecks.at(-1),id:201});
  if(fault==='hidden_page')return Response.json({total_count:301,check_runs:prChecks});
 }});await assert.rejects(f.controller.preflight(),/Contained public release:/);
});

for(const fault of ['absent','ambiguous','banned194','unmerged','wrong_merge','base','foreign_head','head_changed','tree'])test('a unique reviewed original-repo squash with identical trees is mandatory: '+fault,async()=>{
 const f=fixture();
 if(fault==='absent')f.associated.length=0;
 if(fault==='ambiguous')f.associated.push({...f.associated[0],number:366});
 if(fault==='banned194')f.associated[0].number=194;
 if(fault==='unmerged')f.pr.merged=false;
 if(fault==='wrong_merge')f.pr.merge_commit_sha=old;
 if(fault==='base')f.pr.base.ref='other';
 if(fault==='foreign_head')f.pr.head.repo.id=1;
 if(fault==='head_changed')f.pr.head.sha=old;
 if(fault==='tree')f.trees[prHead]=old;
 await assert.rejects(f.controller.preflight(),/Contained public release:/);
});

test('master without an aggregate is accepted only through its reviewed identical-tree PR aggregate',async()=>{
 const f=fixture();assert.ok(!f.checks.some(check=>check.name==='CodeQL'));
 await f.controller.preflight();assert.ok(f.calls.some(call=>call.url.includes('/commits/'+prHead+'/check-runs')));
});

test('manual-run CI checks are pinned by their actual check identities, not an older same-head success',async()=>{
 const f=fixture();f.checks.push({...f.checks.find(check=>check.name==='backend'),id:999});
 f.checks.find(check=>check.name==='backend').conclusion='failure';
 await assert.rejects(f.controller.preflight(),/required_exact_head_check_not_successful/);
});

test('all check pages are read from fixed routes without following response URLs',async()=>{
 const f=fixture({fault:({url,checks})=>{
  if(!url.pathname.endsWith('/commits/'+current+'/check-runs'))return;
  const unrelated=Array.from({length:100},(_,i)=>({id:i+1000,name:'unrelated-'+i}));
  return Response.json({total_count:100+checks.length,check_runs:url.searchParams.get('page')==='1'?unrelated:checks,
   next:'https://never-follow.invalid/private'});
 }});await f.controller.preflight();
 assert.ok(f.calls.some(call=>call.url.endsWith('filter=all&per_page=100&page=2')));
 assert.ok(f.calls.every(call=>!call.url.includes('never-follow')));
});

for(const fault of ['paid_plan','project','root','env','deployed','commit_conflict'])test('free pinned platform and exact post-deploy commit required: '+fault,async()=>{
 const f=fixture({fault:({url})=>{
  if(fault==='paid_plan' && url.pathname.startsWith('/v2/teams/'))return Response.json({id:TEAM,billing:{plan:'pro'}});
  if(fault==='project' && url.pathname==='/v9/projects/'+PROJECT)return Response.json({id:'prj_other',rootDirectory:'frontend'});
  if(fault==='root' && url.pathname==='/v9/projects/'+PROJECT)return Response.json({id:PROJECT,rootDirectory:'.'});
  if(fault==='env' && url.pathname.endsWith('/env'))return Response.json({envs:[]});
  if(fault==='commit_conflict' && url.pathname.startsWith('/v13/deployments/'))return Response.json({projectId:PROJECT,readyState:'READY',target:'production',meta:{sportsbetCommit:current,githubCommitSha:old}});
 }});
 if(fault==='deployed') {const receipt=await f.controller.preflight();await assert.rejects(f.controller.finish({current,receipt}),/reviewed_production_commit_not_ready/);}
 else await assert.rejects(f.controller.preflight(),/Contained public release:/);
});

test('receipt identity is bound to current run, commit and exact guard; supplied success flags reject',async()=>{
 const f=fixture(),receipt=await f.controller.preflight();f.deploy();
 for(const changed of [{...receipt,current:old},{...receipt,runId:'2'},{...receipt,runAttempt:2},
  {...receipt,project:'prj_other'},{...receipt,status:'verified'},{...receipt,owner_authentication_verified:true}]) {
  await assert.rejects(f.controller.finish({current,receipt:changed}),/prepared_receipt_/);
 }
});

test('public verification gets no control-plane credential and cannot request external origins or diagnostic bypasses',async()=>{
 for(const probe of [options=>options.fetchImpl('https://never-follow.invalid/'),
  options=>options.fetchImpl(options.base+'/terminal',{headers:{Authorization:'Bearer fixture'}}),
  options=>options.fetchImpl(options.base+'/terminal',{headers:{cookie:'fixture'}}),
  options=>options.fetchImpl(options.base+'/terminal',{headers:{'x-private-release-probe':'fixture'}})]) {
  const f=fixture({access:probe});await assert.rejects(f.controller.preflight(),/contained_access_not_verified/);
 }
});

test('public verification failures retain prepared uncertainty and never retry, recover or mutate',async()=>{
 const f=fixture({verify:async()=>{throw Error('PRIVATE_PROVIDER_RESPONSE');}}),receipt=await f.controller.preflight();f.deploy();
 await assert.rejects(f.controller.finish({current,receipt}),error=>error.message==='Contained public release: public_surface_not_verified');
 assert.deepEqual(f.counts(),{accessCalls:1,verifyCalls:1});assert.equal(receipt.status,'prepared');
 assert.ok(f.calls.every(call=>call.method==='GET'));assert.deepEqual(f.state.rules[1],POLICY);
});

test('post-probe drift and master movement cannot produce successful completion',async()=>{
 let moved=false;
 const f=fixture({verify:async()=>{moved=true;},fault:({url})=>moved && url.pathname.endsWith('/git/ref/heads/master')?
  Response.json({ref:'refs/heads/master',object:{type:'commit',sha:old}}):null});
 const receipt=await f.controller.preflight();f.deploy();await assert.rejects(f.controller.finish({current,receipt}),/current_master_changed/);
});

test('malformed, refused, oversized or thrown metadata never echoes provider bodies',async()=>{
 for(const response of [()=>new Response('PRIVATE_PROVIDER_RESPONSE',{status:403}),
  ()=>new Response('not json'),()=>new Response('x'.repeat(2*1024*1024+1)),
  ()=>{throw Error('PRIVATE_PROVIDER_RESPONSE');}]) {
  const f=fixture({fault:response});await assert.rejects(f.controller.preflight(),error=>
   error.message.startsWith('Contained public release:') && !error.message.includes('PRIVATE_PROVIDER_RESPONSE'));
 }
});

test('CLI refuses an ordinary push before credentials, metadata or deployment can be used',()=>{
 const script=fileURLToPath(new URL('../contained-public-release.mjs',import.meta.url));
 const result=spawnSync(process.execPath,[script,'preflight'],{encoding:'utf8',env:{...process.env,...baseEnv,
  VERCEL_PROJECT_ID:PROJECT,VERCEL_ORG_ID:TEAM,GITHUB_EVENT_NAME:'push',VERCEL_TOKEN:'PRIVATE_FIXTURE_VALUE'}});
 assert.equal(result.status,1);assert.match(result.stderr,/explicit_owner_master_dispatch_required/);
 assert.ok(!result.stderr.includes('PRIVATE_FIXTURE_VALUE'));
});
