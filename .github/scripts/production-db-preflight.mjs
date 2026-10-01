/** Require repeatable live database reads before spending a production deployment. */
import {pathToFileURL} from 'node:url';
import {randomInt} from 'node:crypto';

export const HOST='https://agentic-ev-analytics-platform.vercel.app';
export const PATHS=['/api/scans','/api/picks?sport=nfl'];

function directDatabaseProbe() {
  const suffix=Array.from({length:16},()=>String.fromCharCode(65+randomInt(26))).join('');
  return '/api/gamelogs?sport=nfl&player=HealthProbe'+suffix+'&limit=1';
}

export async function preflight({fetcher=fetch,sleep=ms=>new Promise(resolve=>setTimeout(resolve,ms)),rounds=2,delayMs=5000}={}) {
  if(!Number.isSafeInteger(rounds) || rounds<1 || rounds>3 || !Number.isSafeInteger(delayMs) || delayMs<0 || delayMs>10000) {
    throw new Error('Invalid database preflight bounds');
  }
  for(let round=0;round<rounds;round++) {
    for(const path of [...PATHS,directDatabaseProbe()]) {
      const url=new URL(path,HOST);
      let response;
      try {
        response=await fetcher(url,{redirect:'error',cache:'no-store',
          headers:{'Cache-Control':'no-cache'},signal:AbortSignal.timeout(8000)});
      } catch {
        throw new Error('Production database preflight failed: '+url.pathname+' request unavailable');
      }
      if(response.status!==200) throw new Error('Production database preflight failed: '+url.pathname+' HTTP '+response.status);
    }
    if(round+1<rounds) await sleep(delayMs);
  }
  return {rounds,reads:rounds*(PATHS.length+1)};
}

if(process.argv[1] && import.meta.url===pathToFileURL(process.argv[1]).href) {
  try {console.log(JSON.stringify(await preflight()));}
  catch(error) {console.error(error.message);process.exitCode=1;}
}