import {execFileSync} from 'node:child_process';
import {appendFileSync} from 'node:fs';
import {pathToFileURL} from 'node:url';

export const PRODUCTION_HOST = 'agentic-ev-analytics-platform.vercel.app';
export const RELEASE_PATHS = ['frontend', '.vercelignore', 'vercel.json', 'package.json',
  'package-lock.json', 'pnpm-lock.yaml', 'pnpm-workspace.yaml', 'yarn.lock', 'turbo.json'];
const sha = value => typeof value === 'string' && /^[a-f0-9]{40}$/.test(value);

export function deployedCommit(deployment, project) {
  if (deployment.projectId !== project || deployment.readyState !== 'READY'
      || deployment.target !== 'production') throw new Error('Production deployment identity is not verified');
  const candidates = [deployment.meta?.githubCommitSha, deployment.meta?.gitCommitSha,
    deployment.gitSource?.sha, deployment.meta?.sportsbetCommit].filter(value => value !== undefined);
  if (!candidates.length || candidates.some(value => !sha(value)) || new Set(candidates).size !== 1) {
    throw new Error('Production deployment has missing or conflicting commit metadata');
  }
  return candidates[0];
}

export function releaseDecision({deployment, project, current, changed, force = false}) {
  if (!sha(current)) throw new Error('Invalid current commit');
  const deployed = deployedCommit(deployment, project);
  // Compare the live release, never just HEAD^: a failed frontend release must
  // remain pending when a subsequent research-only commit arrives.
  const differs = changed(deployed, current);
  if (typeof differs !== 'boolean') throw new Error('Release comparison unavailable');
  return {deploy: force || differs, deployed, current,
    reason: force ? 'explicit_redeploy' : differs ? 'frontend_source_changed' : 'frontend_source_unchanged'};
}

export async function readPlan({token, project, team, current, force = false, fetcher = fetch, changed}) {
  if (!token || !/^prj_[A-Za-z0-9]+$/.test(project ?? '') || !/^team_[A-Za-z0-9]+$/.test(team ?? '')) {
    throw new Error('Deployment credentials or project identifiers are missing');
  }
  const get = async path => {
    const response = await fetcher(`https://api.vercel.com${path}${path.includes('?') ? '&' : '?'}teamId=${encodeURIComponent(team)}`, {
      headers: {Authorization: `Bearer ${token}`}, redirect: 'error', signal: AbortSignal.timeout(15000),
    });
    if (!response.ok) throw new Error(`Deployment metadata read failed (HTTP ${response.status})`);
    return response.json();
  };
  const settings = await get(`/v9/projects/${encodeURIComponent(project)}`);
  if (settings.id !== project || settings.rootDirectory !== 'frontend') throw new Error('Unexpected project build root');
  const deployment = await get(`/v13/deployments/${PRODUCTION_HOST}?withGitRepoInfo=true`);
  return releaseDecision({deployment, project, current, force, changed});
}

export function sourceChanged(deployed, current, run = execFileSync) {
  if (!sha(deployed) || !sha(current)) throw new Error('Invalid comparison commit');
  // The full checkout provides ancestry and object data; no shell interpolation.
  run('git', ['cat-file', '-e', `${deployed}^{commit}`], {stdio: 'pipe'});
  run('git', ['merge-base', '--is-ancestor', deployed, current], {stdio: 'pipe'});
  return run('git', ['diff', '--name-only', deployed, current, '--', ...RELEASE_PATHS],
    {encoding: 'utf8', stdio: 'pipe'}).trim().length > 0;
}

if (process.argv[1] && import.meta.url === pathToFileURL(process.argv[1]).href) {
  try {
    const result = await readPlan({token: process.env.VERCEL_TOKEN, project: process.env.VERCEL_PROJECT_ID,
      team: process.env.VERCEL_ORG_ID, current: process.env.GITHUB_SHA,
      force: process.env.FORCE_FRONTEND_DEPLOY === 'true', changed: sourceChanged});
    // Only fixed booleans, reason codes and validated commit hashes reach logs.
    console.log(JSON.stringify(result));
    if (process.env.GITHUB_OUTPUT) appendFileSync(process.env.GITHUB_OUTPUT, `deploy=${result.deploy}\n`);
  } catch (error) {
    // Never print provider response bodies or child-process output containing credentials.
    const safe = /^(Production deployment|Invalid current commit|Deployment credentials|Deployment metadata read|Unexpected project build root|Release comparison unavailable)/.test(error.message);
    console.error(safe ? error.message : 'Production release comparison failed; deployment not attempted');
    process.exitCode = 1;
  }
}
