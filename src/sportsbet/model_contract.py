"""Shared identity for the model evaluated by scans and published metrics."""

MODEL_VERSION = 'empirical-jeffreys-v4'
CFB_MODEL_VERSION = 'empirical-jeffreys-v4-cfb-history-v1'
CFB_HISTORY_POLICY = 'cfb-explicit-receiving-v1'
CFB_HISTORY_FROZEN_AT = '2026-09-29T04:15:00+00:00'


def model_version_for(sport: str) -> str:
    return CFB_MODEL_VERSION if sport == 'cfb' else MODEL_VERSION


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
    CFB_MODEL_VERSION,
})


def forecast_version_valid(payload: dict, captured) -> bool:
    from datetime import datetime
    version = payload.get('model_version')
    if payload.get('sport') != 'cfb':
        return version == MODEL_VERSION
    cutoff = datetime.fromisoformat(CFB_HISTORY_FROZEN_AT)
    if captured.utcoffset() is None:
        return False
    if version == MODEL_VERSION:
        return captured < cutoff
    return (version == CFB_MODEL_VERSION and captured >= cutoff
        and payload.get('history_policy_version') == CFB_HISTORY_POLICY)
