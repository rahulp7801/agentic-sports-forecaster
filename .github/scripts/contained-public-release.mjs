/** Explicit public-surface deployment while the existing live deny stays active. */
import {constants,openSync,closeSync,fstatSync,readSync,writeFileSync} from 'node:fs';
import {resolve,dirname,basename} from 'node:path';
import {pathToFileURL} from 'node:url';
import {PROJECT,TEAM,ORIGIN,guardState} from './private-dashboard-release.mjs';
import {deployedCommit,PRODUCTION_HOST} from './deployment-plan.mjs';

export const REPOSITORY='rahulp7801/agentic-sports-forecaster';
export const REPOSITORY_ID=1199906339;
export const OWNER_ID=76501505;
export const WORKFLOW_ID=355316840;
export const WORKFLOW_PATH='.github/workflows/ci.yml';
export const REQUIRED_JOBS=['release-inputs','secrets','backend','frontend','postgres','worker-image','production-schema','release-plan'];
export const CODEQL_CHECKS=['Analyze (python)','Analyze (javascript-typescript)','Analyze (actions)','CodeQL'];
export const ACTION_CHECKS=['secrets','backend','frontend','postgres','worker-image',...CODEQL_CHECKS.slice(0,3)];
export const CHECK_APPS={actions:{id:15368,slug:'github-actions'},aggregate:{id:57789,slug:'github-advanced-security'}};
export const PUBLIC_REQUIRED_KEYS=['NEXTAUTH_URL','NEXTAUTH_SECRET','WAITLIST_DATABASE_URL'];
const PROTOCOL='contained-public-release-v1',MAX_BYTES=2*1024*1024;
const sha=value=>typeof value==='string' && /^[a-f0-9]{40}$/.test(value);
const decimal=value=>typeof value==='string' && /^[1-9][0-9]{0,19}$/.test(value);
const fail=code=>{throw Error('Contained public release: '+code);};
const need=(condition,code)=>{if(!condition)fail(code);};
const exactKeys=(value,keys)=>value && typeof value==='object' && !Array.isArray(value) &&
 Object.keys(value).length===keys.length && keys.every(key=>Object.hasOwn(value,key));

export function executionContext(env=process.env) {
 need(env.GITHUB_ACTIONS==='true' && env.GITHUB_EVENT_NAME==='workflow_dispatch' &&
  env.GITHUB_REF==='refs/heads/master' && env.GITHUB_REPOSITORY===REPOSITORY &&
  env.GITHUB_REPOSITORY_ID===String(REPOSITORY_ID) && env.GITHUB_ACTOR_ID===String(OWNER_ID) &&
  env.PUBLIC_LANDING_ONLY==='true' && env.FORCE_FRONTEND_DEPLOY==='false' &&
  sha(env.GITHUB_SHA) && decimal(env.GITHUB_RUN_ID) && env.GITHUB_RUN_ATTEMPT==='1',
  'explicit_owner_master_dispatch_required');
 return Object.freeze({current:env.GITHUB_SHA,runId:env.GITHUB_RUN_ID,runAttempt:1});
}

export function waitlistConfigured(envs) {
 need(Array.isArray(envs) && envs.length<=1000,'environment_metadata_invalid');
 for(const key of PUBLIC_REQUIRED_KEYS) {
  const matches=envs.filter(item=>item?.key===key && Array.isArray(item.target) &&
   item.target.includes('production') && !item.gitBranch);
  need(matches.length===1,'production_public_setting_missing_or_ambiguous');
 }
}

function closed(config) {
 let state;try{state=guardState(config);}catch{fail('containment_configuration_invalid');}
 need(state.guard && !state.diagnostic,'existing_exact_containment_required');
 return {guardId:state.guard.id,firewallVersion:state.version,unrelatedDigest:state.digest};
}
function sameClosed(first,next) {
 need(first.guardId===next.guardId && first.firewallVersion===next.firewallVersion &&
  first.unrelatedDigest===next.unrelatedDigest,'containment_changed');
}
function receiptCheck(value,context) {
 need(exactKeys(value,['protocol','status','current','runId','runAttempt','project','team',
  'guardId','firewallVersion','unrelatedDigest','previousDeployment']), 'prepared_receipt_invalid');
 need(value.protocol===PROTOCOL && value.status==='prepared' && value.current===context.current &&
  value.runId===context.runId && value.runAttempt===context.runAttempt && value.project===PROJECT && value.team===TEAM &&
  typeof value.guardId==='string' && /^rule_[A-Za-z0-9_]+$/.test(value.guardId) &&
  Number.isSafeInteger(value.firewallVersion) && value.firewallVersion>0 &&
  typeof value.unrelatedDigest==='string' && /^[a-f0-9]{64}$/.test(value.unrelatedDigest) &&
  sha(value.previousDeployment),'prepared_receipt_identity_invalid');
}

async function boundedJson(response) {
 need(response.ok,'metadata_request_refused');
 const reader=response.body?.getReader();need(reader,'metadata_response_invalid');
 const chunks=[];let bytes=0;
 try {
  while(true) {const {done,value}=await reader.read();if(done)break;
   bytes+=value.length;if(bytes>MAX_BYTES){await reader.cancel();fail('metadata_response_unbounded');}chunks.push(value);
  }
 }finally{reader.releaseLock();}
 try{return JSON.parse(Buffer.concat(chunks).toString('utf8'));}catch{fail('metadata_response_invalid');}
}

export function containedPublicController({token,githubToken,context,project=PROJECT,team=TEAM,
 fetcher=fetch,verifyAccess=async options=>(await import('../../frontend/scripts/verify-contained-public.mjs')).verifyContainedAccess(options),
 verify=async options=>(await import('../../frontend/scripts/verify-contained-public.mjs')).verifyContainedPublic(options)}={}) {
 need([token,githubToken].every(value=>typeof value==='string' && value.trim() && !/[\r\n]/.test(value)) &&
  project===PROJECT && team===TEAM,'protected_credentials_or_project_missing');
 need(exactKeys(context,['current','runId','runAttempt']) && sha(context.current) && decimal(context.runId) &&
  context.runAttempt===1,'execution_context_invalid');
 context=Object.freeze({...context});
 async function metadata(origin,path,credential) {
  let response;
  try {response=await fetcher(origin+path,{method:'GET',headers:{Authorization:'Bearer '+credential,
   Accept:'application/json',...(origin==='https://api.github.com'?{'X-GitHub-Api-Version':'2026-03-10'}:{})},
   redirect:'error',cache:'no-store',signal:AbortSignal.timeout(15000)});}
  catch{fail('metadata_request_unavailable');}
  try{return await boundedJson(response);}catch{fail('metadata_response_invalid_or_unbounded');}
 }
 const github=path=>metadata('https://api.github.com','/repos/'+REPOSITORY+path,githubToken);
 const vercel=path=>metadata('https://api.vercel.com',path,token);
 const firewall=()=>vercel('/v1/security/firewall/config/active?projectId='+PROJECT+'&teamId='+TEAM);
 async function readChecks(commit) {
  const checks=[];let total;
  for(let page=1;page<=3;page++) {
   // The default latest filter omits the PR-only Advanced Security aggregate.
   const result=await github('/commits/'+commit+'/check-runs?filter=all&per_page=100&page='+page);
   need(Number.isSafeInteger(result?.total_count) && result.total_count>=0 && result.total_count<=300 &&
    Array.isArray(result.check_runs) && result.check_runs.length<=100 &&
    (total===undefined || total===result.total_count),'check_runs_unbounded_or_changed');
   total=result.total_count;checks.push(...result.check_runs);
   if(checks.length>=total)break;
   need(result.check_runs.length===100,'check_run_page_incomplete');
  }
  need(checks.length===total && checks.every(check=>Number.isSafeInteger(check?.id) && check.id>0) &&
   new Set(checks.map(check=>check.id)).size===checks.length,'check_run_pages_incomplete');
  return checks;
 }
 function successfulCheck(checks,name,commit,app,id) {
  const found=checks.filter(check=>check.name===name && (id===undefined || check.id===id));
  need(found.length===1 && found[0].status==='completed' && found[0].conclusion==='success' &&
   found[0].head_sha===commit && found[0].app?.id===app.id && found[0].app?.slug===app.slug,
   'required_exact_head_check_not_successful');
 }
 async function reviewedSquash(masterChecks,jobChecks) {
  for(const name of ACTION_CHECKS)successfulCheck(masterChecks,name,context.current,CHECK_APPS.actions,jobChecks.get(name));
  const associated=await github('/commits/'+context.current+'/pulls?per_page=100');
  need(Array.isArray(associated) && associated.length<100,'associated_pull_requests_unbounded');
  const candidates=associated.filter(pr=>pr?.merge_commit_sha===context.current && pr.base?.ref==='master' &&
   pr.base?.repo?.id===REPOSITORY_ID);
  need(candidates.length===1 && Number.isSafeInteger(candidates[0].number) && candidates[0].number>0 &&
   candidates[0].number!==194,'reviewed_pull_request_missing_or_ambiguous');
  const candidate=candidates[0],pr=await github('/pulls/'+candidate.number);
  need(pr?.number===candidate.number && pr.merged===true && pr.state==='closed' &&
   typeof pr.merged_at==='string' && Number.isFinite(Date.parse(pr.merged_at)) && pr.merge_commit_sha===context.current &&
   pr.base?.ref==='master' && pr.base?.repo?.id===REPOSITORY_ID && pr.base.repo.full_name===REPOSITORY &&
   pr.head?.repo?.id===REPOSITORY_ID && pr.head.repo.full_name===REPOSITORY && sha(pr.head.sha) &&
   pr.head.sha===candidate.head?.sha,'reviewed_pull_request_identity_changed');
  const master=await github('/git/commits/'+context.current),head=await github('/git/commits/'+pr.head.sha);
  need(master?.sha===context.current && head?.sha===pr.head.sha && sha(master.tree?.sha) &&
   master.tree.sha===head.tree?.sha,'reviewed_squash_tree_mismatch');
  const checks=await readChecks(pr.head.sha);
  for(const name of ACTION_CHECKS)successfulCheck(checks,name,pr.head.sha,CHECK_APPS.actions);
  successfulCheck(checks,'CodeQL',pr.head.sha,CHECK_APPS.aggregate);
 }
 async function repositoryAndChecks() {
  const repository=await github('');
  need(repository?.id===REPOSITORY_ID && repository.full_name===REPOSITORY && repository.private===false &&
   repository.default_branch==='master' && repository.owner?.id===OWNER_ID,'public_repository_identity_changed');
  const branch=await github('/git/ref/heads/master');
  need(branch?.ref==='refs/heads/master' && branch.object?.type==='commit' &&
   branch.object.sha===context.current,'current_master_changed');
  const run=await github('/actions/runs/'+context.runId);
  need(String(run?.id)===context.runId && run.run_attempt===1 && run.event==='workflow_dispatch' &&
   run.head_sha===context.current && run.head_branch==='master' && run.repository?.id===REPOSITORY_ID &&
   run.workflow_id===WORKFLOW_ID && run.path===WORKFLOW_PATH &&
   run.actor?.id===OWNER_ID && run.triggering_actor?.id===OWNER_ID && run.status==='in_progress',
   'current_workflow_identity_changed');
  const jobs=await github('/actions/runs/'+context.runId+'/jobs?filter=latest&per_page=100');
  need(Array.isArray(jobs?.jobs) && Number.isSafeInteger(jobs.total_count) &&
   jobs.total_count===jobs.jobs.length && jobs.total_count<=100,'workflow_jobs_unbounded');
  const jobChecks=new Map();
  for(const name of REQUIRED_JOBS) {
   const found=jobs.jobs.filter(job=>job?.name===name);
   need(found.length===1 && found[0].status==='completed' && found[0].conclusion==='success' &&
    found[0].head_sha===context.current && String(found[0].run_id)===context.runId,'required_workflow_job_not_successful');
   if(ACTION_CHECKS.includes(name)) {
    const prefix='https://api.github.com/repos/'+REPOSITORY+'/check-runs/';
    const path=found[0].check_run_url;
    need(typeof path==='string' && path.startsWith(prefix) && decimal(path.slice(prefix.length)) &&
     Number.isSafeInteger(Number(path.slice(prefix.length))),'workflow_check_identity_invalid');
    jobChecks.set(name,Number(path.slice(prefix.length)));
   }
  }
  await reviewedSquash(await readChecks(context.current),jobChecks);
 }
 async function platform(current) {
  const account=await vercel('/v2/teams/'+TEAM);
  need(account?.id===TEAM && account.billing?.plan==='hobby','existing_free_hobby_plan_required');
  const settings=await vercel('/v9/projects/'+PROJECT+'?teamId='+TEAM);
  need(settings?.id===PROJECT && settings.rootDirectory==='frontend','project_identity_changed');
  const deployment=await vercel('/v13/deployments/'+PRODUCTION_HOST+'?withGitRepoInfo=true&teamId='+TEAM);
  let commit;try{commit=deployedCommit(deployment,PROJECT);}catch{fail('production_deployment_identity_invalid');}
  if(current!==undefined)need(commit===current,'reviewed_production_commit_not_ready');
  const env=await vercel('/v9/projects/'+PROJECT+'/env?teamId='+TEAM+'&decrypt=false');
  waitlistConfigured(env?.envs);return commit;
 }
 async function publicFetch(url,options={}) {
  const target=new URL(url),headers=new Headers(options.headers);
  need(target.origin===ORIGIN && !target.username && !target.password &&
   !['authorization','cookie','x-private-release-probe'].some(name=>headers.has(name)),
   'public_probe_credentials_or_origin_refused');
  return fetcher(target.href,{...options,headers,redirect:'manual',credentials:'omit',cache:'no-store',
   signal:AbortSignal.any([...(options.signal?[options.signal]:[]),AbortSignal.timeout(15000)])});
 }
 async function preflight() {
  const before=closed(await firewall());
  await repositoryAndChecks();const previousDeployment=await platform();
  try{await verifyAccess({base:ORIGIN,fetchImpl:publicFetch});}catch{fail('contained_access_not_verified');}
  await repositoryAndChecks();sameClosed(before,closed(await firewall()));
  return {protocol:PROTOCOL,status:'prepared',...context,project:PROJECT,team:TEAM,...before,previousDeployment};
 }
 async function finish({current,receipt}={}) {
  need(current===context.current,'reviewed_commit_changed');receiptCheck(receipt,context);
  sameClosed(receipt,closed(await firewall()));await repositoryAndChecks();await platform(current);
  try{await verify({base:ORIGIN,fetchImpl:publicFetch});}catch{fail('public_surface_not_verified');}
  await repositoryAndChecks();await platform(current);sameClosed(receipt,closed(await firewall()));
  return {status:'public_surface_verified',current,project:PROJECT,team:TEAM,containment_active:true,
   owner_authentication_verified:false};
 }
 return {preflight,finish};
}

function receiptPath(env) {
 need(typeof env.RUNNER_TEMP==='string' && typeof env.CONTAINED_PUBLIC_RECEIPT==='string','receipt_path_missing');
 const path=resolve(env.CONTAINED_PUBLIC_RECEIPT);
 need(dirname(path)===resolve(env.RUNNER_TEMP) && basename(path)==='contained-public-release.json','receipt_path_invalid');
 return path;
}
function readReceipt(path) {
 let fd;
 try {
  fd=openSync(path,constants.O_RDONLY | (constants.O_NOFOLLOW ?? 0));const before=fstatSync(fd);
  need(before.isFile() && before.nlink===1 && before.size>0 && before.size<=8192,'prepared_receipt_unavailable');
  const raw=Buffer.alloc(8193),size=readSync(fd,raw,0,raw.length,0),after=fstatSync(fd);
  need(size===before.size && before.dev===after.dev && before.ino===after.ino && before.mtimeMs===after.mtimeMs &&
   before.size===after.size,'prepared_receipt_changed');
  return JSON.parse(raw.subarray(0,size).toString('utf8'));
 }catch{fail('prepared_receipt_unavailable');}finally{if(fd!==undefined)closeSync(fd);}
}
if(process.argv[1] && import.meta.url===pathToFileURL(process.argv[1]).href) {
 try {
  const mode=process.argv[2];need(['preflight','finish'].includes(mode),'operation_invalid');
  need(process.env.VERCEL_PROJECT_ID===PROJECT && process.env.VERCEL_ORG_ID===TEAM,'protected_project_variables_missing');
  const context=executionContext(),path=receiptPath(process.env);
  const controller=containedPublicController({token:process.env.VERCEL_TOKEN,githubToken:process.env.GITHUB_TOKEN,
   context,project:process.env.VERCEL_PROJECT_ID,team:process.env.VERCEL_ORG_ID});
  if(mode==='preflight') {
   const receipt=await controller.preflight();writeFileSync(path,JSON.stringify(receipt),{flag:'wx',mode:0o600});
   console.log(JSON.stringify({status:'public_release_prepared',current:context.current,containment_active:true,owner_authentication_verified:false}));
  }else{
   const result=await controller.finish({current:context.current,receipt:readReceipt(path)});
   writeFileSync(path+'.verified',JSON.stringify(result),{flag:'wx',mode:0o600});console.log(JSON.stringify(result));
  }
 }catch(error){
  console.error(error.message?.startsWith('Contained public release:')?error.message:
   'Contained public release failed; no provider body or credential logged.');process.exitCode=1;
 }
}
