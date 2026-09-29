"""Shared identity for the model evaluated by scans and published metrics."""

MODEL_VERSION = 'empirical-jeffreys-v4'
CFB_MODEL_VERSION = 'empirical-jeffreys-v4-cfb-history-v1'
CFB_HISTORY_POLICY = 'cfb-explicit-receiving-v1'
CFB_HISTORY_FROZEN_AT = '2026-09-29T04:15:00+00:00'
NFL_MODEL_VERSION = 'empirical-jeffreys-v4-nfl-history-v1'
NFL_HISTORY_POLICY = 'nfl-explicit-receiving-v1'
NFL_HISTORY_FROZEN_AT = '2026-09-29T05:45:00+00:00'


def model_version_for(sport: str, observed_at=None) -> str:
    from datetime import datetime
    if sport == 'nfl' and observed_at is not None and observed_at < datetime.fromisoformat(NFL_HISTORY_FROZEN_AT):
        return MODEL_VERSION
    return {'cfb': CFB_MODEL_VERSION, 'nfl': NFL_MODEL_VERSION}.get(sport, MODEL_VERSION)


def history_policy_for(sport: str) -> str | None:
    return {'cfb': CFB_HISTORY_POLICY, 'nfl': NFL_HISTORY_POLICY}.get(sport)


PROP_MARKETS = {
    'nba': {'player_points': 'points', 'player_rebounds': 'rebounds',
            'player_assists': 'assists'},
    'nfl': {'player_pass_yds': 'pass_yds', 'player_rush_yds': 'rush_yds',
            'player_reception_yds': 'rec_yds', 'player_receptions': 'receptions'},
    'cfb': {'player_pass_yds': 'pass_yds', 'player_rush_yds': 'rush_yds',
            'player_reception_yds': 'rec_yds', 'player_receptions': 'receptions'},
}

# These scanner cohorts were introduced after quote source and normalized-row
# commitments became mandatory. Advancing MODEL_VERSION must not make their
# historical records exempt from provenance validation.
QUOTE_PROVENANCE_MODEL_VERSIONS = frozenset({
    'empirical-v2',
    'empirical-jeffreys-v3',
    'empirical-jeffreys-v4',
    CFB_MODEL_VERSION, NFL_MODEL_VERSION,
})


def forecast_version_valid(payload: dict, captured) -> bool:
    from datetime import datetime
    sport = payload.get('sport'); version = payload.get('model_version')
    if version == MODEL_VERSION:
        return True  # Preserve retained v4 forecasts, including deployment overlap.
    contracts = {'cfb': (CFB_MODEL_VERSION, CFB_HISTORY_POLICY, CFB_HISTORY_FROZEN_AT),
                 'nfl': (NFL_MODEL_VERSION, NFL_HISTORY_POLICY, NFL_HISTORY_FROZEN_AT)}
    if sport not in contracts or captured.utcoffset() is None:
        return False
    expected, policy, cutoff = contracts[sport]
    return version == expected and captured >= datetime.fromisoformat(cutoff) and payload.get('history_policy_version') == policy
