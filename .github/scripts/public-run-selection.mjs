import {pathToFileURL} from 'node:url';

const schedules = new Set([
  '7 0,3,6,9,15,18,21 * * *', '7 12 * * *',
  '37 1,4,7,10,16,19,22 * * *', '37 13 * * *',
]);
const invalid = () => new Error('Public run selection metadata is invalid');
const identifier = value => typeof value === 'string' && value.length >= 1 && value.length <= 20
  && /^[1-9]/.test(value) && !/[^0-9]/.test(value);

// Record the selected values independently from the triggering cron. This is
// run context, not a producer report or a replacement for source capture clocks.
export function publicRunSelection({eventName, schedule, operation, sport, sha, runId, runAttempt}) {
  if (!['schedule', 'workflow_dispatch'].includes(eventName)
      || !['public_monitor', 'public_daily'].includes(operation)
      || !['both', 'nfl', 'nba', 'cfb'].includes(sport)
      || typeof sha !== 'string' || sha.length !== 40 || !/^[a-f0-9]{40}$/.test(sha)
      || !identifier(runId) || !identifier(runAttempt)
      || (eventName === 'schedule' ? !schedules.has(schedule)
        : ![undefined, null, ''].includes(schedule))) throw invalid();
  return {
    schema_version: 1,
    receipt_kind: 'public_run_selection',
    event_name: eventName,
    schedule: eventName === 'schedule' ? schedule : null,
    selected_operation: operation,
    selected_sport: sport,
    head_sha: sha,
    run_id: runId,
    run_attempt: runAttempt,
  };
}

export function publicRunSelectionFromEnvironment(environment) {
  return publicRunSelection({eventName: environment.GITHUB_EVENT_NAME,
    schedule: environment.PUBLIC_RUN_SCHEDULE, operation: environment.OPERATION,
    sport: environment.SPORT, sha: environment.GITHUB_SHA,
    runId: environment.GITHUB_RUN_ID, runAttempt: environment.GITHUB_RUN_ATTEMPT});
}

if (process.argv[1] && import.meta.url === pathToFileURL(process.argv[1]).href) {
  try {
    console.log(JSON.stringify(publicRunSelectionFromEnvironment(process.env)));
  } catch {
    console.error('Public run selection metadata is invalid');
    process.exitCode = 1;
  }
}
