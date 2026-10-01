import test from 'node:test';
import assert from 'node:assert/strict';
import {execFileSync} from 'node:child_process';
import {mkdtempSync, writeFileSync, mkdirSync, rmSync, realpathSync} from 'node:fs';
import {tmpdir} from 'node:os';
import {join, dirname, basename} from 'node:path';
import {deployedCommit, releaseDecision, readPlan, sourceChanged} from '../deployment-plan.mjs';

const old = 'a'.repeat(40), current = 'b'.repeat(40), project = 'prj_test';
const deployment = () => ({projectId: project, readyState: 'READY', target: 'production', meta: {githubCommitSha: old}});

test('research-only change skips deployment against the live commit', () => {
  let pair;
  const result = releaseDecision({deployment: deployment(), project, current,
    changed: (...args) => {pair = args; return false;}});
  assert.deepEqual(pair, [old, current]);
  assert.equal(result.deploy, false); assert.equal(result.reason, 'frontend_source_unchanged');
});

test('undeployed frontend change remains required across later research commits', () => {
  const result = releaseDecision({deployment: deployment(), project, current, changed: () => true});
  assert.equal(result.deploy, true); assert.equal(result.reason, 'frontend_source_changed');
});

test('explicit redeploy handles external configuration changes', () => {
  assert.equal(releaseDecision({deployment: deployment(), project, current, force: true, changed: () => false}).deploy, true);
});

for (const fault of ['project', 'state', 'target', 'missing', 'conflicting', 'injection']) {
  test(`unverified production identity fails closed: ${fault}`, () => {
    const d = deployment();
    if (fault === 'project') d.projectId = 'prj_other';
    if (fault === 'state') d.readyState = 'ERROR';
    if (fault === 'target') d.target = 'preview';
    if (fault === 'missing') d.meta = {};
    if (fault === 'conflicting') d.gitSource = {sha: current};
    if (fault === 'injection') d.meta.githubCommitSha = '--help';
    assert.throws(() => deployedCommit(d, project));
  });
}

test('consistent CLI and provider commit metadata are accepted', () => {
  const d = deployment(); d.meta.sportsbetCommit = old; d.gitSource = {sha: old};
  assert.equal(deployedCommit(d, project), old);
});

test('unknown diff result or missing git objects cannot become a skip', () => {
  assert.throws(() => releaseDecision({deployment: deployment(), project, current, changed: () => undefined}));
  assert.throws(() => sourceChanged(old, current, () => {throw new Error('missing object');}));
});

test('provider reads are bounded, read-only and resolve the production hostname', async () => {
  const calls = [];
  const result = await readPlan({token: 'private-test-token', project, team: 'team_test', current,
    changed: () => false, fetcher: async (url, options) => {
      calls.push([url, options]);
      return {ok: true, json: async () => url.includes('/projects/')
        ? {id: project, rootDirectory: 'frontend'} : deployment()};
    }});
  assert.equal(result.deploy, false); assert.equal(calls.length, 2);
  assert.ok(calls[1][0].includes('/deployments/agentic-ev-analytics-platform.vercel.app?withGitRepoInfo=true'));
  for (const [url, options] of calls) {
    assert.equal(new URL(url).origin, 'https://api.vercel.com');
    assert.equal(options.method, undefined); assert.equal(options.redirect, 'error');
    assert.ok(options.signal instanceof AbortSignal);
  }
  assert.ok(!JSON.stringify(result).includes('private-test-token'));
});

test('provider denial does not attempt a deployment or log response secrets', async () => {
  await assert.rejects(readPlan({token: 'private', project, team: 'team_test', current, changed: () => false,
    fetcher: async () => ({ok: false, status: 403, json: () => {throw new Error('must not read');}})}),
    /^Error: Deployment metadata read failed \(HTTP 403\)$/);
});

test('unexpected project root cannot skip deployment', async () => {
  await assert.rejects(readPlan({token: 'private', project, team: 'team_test', current,
    changed: () => false, fetcher: async () => ({ok: true, json: async () => ({id: project, rootDirectory: '.'})})}),
    /Unexpected project build root/);
});

test('real git comparison detects pending frontend and upload boundary changes', () => {
  const directory = mkdtempSync(join(tmpdir(), 'sportsbet-release-test-'));
  const git = args => execFileSync('git', args, {cwd: directory, encoding: 'utf8', stdio: 'pipe'}).trim();
  const commit = () => {git(['add', '.']); git(['-c', 'user.name=Test', '-c', 'user.email=test@example.invalid',
    '-c', 'commit.gpgsign=false', 'commit', '-qm', 'fixture']); return git(['rev-parse', 'HEAD']);};
  const run = (cmd, args, options) => execFileSync(cmd, args, {...options, cwd: directory});
  try {
    git(['init', '-q']); mkdirSync(join(directory, 'frontend'));
    writeFileSync(join(directory, 'frontend/app.txt'), 'live'); const live = commit();
    writeFileSync(join(directory, 'research.txt'), 'research'); const research = commit();
    assert.equal(sourceChanged(live, research, run), false);
    writeFileSync(join(directory, 'frontend/app.txt'), 'pending'); const pending = commit();
    writeFileSync(join(directory, 'research.txt'), 'later research'); const later = commit();
    assert.equal(sourceChanged(pending, later, run), false);
    assert.equal(sourceChanged(live, later, run), true);
    writeFileSync(join(directory, '.vercelignore'), '*'); const boundary = commit();
    assert.equal(sourceChanged(later, boundary, run), true);
  } finally {
    const resolved = realpathSync(directory);
    assert.equal(dirname(resolved), realpathSync(tmpdir()));
    assert.ok(basename(resolved).startsWith('sportsbet-release-test-'));
    rmSync(resolved, {recursive: true, force: true});
  }
});
