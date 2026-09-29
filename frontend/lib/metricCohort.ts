export type MetricCohort = 'all' | 'recommendations';
export type MetricSport = 'all' | 'nba' | 'nfl' | 'cfb';

export function metricCohort(url: string): MetricCohort | null {
  const value = new URL(url).searchParams.get('cohort') ?? 'all';
  return value === 'all' || value === 'recommendations' ? value : null;
}

export function metricSport(url: string): MetricSport | null {
  const value = new URL(url).searchParams.get('sport') ?? 'all';
  return value === 'all' || value === 'nba' || value === 'nfl' || value === 'cfb' ? value : null;
}

export function metricSnapshotKey(cohort: MetricCohort, sport: MetricSport = 'all') {
  return `metrics:${cohort}${sport === 'all' ? '' : `:${sport}`}`;
}

export function metricLedgerArgs(cohort: MetricCohort, sport: MetricSport = 'all') {
  return ['-m', 'sportsbet.ledger', ...(cohort === 'recommendations' ? ['--recommendations-only'] : []),
    ...(sport === 'all' ? [] : ['--sport', sport]),
    ...(sport === 'cfb' ? ['--model-version','empirical-jeffreys-v4-cfb-history-v1']
      : sport === 'nfl' ? ['--model-version','empirical-jeffreys-v4-nfl-history-v1'] : [])];
}
