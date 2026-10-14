"""Independent prospective teammate-context study; no collection or pick promotion.

The October 4 exploratory signal is excluded. Existing captures supply the
sources; a separate hash marker travels in their original private anchor commit.
"""
from __future__ import annotations

import argparse
from collections import Counter, defaultdict
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal, InvalidOperation
import hashlib
import json
from pathlib import Path
import re

import pyarrow as pa
import pyarrow.parquet as pq

from sportsbet.quant import kalshi_stat_only_next_eval as single
from sportsbet.quant import kalshi_stat_only_next_context as context
from sportsbet.quant import kalshi_stat_only_next_series as series
from sportsbet.quant import kalshi_stat_only_remote_anchor as anchor
from sportsbet.quant import kalshi_stat_only_context_price_audit as comparison
from sportsbet.quant import kalshi_stat_only_teammate_context as bins
from sportsbet.quant.kalshi_market_cohort import clock, digest
from sportsbet.quant.kalshi_market_settlement import venue_results
from sportsbet.quant.kalshi_pair_capture import unpack
from sportsbet.quant.kalshi_role_shadow import team as source_team
from sportsbet.quant.kalshi_stat_only_transfer import NY

VERSION = 'kalshi-nfl-prospective-teammate-context-v1'
MARKER_VERSION = VERSION + '-anchor'
START = '2026-10-08T00:00:00+00:00'
ROOT_NAME = re.compile(r'next-nfl-stat-only-(?P<stamp>[0-9]{8}T[0-9]{4})\Z')
NON_SKILL = frozenset({'C','G','OG','OT','T','OL','DE','DT','DL','NT','LB',
                      'ILB','OLB','CB','DB','S','FS','SS','K','P','LS'})
POLICY = dict(primary_group='questionable_teammate_only',
    maximum_decision_to_kickoff_hours=48, prior_completed_team_games=3,
    minimum_primary_paired_independent_games=50,
    ownership='earliest_server_published_eligible_capture_owns_entire_fixture',
    unavailable_membership='retained_never_repaired_by_later_capture',
    secondary_scopes='all_original_bins_and_fixed_probability_ge_75pct_subset',
    comparisons='same_contract_prices_and_strict_prior20_brier_and_log_loss',
    support='complete_primary_coverage_and_favorable_game_and_player_bounds_for_both_comparators',
    recognized_non_skill_positions=sorted(NON_SKILL),
    causal_effect=False, consumer_promotion=False, motivating_october4_excluded=True)
FILES = ('kalshi_stat_only_next_teammate_study.py',
    'kalshi_stat_only_context_price_audit.py', 'kalshi_stat_only_teammate_context.py',
    'kalshi_stat_only_next_eval.py', 'kalshi_stat_only_next_series.py',
    'kalshi_stat_only_remote_anchor.py', 'kalshi_stat_only_win_uncertainty.py',
    'kalshi_role_shadow_eval.py', 'kalshi_stat_only_next_context.py',
    'kalshi_stat_only_transfer.py', 'kalshi_market_settlement.py',
    'kalshi_role_shadow.py')


def team(value: str) -> str:
    normalized = source_team(value)
    return 'JAC' if normalized == 'JAX' else normalized


def _venue_club(source: dict, target_id: str) -> str | None:
    """Extra opponent metadata is not guaranteed by the original forecast gates."""
    target = source['targets'].get(target_id)
    details = target.get('details') if isinstance(target, dict) else None
    value = details.get('abbreviation') if isinstance(details, dict) else None
    return team(value) if isinstance(value, str) and value.strip() else None


def implementation() -> dict:
    """Bind the study and reused score/chronology helpers, independent of CRLF."""
    root = Path(__file__).resolve().parent
    result = {}
    for name in FILES:
        path = root / name
        if path.is_symlink() or not path.is_file():
            raise ValueError('Study implementation missing or linked')
        result[name] = hashlib.sha256(path.read_bytes().replace(b'\r\n', b'\n')).hexdigest()
    return result


def marker_path(root: Path) -> Path:
    match = ROOT_NAME.fullmatch(root.name)
    if match is None:
        raise ValueError('Unexpected prospective capture name')
    return Path('docs/verification') / f'next-nfl-context-{match["stamp"]}-anchor.json'


def marker(receipt: dict) -> dict:
    return dict(protocol=MARKER_VERSION, receipt_sha256=digest(receipt),
                commitment_sha256=receipt['commitment_sha256'],
                policy_sha256=digest(receipt['policy']),
                implementation_sha256=digest(receipt['implementation']))


def _rows(path: Path, columns: list[str], limit: int = 2_000_000) -> list[dict]:
    if path.is_symlink() or not path.is_file() or not 0 < path.stat().st_size <= limit:
        raise ValueError('Study source missing or unbounded')
    rows = pq.read_table(path, columns=columns).to_pylist()
    labels = set(columns) - {'season','week','targets'}
    if any((row[key] is not None and not isinstance(row[key], str))
           for row in rows for key in labels):
        raise pa.ArrowInvalid('Unsupported context identity or label type')
    if any((row[key] is not None and type(row[key]) is not int)
           for row in rows for key in set(columns) & {'season','week'}):
        raise pa.ArrowInvalid('Unsupported context season or week type')
    return rows


def _target_share(stats: list[dict], schedule: list[dict], club: str,
                  season: int, week: int, acute: set[str], before: datetime) -> Decimal | None:
    prior = [g for g in schedule if g['season'] == season and g['game_type'] == 'REG'
             and g['week'] < week and club in (team(g['home_team']), team(g['away_team']))
             and date.fromisoformat(g['gameday']) < before.astimezone(NY).date()]
    prior.sort(key=lambda g: (g['gameday'], g['week']))
    weeks = [g['week'] for g in prior[-POLICY['prior_completed_team_games']:]]
    if not weeks or len(weeks) != len(set(weeks)):
        return None
    selected = [r for r in stats if r['season'] == season and r['season_type'] == 'REG'
                and r['week'] in weeks and team(r['team']) == club]
    if {r['week'] for r in selected} != set(weeks):
        return None
    total = affected = Decimal(0)
    seen = set()
    for row in selected:
        # Missing targets and identities cannot silently become zero exposure.
        identity = (row['week'], row['player_id'])
        if not row['player_id'] or identity in seen or row['targets'] is None:
            return None
        seen.add(identity)
        try:
            targets = Decimal(str(row['targets']))
        except (InvalidOperation, TypeError, ValueError):
            return None
        if not targets.is_finite() or targets < 0:
            return None
        total += targets
        if row['player_id'] in acute:
            affected += targets
    return affected / total if total > 0 else None


def membership(subject: str, club: str, season: int, week: int,
               rosters: list[dict], injuries: list[dict], stats: list[dict],
               schedule: list[dict], *, before: datetime) -> dict:
    """No historical-team fallback or inferred final status for unresolved reports."""
    unavailable = dict(teammate_context_stratum='coverage_unavailable',
                       coverage_reason='current_roster_or_report_unavailable',
                       acute_target_share=None, subject_report_status=None)
    current = [r for r in rosters if r['season'] == season and r['week'] == week
               and r['game_type'] == 'REG']
    club_roster = [r for r in current if team(r['team']) == club]
    subject_rows = [r for r in current if r['gsis_id'] == subject]
    ids = [r['gsis_id'] for r in club_roster]
    if (not club or not subject or not club_roster or any(not value for value in ids)
            or len(ids) != len(set(ids)) or len(subject_rows) != 1
            or team(subject_rows[0]['team']) != club or subject_rows[0]['status'] != 'ACT'):
        return unavailable
    reports = [r for r in injuries if r['season'] == season and r['week'] == week
               and r['season_type'] == 'REG' and team(r['team']) == club]
    report_ids = [r['gsis_id'] for r in reports]
    if (not reports or any(not value for value in report_ids)
            or len(report_ids) != len(set(report_ids))
            or not set(report_ids) <= set(ids)
            or any(not isinstance(r['position'], str) or r['position'] not in bins.SKILL | NON_SKILL for r in reports)
            or any(sum(r['gsis_id'] == gsis for r in current) != 1 for gsis in report_ids)):
        return unavailable
    teammates = [r for r in reports if r['gsis_id'] != subject and r['position'] in bins.SKILL]
    if any(r['report_status'] not in bins.ACUTE | {'Questionable'} for r in teammates):
        return dict(unavailable, coverage_reason='skill_teammate_final_status_unavailable')
    acute = {r['gsis_id'] for r in teammates if r['report_status'] in bins.ACUTE}
    share = _target_share(stats, schedule, club, season, week, acute, before) if acute else Decimal(0)
    label = bins.stratum(share, bool(acute), any(r['report_status'] == 'Questionable' for r in teammates))
    status = next((r['report_status'] for r in reports if r['gsis_id'] == subject), 'not_listed')
    return dict(teammate_context_stratum=label,
        coverage_reason='prior_target_coverage_unavailable' if share is None else 'observed',
        acute_target_share=str(share) if share is not None else None,
        subject_report_status=status)


def build(values: dict, source_dir: Path, commitment: dict, *, now: datetime) -> dict:
    decided = clock(values['decisions']['decided_at'])
    first = clock(commitment['first_selected_start_at'])
    if now.utcoffset() is None or not clock(START) <= decided <= now < first:
        raise ValueError('Study receipt requires a new, pregame prospective capture')
    context_dir = source_dir.parent / 'context'
    source_hash = context.verify(context_dir, before=decided)
    if source_hash != commitment.get('context_receipt_sha256'):
        raise ValueError('Study context differs from primary commitment')
    receipt, _ = single._input(context_dir / 'receipt.json', 100_000)
    schedule_path = source_dir.parent / 'schedule.parquet'
    schedule = _rows(schedule_path, ['season','game_type','week','gameday','home_team','away_team'], 1_000_000)
    season = decided.year if decided.month >= 9 else decided.year - 1
    rosters, injuries, stats = [], [], []
    study_source_status = receipt['status']
    if receipt['status'] == 'observed':
        try:
            rosters = _rows(context_dir / f'roster_weekly_{season}.parquet',
                ['season','game_type','week','team','gsis_id','status'])
            injuries = _rows(context_dir / f'injuries_{season}.parquet',
                ['season','season_type','week','team','gsis_id','position','report_status'])
            stats = _rows(source_dir / f'stats_player_week_{season}.parquet',
                ['season','season_type','week','team','player_id','targets'], 20_000_000)
        except pa.ArrowException:
            # Raw bytes were authenticated above; an optional diagnostic cannot
            # infer healthy context from an unsupported source schema.
            rosters, injuries, stats = [], [], []
            study_source_status = 'context_schema_unavailable'
    cohort, _ = unpack(values['pair'])
    fixtures = series._fixture_map(values['market'], cohort)
    source = values['market']['evidence']['sources']['kalshi']
    offers = {r['ticker']: r for r in cohort['selections']}
    forecasts = {r['ticker']: r for r in values['forecast']['forecasts']}
    rows = []
    for candidate in values['decisions']['candidates']:
        ticker = candidate['ticker']
        f, offer = forecasts[ticker], offers[ticker]
        start = clock(f['scheduled_game_start_time'])
        club = _venue_club(source, offer['team_target_id'])
        fixture = fixtures[f['milestone_id']]
        clubs = {_venue_club(source, key) for key in fixture[1:]}
        games = [g for g in schedule if g['season'] == season and g['game_type'] == 'REG'
                 and g['gameday'] == start.astimezone(NY).date().isoformat()
                 and None not in clubs and {team(g['home_team']), team(g['away_team'])} == clubs]
        eligible = timedelta(0) < start - decided <= timedelta(hours=POLICY['maximum_decision_to_kickoff_hours'])
        observed = dict(teammate_context_stratum='coverage_unavailable',
            coverage_reason=study_source_status if study_source_status != 'observed' else 'source_unavailable',
            acute_target_share=None, subject_report_status=None)
        if len(games) != 1 or club not in clubs or None in clubs:
            observed['coverage_reason'] = 'exact_fixture_schedule_unavailable'
        elif study_source_status == 'observed':
            observed = membership(f['gsis_player_id'], club, season, games[0]['week'],
                rosters, injuries, stats, schedule, before=decided)
        rows.append(dict(candidate, high_probability=Decimal(candidate['model_win_probability']) >= Decimal('.75'),
            gsis_player_id=f['gsis_player_id'], quoted_current_team=club,
            fixture_key=list(fixture), within_context_window=eligible, **observed))
    fixtures_record = [dict(fixture_key=list(fixture), within_context_window=(
        timedelta(0) < clock(fixture[0]) - decided <= timedelta(hours=POLICY['maximum_decision_to_kickoff_hours'])))
        for fixture in sorted(fixtures.values())]
    return dict(protocol=VERSION, recorded_at=now.isoformat(), policy=POLICY.copy(),
        implementation=implementation(), commitment_sha256=digest(commitment),
        source_context_receipt_sha256=source_hash, rows=rows, fixtures=fixtures_record,
        fixed_candidates=len(rows), source_status=receipt['status'], study_source_status=study_source_status,
        edge_established=False, qualified_picks=0, causal_context_effect_established=False)


def verify_receipt(receipt: dict, values: dict, source_dir: Path, commitment: dict) -> None:
    if build(values, source_dir, commitment, now=clock(receipt['recorded_at'])) != receipt:
        raise ValueError('Prospective membership, policy or implementation changed')


def prepare(root: Path, values: dict, commitment: dict, *, now: datetime) -> tuple[Path, dict]:
    """Exclusive local receipt; only the hash-only marker enters the private repo."""
    path = root / 'teammate-study.json'
    if path.exists() or path.is_symlink():
        raise ValueError('Prospective study receipt already exists')
    receipt = build(values, root / 'sources', commitment, now=now)
    with path.open('x', encoding='utf-8') as stream:
        json.dump(receipt, stream, sort_keys=True, indent=2, allow_nan=False)
    return marker_path(root), marker(receipt)


def verify_marker(receipt: dict, commitment: dict, oid: str, primary_path: str) -> dict:
    proof = anchor.verify(commitment, oid, primary_path)
    root = Path(primary_path).name.removesuffix('-anchor.json')
    path = marker_path(Path(root))
    saved = json.loads(anchor._run('git', 'show', f'{oid}:{path.as_posix()}'))
    if saved != marker(receipt) or clock(receipt['recorded_at']) > clock(proof['remote_pushed_at']):
        raise ValueError('Study marker changed or not server-published before kickoff')
    return proof


def aggregate(cases: list[dict], *, now: datetime) -> dict:
    if now.utcoffset() is None or not 0 < len(cases) <= series.MAX_CASES:
        raise ValueError('Study clock or case count invalid')
    prepared = []
    artifacts = set()
    for case in cases:
        values, _, prices = single.committed_preflight(case['inputs'], Path(case['source_dir']), case['commitment'])
        receipt, _ = single._input(Path(case['source_dir']).parent / 'teammate-study.json', 500_000)
        verify_receipt(receipt, values, Path(case['source_dir']), case['commitment'])
        proof = verify_marker(receipt, case['commitment'], case['anchor_commit_oid'], case['anchor_marker_path'])
        single.evaluate(case['inputs'], Path(case['source_dir']), case['commitment'], case['settlements'], now=now)
        cohort, _ = unpack(values['pair'])
        _, states = venue_results(values['market'], cohort, case['settlements'], now=now)
        artifact = (values['forecast']['frozen_model_artifact_sha256'], values['forecast']['frozen_implementation_sha256'])
        artifacts.add(artifact)
        prepared.append((clock(proof['remote_pushed_at']), digest(case['commitment']), receipt, values, prices, states))
    if len(artifacts) != 1:
        raise ValueError('Study cannot mix frozen model implementations')
    return combine(prepared)


def combine(prepared: list[tuple]) -> dict:
    """Authenticated cases only. Ownership precedes context, price or outcome filtering."""
    seen = set()
    rows, forecasts, controls, prices, states = [], [], [], {}, {}
    counts = Counter()
    receipts = []
    for _, commitment_hash, receipt, values, case_prices, case_states in sorted(prepared, key=lambda r: (r[0], r[1])):
        receipts.append(digest(receipt))
        eligible_fixtures = {tuple(r['fixture_key']) for r in receipt['fixtures'] if r['within_context_window']}
        owned = eligible_fixtures - seen
        counts['duplicate_eligible_games_excluded'] += len(eligible_fixtures & seen)
        counts['independent_eligible_games'] += len(owned)
        seen.update(eligible_fixtures)
        f_by = {r['ticker']: r for r in values['forecast']['forecasts']}
        c_by = {r['ticker']: r for r in values['control']['forecast_rows']}
        for row in receipt['rows']:
            counts['all_capture_candidates'] += 1
            if not row['within_context_window']:
                counts['outside_context_window_candidates'] += 1
                continue
            fixture = tuple(row['fixture_key'])
            if fixture not in owned:
                counts['duplicate_eligible_candidates_excluded'] += 1
                continue
            ticker = row['ticker']
            unique = commitment_hash + ':' + ticker
            game = json.dumps(fixture, separators=(',', ':'))
            rows.append(dict(row, ticker=unique, milestone_id=game))
            forecasts.append(dict(f_by[ticker], ticker=unique, milestone_id=game))
            controls.append(dict(c_by[ticker], ticker=unique))
            prices[unique], states[unique] = case_prices[ticker], case_states[ticker]
    summarized = comparison.summarize(rows, forecasts, controls, prices, states)
    scopes = dict(all_prospective_candidates=summarized['all_original_70'],
                  fixed_probability_ge_75pct_subset=summarized['original_high_probability_11'])
    primary = scopes['all_prospective_candidates']['strata'][POLICY['primary_group']]
    supported = (primary['complete_result_and_price_coverage']
        and primary['same_price_paired_games'] >= POLICY['minimum_primary_paired_independent_games']
        and series._favorable(primary['model_minus_market_bounds'] or {}, 'market')
        and series._favorable(primary['model_minus_strict_prior20_bounds'] or {}, 'prior20'))
    if counts['all_capture_candidates'] != len(rows) + counts['outside_context_window_candidates'] + counts['duplicate_eligible_candidates_excluded']:
        raise ValueError('Study lost a fixed candidate')
    return dict(protocol=VERSION, policy=POLICY.copy(), implementation=implementation(),
        frozen_receipt_sha256=receipts, candidate_accounting=dict(sorted(counts.items())),
        scopes=scopes, primary_group_association_supported=bool(supported),
        motivating_october4_excluded=True, remote_pregame_anchor_verified=True,
        causal_context_effect_established=False, edge_established=False,
        qualified_picks=0, roi=None, fills_verified=False, execution_ready=False)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--manifest', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    if args.output.exists() or args.output.is_symlink():
        parser.error('Study output must be exclusive')
    manifest, _ = single._input(args.manifest, 100_000)
    if manifest.get('protocol') != VERSION or not 0 < len(manifest.get('cases', [])) <= series.MAX_CASES:
        parser.error('Invalid prospective study manifest')
    root = args.manifest.resolve().parent
    cases = []
    for row in manifest['cases']:
        if set(row) != set(single.LIMITS) | {'source_dir','commitment','settlements','anchor_commit_oid','anchor_marker_path'}:
            parser.error('Invalid prospective case scope')
        commitment, _ = single._input(series._local(root, row['commitment']), 10_000)
        # Authenticate pregame evidence before the settlement file is read.
        inputs = {name: str(series._local(root, row[name])) for name in single.LIMITS}
        values, pre, _ = single.committed_preflight(inputs, series._local(root, row['source_dir']), commitment)
        now = datetime.now(timezone.utc)
        if now < clock(pre['first_eligible_settlement_at']):
            parser.error('Before full-cohort result gate; settlement input not read')
        receipt, _ = single._input(series._local(root, row['source_dir']).parent / 'teammate-study.json', 500_000)
        verify_receipt(receipt, values, series._local(root, row['source_dir']), commitment)
        verify_marker(receipt, commitment, row['anchor_commit_oid'], row['anchor_marker_path'])
        settlements, _ = single._input(series._local(root, row['settlements']), 30_000_000)
        cases.append(dict(inputs=inputs, source_dir=series._local(root, row['source_dir']),
            commitment=commitment, settlements=settlements,
            anchor_commit_oid=row['anchor_commit_oid'], anchor_marker_path=row['anchor_marker_path']))
    report = aggregate(cases, now=datetime.now(timezone.utc))
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open('x', encoding='utf-8') as stream:
        json.dump(report, stream, sort_keys=True, indent=2, allow_nan=False)
    print(json.dumps({key: report[key] for key in ('protocol','primary_group_association_supported','edge_established','qualified_picks')}, sort_keys=True))


if __name__ == '__main__':
    main()
