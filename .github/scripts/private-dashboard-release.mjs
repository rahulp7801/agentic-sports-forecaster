/** Protected, reversible transition from emergency containment to owner authentication. */
import {readFileSync,writeFileSync,renameSync} from 'node:fs';
import {createHash,randomBytes} from 'node:crypto';
import {pathToFileURL} from 'node:url';
import {deployedCommit,PRODUCTION_HOST} from './deployment-plan.mjs';
import {requiredHtmlMarkers,verifySecurityHeaders,verifyProductionWithRetry} from '../../frontend/scripts/verify-production.mjs';

export const PROJECT='prj_xUgCA0BZejb4GZgeOHuJVQqs6M1M';
export const TEAM='team_IWsRUaGJj5J56jLXwFs3Wzy7';
export const ORIGIN='https://'+PRODUCTION_HOST;
export const POLICY=JSON.parse(readFileSync(new URL('../security/private-dashboard-containment.json',import.meta.url),'utf8'));
export const REQUIRED_KEYS=['NEXTAUTH_URL','NEXTAUTH_SECRET','GITHUB_CLIENT_ID','GITHUB_CLIENT_SECRET','WAITLIST_DATABASE_URL'];
export const PROBE_NAME='Verify owner authentication while public access remains closed';
export const PROBE_HEADER='x-private-release-probe';
export const probeCanary=secret=>'/private-release-check-'+secret.slice(0,32);
export function probePolicy(secret) {
 if(typeof secret!=='string' || !/^[a-f0-9]{64}$/.test(secret))fail('invalid diagnostic secret');
 const {id,...rule}=structuredClone(POLICY);void id;rule.name=PROBE_NAME;rule.description='Temporary diagnostic exception; application owner authentication still applies.';
 const header={type:'header',key:PROBE_HEADER,op:'eq',neg:true,value:secret};
 rule.conditionGroup=rule.conditionGroup.map(group=>({conditions:[...group.conditions,header]}));
 rule.conditionGroup.push({conditions:[{type:'path',op:'eq',neg:false,value:probeCanary(secret)},header]});return rule;
}
function diagnosticRule(rule) {
 const conditions=rule?.conditionGroup?.[0]?.conditions;const secret=Array.isArray(conditions)?conditions.at(-1)?.value:null;
 if(!/^[a-f0-9]{64}$/.test(secret ?? '') || !/^rule_[A-Za-z0-9_]+$/.test(rule?.id ?? '') || rule?.name!==PROBE_NAME || rule.active!==true || rule.valid===false || (rule.validationErrors && !(Array.isArray(rule.validationErrors) && !rule.validationErrors.length)) || Object.keys(rule).some(key=>!['id','name','description','active','conditionGroup','action','valid','validationErrors'].includes(key)))return false;
 return canonical(spec(rule))===canonical(spec(probePolicy(secret)));
}
const sha=value=>typeof value==='string' && /^[a-f0-9]{40}$/.test(value);
const fail=message=>{throw Error('Private release: '+message);};
const canonical=value=>JSON.stringify(sort(value));
function sort(value) {if(Array.isArray(value))return value.map(sort);if(value && typeof value==='object')return Object.fromEntries(Object.keys(value).sort().map(key=>[key,sort(value[key])]));return value;}
function spec(rule) {return {name:rule.name,description:rule.description,active:rule.active,conditionGroup:rule.conditionGroup,action:rule.action};}
function samePolicy(rule) {
 return rule && /^rule_[A-Za-z0-9_]+$/.test(rule.id ?? '') && rule.valid!==false &&
  (!rule.validationErrors || (Array.isArray(rule.validationErrors) && !rule.validationErrors.length)) &&
  Object.keys(rule).every(key=>['id','name','description','active','conditionGroup','action','valid','validationErrors'].includes(key)) &&
  canonical({...spec(rule),active:true})===canonical(spec(POLICY));
}
export function guardState(config) {
 if(config?.ownerId!==TEAM || config.projectKey!==PROJECT+'#active' || config.firewallEnabled!==true ||
  !Number.isSafeInteger(config.version) || config.version<1 || !Array.isArray(config.rules) || config.rules.length>1000 ||
  config.rules.some(rule=>typeof rule?.id!=='string') || new Set(config.rules.map(rule=>rule.id)).size!==config.rules.length)fail('firewall identity is not verified');
 const named=config.rules.filter(rule=>rule.name===POLICY.name || rule.id===POLICY.id);
 if(named.length>1 || (named.length && (!samePolicy(named[0]) || named[0].active!==true)))fail('containment policy has drifted');
 const guard=named[0] ?? null;
 // Capture every unrelated setting/rule, not only the existing IP rate limit.
 const diagnostics=config.rules.filter(rule=>rule.name===PROBE_NAME);
 if(diagnostics.length>1 || diagnostics.some(rule=>!diagnosticRule(rule)))fail('diagnostic containment has drifted');
 const other=structuredClone(config);other.rules=other.rules.filter(rule=>rule.id!==guard?.id && !diagnostics.some(probe=>probe.id===rule.id));
 for(const key of ['id','version','updatedAt','changes','projectKey','ownerId'])delete other[key];
 return {guard,diagnostic:diagnostics[0] ?? null,version:config.version,digest:createHash('sha256').update(canonical(other)).digest('hex')};
}
export function configuredKeys(envs) {
 if(!Array.isArray(envs))fail('production environment metadata unavailable');
 const missing=REQUIRED_KEYS.filter(key=>envs.filter(env=>env.key===key && Array.isArray(env.target) && env.target.includes('production') && !env.gitBranch).length!==1);
 if(missing.length)fail('production settings missing or ambiguous: '+missing.join(', '));
}
export function releaseController({token,project=PROJECT,team=TEAM,fetcher=fetch,wait=ms=>new Promise(resolve=>setTimeout(resolve,ms)),verify=verifyProductionWithRetry,now=Date.now}={}) {
 if(typeof token!=='string' || !token.trim() || /[\r\n]/.test(token) || project!==PROJECT || team!==TEAM)fail('credentials or project identity missing');
 const query='?projectId='+PROJECT+'&teamId='+TEAM;
 async function provider(path,body) {
  let response;try {response=await fetcher('https://api.vercel.com'+path,{method:body?'PATCH':'GET',headers:{Authorization:'Bearer '+token,...(body?{'Content-Type':'application/json'}:{})},...(body?{body:JSON.stringify(body)}:{}),redirect:'error',signal:AbortSignal.timeout(15000)});}catch{fail('provider request unavailable');}
  if(!response.ok)fail('provider request refused (HTTP '+response.status+')');
  try{return await response.json();}catch{fail('provider response invalid');}
 }
 const config=()=>provider('/v1/security/firewall/config/active'+query);
 async function identity(current) {
  const account=await provider('/v2/teams/'+TEAM);
  if(account.id!==TEAM || account.billing?.plan!=='hobby')fail('existing free Hobby plan is not verified');
  const settings=await provider('/v9/projects/'+PROJECT+'?teamId='+TEAM);
  if(settings.id!==PROJECT || settings.rootDirectory!=='frontend')fail('project build root is not verified');
  const deployment=await provider('/v13/deployments/'+PRODUCTION_HOST+'?withGitRepoInfo=true&teamId='+TEAM);
  let deployed;try{deployed=deployedCommit(deployment,PROJECT);}catch{fail('production deployment identity is not verified');}
  if(current!==undefined && (!sha(current) || deployed!==current))fail('production alias is not the reviewed commit');
  return deployed;
 }
 async function environment() {configuredKeys((await provider('/v9/projects/'+PROJECT+'/env?teamId='+TEAM)).envs);}
 async function get(path,statuses,extraHeaders={}) {
  let response;try{response=await fetcher(ORIGIN+path,{redirect:'manual',cache:'no-store',headers:{'Cache-Control':'no-cache',...extraHeaders},signal:AbortSignal.timeout(15000)});}catch{fail('public surface unavailable');}
  if(!statuses.includes(response.status))fail('unexpected public response at '+path.split('?')[0]+' (HTTP '+response.status+')');
  return response;
 }
 async function contained() {
  for(const path of ['/api/scans','/api/picks?sport=nfl','/terminal','/signals_cache.json'])await get(path,[403]);
  await get('/',[200]);
 }
 async function surface(current) {
  const home=await get('/?readiness='+current,[200]);try{verifySecurityHeaders(home.headers);}catch{fail('public security headers are not verified');}
  const html=await home.text();if(requiredHtmlMarkers.some(marker=>!html.includes(marker)))fail('new public landing is not ready');
  const login=await get('/login',[200]);if(!login.headers.get('cache-control')?.includes('no-store') || !(await login.text()).includes('Owner access'))fail('owner login is not ready');
  const csrf=await get('/api/auth/csrf',[200]);const csrfBody=await csrf.json().catch(()=>null);
  if(!csrf.headers.get('cache-control')?.includes('no-store') || typeof csrfBody?.csrfToken!=='string' || csrfBody.csrfToken.length<16)fail('owner auth configuration is not ready');
  const cookies=csrf.headers.getSetCookie?.() ?? [csrf.headers.get('set-cookie') ?? ''];
  if(!cookies.some(cookie=>/HttpOnly/i.test(cookie) && /Secure/i.test(cookie) && /SameSite=Lax/i.test(cookie)))fail('secure auth cookies are not ready');
  const providers=await get('/api/auth/providers',[200]);const entries=await providers.json().catch(()=>null);
  if(!entries || Object.keys(entries).length!==1 || entries.github?.id!=='github' || entries.github?.type!=='oauth')fail('GitHub owner provider is not ready');
 }
 async function restore() {
  const before=await config();
  if(before?.ownerId!==TEAM || before.projectKey!==PROJECT+'#active' || before.firewallEnabled!==true || !Array.isArray(before.rules))fail('cannot attest firewall before recovery');
  if(before.rules.some(rule=>samePolicy(rule) && rule.active===true)){await removeDiagnostics(before);await contained();return {restored:true};}
  const {id,...value}=POLICY;void id;
  // Targeted free deny insertion preserves the grandfathered rate rule and all other settings.
  try{await provider('/v1/security/firewall/config'+query,{action:'rules.insert',id:null,value});}catch{ /* Reconcile ambiguous insertion without repeating the mutation. */ }
  for(let attempt=0;attempt<3;attempt++){const after=await config();if(after?.ownerId===TEAM && after.projectKey===PROJECT+'#active' && after.firewallEnabled===true && after.rules?.some(rule=>samePolicy(rule) && rule.active===true)){await removeDiagnostics(after);await contained();return {restored:true};}if(attempt<2)await wait(500);}
  fail('containment restoration could not be verified');
 }
 async function removeDiagnostics(active) {
  // Only remove the known, structurally exact diagnostic after the original guard is restored.
  for(const rule of active.rules.filter(rule=>rule.name===PROBE_NAME)) {
   if(!diagnosticRule(rule))fail('diagnostic containment requires operator recovery');
   await provider('/v1/security/firewall/config'+query,{action:'rules.remove',id:rule.id});
  }
 }
 async function preflight() {
  await identity();await environment();let state=guardState(await config());
  if(state.diagnostic){await restore();state=guardState(await config());}
  const guarded=Boolean(state.guard);if(state.guard)await contained();else {
   await verify({base:ORIGIN,fetchImpl:fetcher},{attempts:1});await restore();
   const closed=guardState(await config());if(!closed.guard || closed.digest!==state.digest)fail('privacy enforcement changed unrelated firewall settings');state=closed;
  }
  return {contained:true,enforced:!guarded,firewallVersion:state.version};
 }
 async function finish({current,receipt}={}) {
  if(!sha(current))fail('reviewed commit missing');
  let attempted=false,verifiedIdentity=false,state;
  const record=status=>receipt?.({status,current,project:PROJECT,team:TEAM});
  try {
   await identity(current);verifiedIdentity=true;await environment();state=guardState(await config());
   if(!state.guard || state.diagnostic)fail('normal containment is missing before transition');await surface(current);await contained();
   const freshConfig=await config(),fresh=guardState(freshConfig);if(freshConfig.rules.length>2)fail('free diagnostic rule capacity unavailable');if(fresh.digest!==state.digest || fresh.guard?.id!==state.guard.id)fail('firewall changed before transition');
   // Every control-plane version retains a public deny: original, both guards, then diagnostic guard.
   const secret=randomBytes(32).toString('hex');record('pending');attempted=true;
   await provider('/v1/security/firewall/config'+query,{action:'rules.insert',id:null,value:probePolicy(secret)});
   const staged=guardState(await config());
   if(staged.guard?.id!==state.guard.id || !staged.diagnostic || canonical(spec(staged.diagnostic))!==canonical(spec(probePolicy(secret))) || staged.digest!==state.digest)fail('diagnostic containment insertion is not verified');
   // This root canary is outside the original guard. Prove absent/wrong header matching
   // before altering any original protected path, including actual provider semantics.
   await get(probeCanary(secret),[403]);
   await get(probeCanary(secret),[403],{[PROBE_HEADER]:(secret[0]==='0'?'1':'0')+secret.slice(1)});
   await get(probeCanary(secret),[404],{[PROBE_HEADER]:secret});
   await provider('/v1/security/firewall/config'+query,{action:'rules.remove',id:state.guard.id});
   const probing=guardState(await config());if(probing.guard || probing.diagnostic?.id!==staged.diagnostic.id || probing.digest!==state.digest)fail('diagnostic containment is not active');
   await contained();const deadline=now()+120000;
   const boundedFetch=(diagnostic)=>(url,options={})=>{
    if(new URL(url).origin!==ORIGIN)fail('verification attempted an external origin');
    const remaining=deadline-now();if(remaining<=0)fail('verification deadline exceeded');
    const requestHeaders=new Headers(options.headers);if(diagnostic)requestHeaders.set(PROBE_HEADER,secret);
    return fetcher(url,{...options,headers:requestHeaders,signal:AbortSignal.any([...(options.signal?[options.signal]:[]),AbortSignal.timeout(Math.min(remaining,15000))])});
   };
   // The exception passes only the WAF; every app route must independently deny this anonymous caller.
   await verify({base:ORIGIN,fetchImpl:boundedFetch(true)},{attempts:6,delayMs:2000,wait,log:()=>{}});
   await identity(current);const ready=guardState(await config());
   if(ready.guard || ready.diagnostic?.id!==staged.diagnostic.id || ready.digest!==state.digest)fail('firewall changed during diagnostic verification');
   await provider('/v1/security/firewall/config'+query,{action:'rules.remove',id:staged.diagnostic.id});
   await verify({base:ORIGIN,fetchImpl:boundedFetch(false)},{attempts:3,delayMs:1000,wait,log:()=>{}});
   await identity(current);const after=guardState(await config());
   if(after.guard || after.diagnostic || after.digest!==state.digest)fail('unrelated firewall settings changed');
   record('verified');return {verified:true,transitioned:true,current};
  } catch {
   if(attempted || (verifiedIdentity && state && !state.guard)) {
    try{await restore();record('restored');}catch{fail('verification failed and containment recovery requires operator attention');}
    fail('verification failed; containment restored');
   }
   fail('preconditions failed; containment was not removed');
  }
 }
 return {preflight,finish,restore};
}
export function recoveryReceipt(value,current) {
 if(value===null || value===undefined)return false;
 if(!['pending','verified','restored'].includes(value.status) || !sha(current) || value.current!==current || value.project!==PROJECT || value.team!==TEAM)fail('recovery receipt identity is not verified');
 return value.status==='pending';
}
if(process.argv[1] && import.meta.url===pathToFileURL(process.argv[1]).href) {
 try {
  const mode=process.argv[2];
  if(!['preflight','finish','recover'].includes(mode))fail('invalid operation');
  if(process.env.GITHUB_ACTIONS!=='true' || process.env.GITHUB_REF!=='refs/heads/master' || !sha(process.env.GITHUB_SHA))fail('protected production execution required');
  const controller=releaseController({token:process.env.VERCEL_TOKEN,project:process.env.VERCEL_PROJECT_ID,team:process.env.VERCEL_ORG_ID});
  const receiptPath=process.env.PRIVATE_RELEASE_RECEIPT;
  if(mode==='preflight')console.log(JSON.stringify(await controller.preflight()));
  else {
   if(!receiptPath)fail('recovery receipt path missing');
   const record=value=>{writeFileSync(receiptPath+'.next',JSON.stringify(value),{encoding:'utf8',mode:0o600});renameSync(receiptPath+'.next',receiptPath);};
   if(mode==='finish')console.log(JSON.stringify(await controller.finish({current:process.env.GITHUB_SHA,receipt:record})));
   else {
    let value;try{const text=readFileSync(receiptPath,'utf8');if(text.length>8192)fail('recovery receipt too large');value=JSON.parse(text);}catch(error){if(error.code==='ENOENT')value=null;else throw error;}
    if(recoveryReceipt(value,process.env.GITHUB_SHA)){await controller.restore();record({...value,status:'restored'});console.log('Private containment restored after incomplete transition');}
    else console.log('No incomplete private transition to recover');
   }
  }
 } catch(error) {
  console.error(error.message?.startsWith('Private release:')?error.message:'Private release failed; no provider body or credential logged');process.exitCode=1;
 }
}
