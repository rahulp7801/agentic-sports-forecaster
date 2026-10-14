import test from 'node:test';
import assert from 'node:assert/strict';
import {spawnSync} from 'node:child_process';
import {fileURLToPath} from 'node:url';
import {releaseController,guardState,configuredKeys,recoveryReceipt,POLICY,PROJECT,TEAM,ORIGIN,REQUIRED_KEYS,PROBE_NAME,PROBE_HEADER,probePolicy,probeCanary} from '../private-dashboard-release.mjs';
import {requiredHtmlMarkers,requiredCssMarkers} from '../../../frontend/scripts/verify-production.mjs';
const current='a'.repeat(40),old='b'.repeat(40);
const headers={
 'x-content-type-options':'nosniff','x-frame-options':'DENY','referrer-policy':'strict-origin-when-cross-origin',
 'cross-origin-opener-policy':'same-origin','cross-origin-resource-policy':'same-origin','x-dns-prefetch-control':'off',
 'origin-agent-cluster':'?1','x-permitted-cross-domain-policies':'none','cache-control':'no-store',
 'cdn-cache-control':'no-store','vercel-cdn-cache-control':'no-store',
 'strict-transport-security':'max-age=63072000; includeSubDomains','permissions-policy':'camera=(), microphone=()',
 'content-security-policy':"default-src 'self'; script-src 'self' 'nonce-YWJjZA==' 'strict-dynamic'; connect-src 'self'; object-src 'none'; base-uri 'self'; form-action 'self'; frame-ancestors 'none'",
};
const rate={id:'rule_existing_rate',name:'Existing independent rate rule',active:true,conditionGroup:[{conditions:[{type:'path',op:'pre',value:'/api/'}]}],action:{mitigate:{action:'rate_limit',rateLimit:{limit:240,window:60,keys:['ip_address']}}}};
const initial=()=>({ownerId:TEAM,projectKey:PROJECT+'#active',firewallEnabled:true,version:2,updatedAt:'old',changes:[],crs:{sqli:{active:false,action:'log'}},ips:[],rules:[structuredClone(rate),{...structuredClone(POLICY),valid:true,validationErrors:null}]});
function fixture({guard=true,fault=()=>null,verify,now}={}) {
 const state=initial();if(!guard)state.rules.pop();const calls=[],events=[],receipts=[];
 const fetcher=async(url,options={})=>{
  url=new URL(url);const requestHeaders=new Headers(options.headers);const method=options.method ?? 'GET';const body=options.body?JSON.parse(options.body):null;calls.push({url:url.href,method,body,headers:options.headers,redirect:options.redirect,signal:options.signal});events.push(method+' '+(body?.action ?? url.pathname));
  const changed=await fault({url,options,state,body});if(changed)return changed;
  if(url.origin==='https://api.vercel.com') {
   assert.equal(requestHeaders.get('authorization'),'Bearer private-fixture');assert.equal(options.redirect,'error');assert.ok(options.signal instanceof AbortSignal);
   if(url.pathname==='/v2/teams/'+TEAM)return Response.json({id:TEAM,billing:{plan:'hobby'}});
   if(url.pathname==='/v9/projects/'+PROJECT)return Response.json({id:PROJECT,rootDirectory:'frontend'});
   if(url.pathname.startsWith('/v13/deployments/'))return Response.json({projectId:PROJECT,readyState:'READY',target:'production',meta:{sportsbetCommit:current}});
   if(url.pathname==='/v9/projects/'+PROJECT+'/env')return Response.json({envs:REQUIRED_KEYS.map(key=>({key,target:['production']}))});
   if(url.pathname.endsWith('/config/active'))return Response.json(state);
   if(method==='PATCH') {
    assert.equal(url.pathname,'/v1/security/firewall/config');assert.equal(url.searchParams.get('projectId'),PROJECT);assert.equal(url.searchParams.get('teamId'),TEAM);
    if(body.action==='rules.remove'){assert.ok(state.rules.some(rule=>rule.id===body.id));state.rules=state.rules.filter(rule=>rule.id!==body.id);}
    else if(body.action==='rules.insert'){assert.equal(body.id,null);assert.equal(body.value.action.mitigate.action,'deny');state.rules.push({...structuredClone(body.value),id:body.value.name===PROBE_NAME?'rule_private_diagnostic_Probe1':'rule_close_live_dashboard_pending_owner_o_auth_release_Restore1',valid:true,validationErrors:null});}
    else assert.fail('Unexpected firewall operation');state.version++;return Response.json(state);
   }
   assert.fail('Unexpected provider path');
  }
  assert.equal(url.origin,ORIGIN);assert.equal(requestHeaders.get('authorization'),null);assert.equal(options.redirect,'manual');
  const path=url.pathname;
  if(path==='/')return new Response('<link rel="stylesheet" href="/app.css">'+requiredHtmlMarkers.join(' '),{headers});
  if(path==='/app.css')return new Response(requiredCssMarkers.join(' '),{headers});
  if(path==='/login')return new Response('Owner access',{headers});
  if(path==='/api/auth/csrf')return Response.json({csrfToken:'fixture-token-'.repeat(3)},{headers:{...headers,'set-cookie':'__Host-next-auth.csrf-token=fixture; Path=/; Secure; HttpOnly; SameSite=Lax'}});
  if(path==='/api/auth/providers')return Response.json({github:{id:'github',type:'oauth'}},{headers});
  if(path==='/.env')return new Response(null,{status:404,headers});
  const diagnostic=state.rules.find(rule=>rule.name===PROBE_NAME),canary=path.startsWith('/private-release-check-'),protectedPath=path.startsWith('/api/') || path.startsWith('/terminal') || path.endsWith('.json');if((protectedPath && state.rules.some(rule=>rule.name===POLICY.name)) || ((protectedPath || canary) && diagnostic && requestHeaders.get(PROBE_HEADER)!==diagnostic.conditionGroup[0].conditions.at(-1).value))return new Response(null,{status:403,headers});
  if(canary)return new Response(null,{status:404,headers});
  if(path==='/api/waitlist')return Response.json({error:'Request rejected.'},{status:method==='POST'?403:405,headers});
  if(path.startsWith('/terminal'))return new Response(null,{status:307,headers:{...headers,location:'/login'}});
  if(method==='POST' || requestHeaders.get('origin'))return Response.json({error:'Request rejected.'},{status:403,headers});
  if(url.searchParams.getAll('sport').length>1)return Response.json({error:'Request rejected.'},{status:400,headers});
  return Response.json({error:'Owner authentication required.'},{status:401,headers});
 };
 const controller=releaseController({token:'private-fixture',fetcher,wait:async()=>{},...(verify?{verify}: {}),...(now?{now}: {})});
 const receipt=value=>{events.push('receipt '+value.status);receipts.push(value);};
 return {controller,state,calls,events,receipts,receipt};
}

test('contained preflight attests project, configuration, active policy and actual denied paths without mutation',async()=>{
 const f=fixture();assert.deepEqual(await f.controller.preflight(),{contained:true,enforced:false,firewallVersion:2});assert.equal(f.calls.filter(call=>call.method==='PATCH').length,0);
 assert.ok(f.calls.some(call=>call.url===ORIGIN+'/terminal'));assert.deepEqual(f.state.rules[0],rate);
});
test('subsequent private deployment is contained before replacing the live app',async()=>{
 const f=fixture({guard:false});const before=guardState(f.state).digest;assert.deepEqual(await f.controller.preflight(),{contained:true,enforced:true,firewallVersion:3});assert.equal(guardState(f.state).digest,before);assert.equal(f.calls.filter(call=>call.body).length,1);assert.equal(f.calls.find(call=>call.body).body.action,'rules.insert');
});
test('unsafe old app cannot become an attested deployment merely because a guard is absent',async()=>{
 const f=fixture({guard:false,fault:({url})=>url.origin===ORIGIN && url.pathname==='/api/scans'?Response.json({private:'leak'},{headers}):null});await assert.rejects(f.controller.preflight(),/unexpected HTTP 200/);assert.equal(f.calls.filter(call=>call.body).length,0);
});
test('complete real verifier releases only the scoped deny rule and preserves every unrelated setting',async()=>{
 const f=fixture();const before=guardState(f.state).digest;const result=await f.controller.finish({current,receipt:f.receipt});assert.deepEqual(result,{verified:true,transitioned:true,current});assert.equal(guardState(f.state).digest,before);assert.equal(guardState(f.state).guard,null);assert.deepEqual(f.receipts.map(value=>value.status),['pending','verified']);assert.ok(f.events.indexOf('receipt pending')<f.events.indexOf('PATCH rules.remove'));assert.deepEqual(f.state.rules[0],rate);
 for(const call of f.calls.filter(call=>new URL(call.url).origin===ORIGIN))assert.equal(new Headers(call.headers).get('authorization'),null);
 const mutations=f.calls.filter(call=>call.body);assert.deepEqual(mutations.map(call=>call.body.action),['rules.insert','rules.remove','rules.remove']);assert.equal(mutations[0].body.value.name,PROBE_NAME);assert.equal(mutations[1].body.id,POLICY.id);assert.equal(mutations[2].body.id,'rule_private_diagnostic_Probe1');
});
for(const fault of ['owner','project','disabled','version','drift','duplicate','invalid','unknown-property'])test('firewall attestation rejects '+fault,()=>{
 const config=initial();if(fault==='owner')config.ownerId='team_other';if(fault==='project')config.projectKey='prj_other#active';if(fault==='disabled')config.firewallEnabled=false;if(fault==='version')config.version=NaN;if(fault==='drift')config.rules[1].conditionGroup=[];if(fault==='duplicate')config.rules.push(structuredClone(config.rules[1]));if(fault==='invalid')config.rules[1].valid=false;if(fault==='unknown-property')config.rules[1].unexpectedBypass=true;assert.throws(()=>guardState(config));
});
test('provider-generated recovery identifier retains the exact reviewed policy',()=>{const config=initial();config.rules[1].id='rule_close_live_dashboard_pending_owner_o_auth_release_Recovery2';assert.ok(guardState(config).guard);});
test('production environment needs exactly one unbranched entry for every required key',()=>{
 const envs=REQUIRED_KEYS.map(key=>({key,target:['production']}));configuredKeys(envs);
 for(const key of REQUIRED_KEYS){assert.throws(()=>configuredKeys(envs.filter(env=>env.key!==key)),error=>error.message.includes(key));assert.throws(()=>configuredKeys([...envs,{key,target:['production']}]));}
 assert.throws(()=>configuredKeys(envs.map(env=>({...env,gitBranch:'unreviewed'}))));assert.throws(()=>configuredKeys(envs.map(env=>({...env,target:['preview']}))));
});
for(const fault of ['old-commit','wrong-project','wrong-root','missing-env','stale-home','broken-login','broken-csrf','insecure-cookie','extra-provider','open-guard'])test('precondition '+fault+' does not remove containment',async()=>{
 const f=fixture({fault:({url})=>{
  if(fault==='old-commit' && url.pathname.startsWith('/v13/deployments/'))return Response.json({projectId:PROJECT,readyState:'READY',target:'production',meta:{sportsbetCommit:old}});
  if(fault==='wrong-project' && url.pathname.startsWith('/v13/deployments/'))return Response.json({projectId:'prj_other',readyState:'READY',target:'production',meta:{sportsbetCommit:current}});
  if(fault==='wrong-root' && url.pathname==='/v9/projects/'+PROJECT)return Response.json({id:PROJECT,rootDirectory:'.'});
  if(fault==='missing-env' && url.pathname.endsWith('/env'))return Response.json({envs:[]});
  if(fault==='stale-home' && url.origin===ORIGIN && url.pathname==='/')return new Response('Old home',{headers});
  if(fault==='broken-login' && url.pathname==='/login')return new Response('missing',{headers});
  if(fault==='broken-csrf' && url.pathname==='/api/auth/csrf')return Response.json({}, {status:503,headers});
  if(fault==='insecure-cookie' && url.pathname==='/api/auth/csrf')return Response.json({csrfToken:'x'.repeat(32)},{headers});
  if(fault==='extra-provider' && url.pathname==='/api/auth/providers')return Response.json({github:{id:'github',type:'oauth'},other:{id:'other',type:'oauth'}},{headers});
  if(fault==='open-guard' && url.pathname==='/api/scans')return Response.json({}, {headers});return null;
 }});await assert.rejects(f.controller.finish({current,receipt:f.receipt}),/containment was not removed/);assert.equal(f.calls.filter(call=>call.body).length,0);assert.ok(guardState(f.state).guard);
});
test('fresh firewall drift immediately before removal fails closed',async()=>{
 let reads=0;const f=fixture({fault:({url,state})=>{if(url.pathname.endsWith('/config/active') && ++reads===2)state.rules[0].action.mitigate.rateLimit.limit=241;return null;}});await assert.rejects(f.controller.finish({current,receipt:f.receipt}),/containment was not removed/);assert.equal(f.calls.filter(call=>call.body).length,0);
});
test('a leaking app is rejected while public diagnostic containment remains active',async()=>{
 const f=fixture({fault:({url,options,state})=>url.origin===ORIGIN && url.pathname==='/api/scans' && new Headers(options.headers).has(PROBE_HEADER) && !state.rules.some(rule=>rule.name===POLICY.name)?Response.json({leak:'fixture'},{headers}):null});await assert.rejects(f.controller.finish({current,receipt:f.receipt}),/containment restored/);assert.ok(guardState(f.state).guard);assert.deepEqual(f.calls.filter(call=>call.body).map(call=>call.body.action),['rules.insert','rules.remove','rules.insert','rules.remove']);assert.deepEqual(f.receipts.map(value=>value.status),['pending','restored']);assert.deepEqual(f.state.rules[0],rate);
});
test('ambiguous removal timeout is reconciled and safely reclosed',async()=>{
 const f=fixture({fault:({body,state})=>{if(body?.action==='rules.remove' && body.id===POLICY.id){state.rules=state.rules.filter(rule=>rule.name!==POLICY.name);state.version++;throw Error('private fixture response');}return null;}});await assert.rejects(f.controller.finish({current,receipt:f.receipt}),/containment restored/);assert.ok(guardState(f.state).guard);assert.deepEqual(f.receipts.map(value=>value.status),['pending','restored']);
});
test('provider refusal before effective removal does not add a duplicate recovery rule',async()=>{
 const f=fixture({fault:({body})=>body?.action==='rules.remove' && body.id===POLICY.id?new Response('provider-secret',{status:403}):null});await assert.rejects(f.controller.finish({current,receipt:f.receipt}),/containment restored/);assert.equal(f.calls.filter(call=>call.body?.action==='rules.insert' && call.body.value.name===POLICY.name).length,0);assert.equal(f.state.rules.length,2);
});
test('failed restoration raises operator recovery state rather than reporting closed access',async()=>{
 const f=fixture({verify:async()=>{throw Error('private fixture credentials');},fault:({body})=>body?.action==='rules.insert' && body.value.name===POLICY.name?new Response('provider-secret',{status:402}):null});await assert.rejects(f.controller.finish({current,receipt:f.receipt}),error=>/requires operator attention/.test(error.message) && !error.message.includes('credentials') && !error.message.includes('provider-secret'));assert.deepEqual(f.receipts.map(value=>value.status),['pending']);
});
test('post-transition unrelated firewall drift triggers scoped recovery without overwriting that setting',async()=>{
 let reads=0;const f=fixture({fault:({url,state})=>{if(url.pathname.endsWith('/config/active') && ++reads===6)state.crs.sqli.active=true;return null;}});await assert.rejects(f.controller.finish({current,receipt:f.receipt}),/containment restored/);assert.ok(guardState(f.state).guard);assert.equal(f.state.crs.sqli.active,true);assert.deepEqual(f.state.rules[0],rate);
});
test('recovery receipts bind pending work to the production project and exact workflow commit',()=>{
 const value={status:'pending',current,project:PROJECT,team:TEAM};assert.equal(recoveryReceipt(value,current),true);for(const status of ['verified','restored'])assert.equal(recoveryReceipt({...value,status},current),false);assert.equal(recoveryReceipt(null,current),false);
 for(const change of [{current:old},{team:'team_other'},{project:'prj_other'},{status:'ignored'}])assert.throws(()=>recoveryReceipt({...value,...change},current));
});
test('local or branch CLI invocation cannot mutate production',()=>{
 const path=fileURLToPath(new URL('../private-dashboard-release.mjs',import.meta.url));for(const mode of ['preflight','finish','recover']){const result=spawnSync(process.execPath,[path,mode],{encoding:'utf8',env:{...process.env,GITHUB_ACTIONS:'false',GITHUB_REF:'refs/heads/master',GITHUB_SHA:current,VERCEL_TOKEN:'private-do-not-log'}});assert.equal(result.status,1);assert.match(result.stderr,/protected production execution required/);assert.ok(!result.stderr.includes('private-do-not-log'));}
 assert.throws(()=>releaseController({token:'fixture',project:'prj_other'}));assert.throws(()=>releaseController({token:'fixture',team:'team_other'}));
});

test('nonfree team plans block transition before any firewall mutation',async()=>{
 const f=fixture({fault:({url})=>url.pathname==='/v2/teams/'+TEAM?Response.json({id:TEAM,billing:{plan:'pro'}}):null});await assert.rejects(f.controller.preflight(),/free Hobby plan/);await assert.rejects(f.controller.finish({current}),/containment was not removed/);assert.equal(f.calls.filter(call=>call.body).length,0);
});
test('unavailable free rule capacity leaves original containment intact',async()=>{
 const f=fixture();f.state.rules.push({...structuredClone(rate),id:'rule_operator_added'});await assert.rejects(f.controller.finish({current}),/containment was not removed/);assert.equal(f.calls.filter(call=>call.body).length,0);
});
test('diagnostic policy retains public deny in every original OR group',()=>{
 const secret='f'.repeat(64),rule=probePolicy(secret);assert.equal(rule.action.mitigate.action,'deny');assert.equal(rule.conditionGroup.length,POLICY.conditionGroup.length+1);
 for(let i=0;i<POLICY.conditionGroup.length;i++){assert.deepEqual(rule.conditionGroup[i].conditions.slice(0,-1),POLICY.conditionGroup[i].conditions);assert.deepEqual(rule.conditionGroup[i].conditions.at(-1),{type:'header',key:PROBE_HEADER,op:'eq',neg:true,value:secret});}
 assert.throws(()=>probePolicy('short'));
 const state=initial();state.rules.push({...rule,id:'rule_probe_fixture',unexpectedBypass:true});assert.throws(()=>guardState(state));
});
test('interrupted diagnostic state is reclosed before the next release preflight',async()=>{
 const f=fixture({guard:false});f.state.rules.push({...probePolicy('f'.repeat(64)),id:'rule_probe_fixture'});await f.controller.preflight();assert.ok(guardState(f.state).guard);assert.equal(guardState(f.state).diagnostic,null);assert.deepEqual(f.calls.filter(call=>call.body).map(call=>call.body.action),['rules.insert','rules.remove']);assert.deepEqual(f.state.rules[0],rate);
});
test('ambiguous diagnostic insertion never removes the original deny guard',async()=>{
 const f=fixture({fault:({body,state})=>{if(body?.action==='rules.insert' && body.value.name===PROBE_NAME){state.rules.push({...body.value,id:'rule_probe_ambiguous'});state.version++;throw Error('private transport details');}return null;}});await assert.rejects(f.controller.finish({current,receipt:f.receipt}),/containment restored/);assert.ok(guardState(f.state).guard);assert.equal(guardState(f.state).diagnostic,null);assert.equal(f.calls.filter(call=>call.body?.id===POLICY.id).length,0);
});
test('ambiguous recovery insertion is reconciled without duplicate writes',async()=>{
 const f=fixture({verify:async()=>{throw Error('fixture access failure');},fault:({body,state})=>{if(body?.action==='rules.insert' && body.value.name===POLICY.name){state.rules.push({...body.value,id:'rule_close_live_dashboard_pending_owner_o_auth_release_Ambiguous'});state.version++;throw Error('private response');}return null;}});await assert.rejects(f.controller.finish({current,receipt:f.receipt}),/containment restored/);assert.ok(guardState(f.state).guard);assert.equal(guardState(f.state).diagnostic,null);assert.equal(f.calls.filter(call=>call.body?.action==='rules.insert' && call.body.value.name===POLICY.name).length,1);
});
test('verification deadline expiry restores public containment',async()=>{
 let clock=0;const f=fixture({now:()=>clock,verify:async options=>{clock=120001;await options.fetchImpl(ORIGIN+'/api/scans');}});await assert.rejects(f.controller.finish({current,receipt:f.receipt}),/containment restored/);assert.ok(guardState(f.state).guard);assert.equal(guardState(f.state).diagnostic,null);
});
for(const stylesheet of ['https://attacker.invalid/app.css',ORIGIN+'.attacker.invalid/app.css',ORIGIN+'@attacker.invalid/app.css',ORIGIN.replace('https:','http:')+'/app.css'])test('diagnostic secret is never forwarded to stylesheet origin '+new URL(stylesheet).origin,async()=>{
 const untrustedOrigin=new URL(stylesheet).origin;
 const f=fixture({verify:async options=>options.fetchImpl(stylesheet)});await assert.rejects(f.controller.finish({current,receipt:f.receipt}),/containment restored/);assert.equal(f.calls.some(call=>new URL(call.url).origin===untrustedOrigin),false);assert.ok(guardState(f.state).guard);assert.equal(guardState(f.state).diagnostic,null);
});

test('missing-header canary semantics are checked before removing the original guard',async()=>{
 const f=fixture({fault:({url,options})=>url.pathname.startsWith('/private-release-check-') && !new Headers(options.headers).has(PROBE_HEADER)?new Response(null,{status:404,headers}):null});await assert.rejects(f.controller.finish({current,receipt:f.receipt}),/containment restored/);assert.equal(f.calls.some(call=>call.body?.id===POLICY.id),false);assert.ok(guardState(f.state).guard);assert.equal(guardState(f.state).diagnostic,null);
});
test('diagnostic canary remains a public nondata route and requires the exact verification header',()=>{
 const secret='f'.repeat(64),rule=probePolicy(secret),canary=rule.conditionGroup.at(-1);assert.deepEqual(canary.conditions[0],{type:'path',op:'eq',neg:false,value:probeCanary(secret)});assert.ok(!probeCanary(secret).startsWith('/api/') && !probeCanary(secret).startsWith('/terminal') && !probeCanary(secret).endsWith('.json'));
});
