/** Verify old live reads, with a narrow path to deploy a proven region recovery. */
import {readFileSync} from 'node:fs';
import {pathToFileURL} from 'node:url';
import {randomInt} from 'node:crypto';

export const HOST='https://agentic-ev-analytics-platform.vercel.app';
export const PATHS=['/api/scans','/api/picks?sport=nfl'];

function pendingRegion() {
  try {
    const config=JSON.parse(readFileSync(new URL('../../frontend/vercel.json',import.meta.url),'utf8'));
    return config.regions?.length===1 && config.regions[0]==='pdx1' ? 'pdx1' : null;
  } catch {
    return null;
  }
}

function oldFunctionRegion(response) {
  const value=response.headers?.get?.('x-vercel-id');
  return /^[a-z0-9]+::([a-z0-9]+)::/.exec(value || '')?.[1] || null;
}

function directDatabaseProbe() {
  const suffix=Array.from({length:16},()=>String.fromCharCode(65+randomInt(26))).join('');
  return '/api/gamelogs?sport=nfl&player=HealthProbe'+suffix+'&limit=1';
}

export async function preflight({fetcher=fetch,sleep=ms=>new Promise(resolve=>setTimeout(resolve,ms)),
  rounds=2,delayMs=5000,recoveryRegion=pendingRegion()}={}) {
  if(!Number.isSafeInteger(rounds) || rounds<1 || rounds>3 || !Number.isSafeInteger(delayMs) || delayMs<0 || delayMs>10000) {
    throw new Error('Invalid database preflight bounds');
  }
  const options=()=>({redirect:'error',cache:'no-store',
    headers:{'Cache-Control':'no-cache'},signal:AbortSignal.timeout(8000)});
  let recoveringReads=0;
  for(let round=0;round<rounds;round++) {
    for(const path of [...PATHS,directDatabaseProbe()]) {
      const url=new URL(path,HOST);
      let response;
      try {
        response=await fetcher(url,options());
      } catch {
        throw new Error('Production database preflight failed: '+url.pathname+' request unavailable');
      }
      if(response.status===200) continue;
      if(response.status===401 && response.headers.get('cache-control')?.includes('no-store')) {
        const body=await response.json().catch(()=>null);
        if(body?.error==='Owner authentication required.') continue;
      }
      // CI's production-schema dependency has already proved a read through
      // the pending 6543 connection. Permit only the old iad1 release's DB
      // routes to be unhealthy while moving this exact release to pdx1.
      if(response.status===503 && recoveryRegion==='pdx1' && oldFunctionRegion(response)==='iad1') {
        recoveringReads++;
        continue;
      }
      throw new Error('Production database preflight failed: '+url.pathname+' HTTP '+response.status);
    }
    if(round+1<rounds) await sleep(delayMs);
  }
  const result={rounds,reads:rounds*(PATHS.length+1)};
  if(!recoveringReads) return result;
  let home;
  try {
    home=await fetcher(new URL('/',HOST),options());
  } catch {
    throw new Error('Production recovery preflight failed: homepage request unavailable');
  }
  if(home.status!==200) throw new Error('Production recovery preflight failed: homepage HTTP '+home.status);
  return {...result,recoveringReads};
}

if(process.argv[1] && import.meta.url===pathToFileURL(process.argv[1]).href) {
  try {
    const result=await preflight();
    if(result.recoveringReads) console.warn('::warning::Old iad1 database routes are unavailable; pending pdx1 read was checked by production-schema');
    console.log(JSON.stringify(result));
  }
  catch(error) {console.error(error.message);process.exitCode=1;}
}