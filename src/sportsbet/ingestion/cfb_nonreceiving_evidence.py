"""Verify explicit CFB passing/rushing finals from archived free ESPN sources.

Missing categories and zero attempts stay unresolved. This path never changes the
receiving-only evidence contract or historical game-log model inputs.
"""
from __future__ import annotations

from datetime import datetime, timezone
import json
import re
from zoneinfo import ZoneInfo

from sportsbet.ingestion.cfb_final_evidence import SUMMARY, GAMELOG, digest, integer
from sportsbet.ingestion.provenance import stat_row_sha256
from sportsbet.ledger import utc_timestamp, verified_settlement_evidence, VERIFIED_SETTLEMENT_SOURCE
from sportsbet.schedules import scheduled_stat_teams
from sportsbet.settlement import _candidate


def inspect_bundle(bundle: dict, *, now=None) -> list[dict]:
    now = now or datetime.now(timezone.utc)
    if (bundle.get('version') != 1 or not 1 <= len(bundle['players']) <= 50
            or not 1 <= len(bundle['sources']) <= 100):
        raise ValueError('Invalid recovery bundle bounds')
    sources = {}; size = 0
    for source in bundle['sources']:
        raw = source['response_text']; length = len(raw.encode('utf-8')); size += length
        if (not 0 < length <= 4_000_000 or size > 20_000_000
                or source['url'] in sources or digest(raw) != source['sha256']
                or utc_timestamp(source['observed_at']) > now):
            raise ValueError('Invalid source commitment')
        sources[source['url']] = source

    def read(url):
        receipt = sources[url]
        return json.loads(receipt['response_text']), receipt

    results = []; seen = set()
    for player in bundle['players']:
        identity = player['player_id']; event = player['espn_event_id']
        if (any(not isinstance(value, str) or not re.fullmatch(r'[1-9][0-9]{0,14}', value)
                for value in (identity, event)) or (identity, event) in seen):
            raise ValueError('Invalid or duplicate player/game identity')
        seen.add((identity, event))
        summary, final = read(SUMMARY + event)
        header = summary['header']; comp, = header['competitions']
        if (header['id'] != event or comp['id'] != event
                or header['league']['slug'] != 'college-football'
                or header['season']['type'] != 2
                or comp['status']['type']['completed'] is not True
                or comp['status']['type']['name'] != 'STATUS_FINAL'):
            raise ValueError('Completed CFB regular-season game required')
        season = header['season']['year']; week = header['week']
        start = utc_timestamp(comp['date']); final_time = utc_timestamp(final['observed_at'])
        day = start.astimezone(ZoneInfo('America/New_York')).date().isoformat()
        if (type(season) is not int or season != (start.year if start.month >= 8 else start.year - 1)
                or type(week) is not int or not 1 <= week <= 25 or day != player['date']
                or not start <= final_time <= now):
            raise ValueError('Invalid final chronology')
        home, = [team for team in comp['competitors'] if team['homeAway'] == 'home']
        away, = [team for team in comp['competitors'] if team['homeAway'] == 'away']
        if len(comp['competitors']) != 2 or home['id'] == away['id']:
            raise ValueError('Invalid game competitors')
        for team in (home, away):
            if (not re.fullmatch(r'[1-9][0-9]{0,14}', team['id'])
                    or team['team']['id'] != team['id']
                    or any(not isinstance(team['team'].get(key), str)
                        or not team['team'][key].strip() or len(team['team'][key]) > limit
                        for key, limit in (('displayName', 100), ('abbreviation', 10)))):
                raise ValueError('Invalid team identity')
        game = dict(provider_event_id=event, date=day, game_time=start.isoformat(), completed=True,
            home_name=home['team']['displayName'], away_name=away['team']['displayName'],
            home_abbr=home['team']['abbreviation'], away_abbr=away['team']['abbreviation'])
        scheduled_stat_teams('cfb', game)
        data, receipt = read(GAMELOG.format(player=identity, season=season))
        observed = utc_timestamp(receipt['observed_at'])
        if not final_time <= observed <= now:
            raise ValueError('Game log predates observed final status')
        for key, value in (('season', str(season)), ('league', 'college-football')):
            matched, = [item for item in data['filters'] if item['name'] == key]
            if matched['value'] != value:
                raise ValueError('Wrong game-log scope')
        result = dict(player_id=identity, game=game, status='unavailable',
            reason='explicit_game_stats_missing')
        entries = [(category, item) for season_type in data['seasonTypes']
            for category in season_type['categories'] if category['type'] == 'event'
            for item in category.get('events', []) if item['eventId'] == event]
        if not entries:
            results.append(result); continue
        if len(entries) != 1 or entries[0][0].get('splitType') != '2':
            raise ValueError('Ambiguous game-log event or season type')
        entry = entries[0][1]; names = data['names']
        if (any(type(category['count']) is not int or not 0 <= category['count'] <= 100
                for category in data['categories'])
                or len(names) != len(set(names)) or len(names) != len(entry['stats'])
                or sum(category['count'] for category in data['categories']) != len(names)):
            raise ValueError('Ambiguous game-log statistic columns')
        values = dict(zip(names, entry['stats'], strict=True))
        meta = data['events'][event]
        if (meta['id'] != event or utc_timestamp(meta['gameDate']) != start
                or meta['week'] != week or meta['homeTeamId'] != home['id']
                or meta['awayTeamId'] != away['id'] or meta['homeTeamScore'] != home['score']
                or meta['awayTeamScore'] != away['score']):
            raise ValueError('Game-log event does not match final summary')
        team, = [side for side in (home, away) if side['id'] == meta['team']['id']]
        opponent = away if team is home else home
        if meta['opponent']['id'] != opponent['id']:
            raise ValueError('Wrong opponent identity')
        boxes = summary['boxscore']['players']
        if len(boxes) != 2 or {box['team']['id'] for box in boxes} != {home['id'], away['id']}:
            raise ValueError('Ambiguous box-score teams')
        box, = [item for item in boxes if item['team']['id'] == team['id']]
        if any(athlete['athlete']['id'] == identity for item in boxes if item is not box
                for category in item['statistics'] for athlete in category['athletes']):
            raise ValueError('Athlete occurs on both teams')

        def box_stats(name):
            categories = [category for category in box['statistics'] if category['name'] == name]
            if len(categories) > 1:
                raise ValueError('Duplicate box-score category')
            if not categories:
                return None
            category = categories[0]
            matched = [athlete for athlete in category['athletes']
                if athlete['athlete']['id'] == identity]
            if len(matched) > 1:
                raise ValueError('Duplicate athlete in box-score category')
            if not matched:
                return None
            athlete = matched[0]; labels = category['labels']
            if len(labels) != len(set(labels)) or len(labels) != len(athlete['stats']):
                raise ValueError('Ambiguous box-score statistics')
            return dict(zip(labels, athlete['stats'], strict=True)), athlete['athlete']

        verified = {}; activity = []; athlete_identity = None
        for category, attempts_name, yards_name in (
                ('passing', 'passingAttempts', 'passingYards'),
                ('rushing', 'rushingAttempts', 'rushingYards')):
            if attempts_name not in values or yards_name not in values:
                continue
            attempts = integer(values[attempts_name], nonnegative=True)
            yards = integer(values[yards_name])
            if attempts == 0:
                if yards != 0:
                    raise ValueError('Yards without attempts')
                continue
            box_entry = box_stats(category)
            if box_entry is None:
                continue
            stats, athlete = box_entry
            if category == 'passing':
                match = re.fullmatch(r'([0-9]{1,3})/([0-9]{1,3})', stats['C/ATT'])
                if not match:
                    raise ValueError('Invalid final passing attempts')
                completions, box_attempts = map(int, match.groups())
                if (completions > box_attempts or box_attempts != attempts
                        or ('completions' in values
                            and completions != integer(values['completions'], nonnegative=True))):
                    raise ValueError('Final passing attempts disagree')
            elif integer(stats['CAR'], nonnegative=True) != attempts:
                raise ValueError('Final rushing attempts disagree')
            if integer(stats['YDS']) != yards:
                raise ValueError('Final sources disagree')
            if (not isinstance(athlete.get('displayName'), str)
                    or not 0 < len(athlete['displayName'].strip()) <= 100
                    or (athlete_identity is not None
                        and athlete_identity['displayName'] != athlete['displayName'])):
                raise ValueError('Conflicting athlete identity')
            athlete_identity = athlete
            verified[yards_name] = yards
            activity.append(dict(category=category, attempts=attempts, yards=yards))
        if not activity:
            results.append(result); continue
        row = dict(game_id=int(event), athlete_id=int(identity),
            player_name=athlete_identity['displayName'], team_id=int(team['id']),
            passing_yards=verified.get('passingYards'), rushing_yards=verified.get('rushingYards'),
            receiving_yards=None, receptions=None, season=season, week=week,
            game_date=start.date().isoformat(), is_home=team is home,
            team_name=team['team']['displayName'],
            team_abbreviation=team['team']['abbreviation'],
            opponent_id=int(opponent['id']), opponent_name=opponent['team']['displayName'],
            opponent_abbreviation=opponent['team']['abbreviation'])
        commitments = [{key: source[key] for key in ('url', 'sha256', 'observed_at')}
            for source in (final, receipt)]
        source = dict(version=1, kind='cfb_explicit_passing_rushing_game_log',
            athlete_id=identity, event_id=event, offensive_activity=activity, sources=commitments)
        result.update(status='verified_explicit_stats', stat_row=row,
            observed_at=observed.isoformat(), stat_record_sha256=stat_row_sha256('cfb', row),
            source_evidence=source,
            source_sha256=digest(json.dumps(source, sort_keys=True, separators=(',', ':'))))
        result.pop('reason'); results.append(result)
    return results


def plan_recovery(rows: list[dict], evidence: list[dict]) -> dict:
    updates = []; unresolved = []
    for prediction in rows:
        if (prediction.get('outcome') is not None or prediction.get('sport') != 'cfb'
                or prediction.get('prop_type') not in ('pass_yds', 'rush_yds')):
            continue
        matches = []
        for item in evidence:
            if item['player_id'] != prediction.get('player_id'):
                continue
            try:
                candidate = _candidate(prediction, 'cfb', [item['game']])
            except (KeyError, TypeError, ValueError, ArithmeticError):
                continue
            if candidate and utc_timestamp(prediction['game_start_time']) == utc_timestamp(item['game']['game_time']):
                matches.append((item, candidate))
        if len(matches) != 1:
            continue
        item, (game, day, line) = matches[0]
        column = 'passing_yards' if prediction['prop_type'] == 'pass_yds' else 'rushing_yards'
        if item['status'] != 'verified_explicit_stats' or item['stat_row'][column] is None:
            unresolved.append(prediction['prediction_id']); continue
        actual = item['stat_row'][column]
        outcome = 'push' if actual == line else ((actual > line) == (prediction['direction'] == 'over'))
        proof = dict(schedule_identity_version=2,
            **{key: game[key] for key in ('provider_event_id', 'date', 'home_abbr',
                'away_abbr', 'home_name', 'away_name', 'completed', 'game_time')},
            player_id=prediction['player_id'], prop_type=prediction['prop_type'],
            actual_value=str(actual), stat_provider='espn',
            stat_source_sha256=item['source_sha256'],
            stat_record_sha256=item['stat_record_sha256'],
            stat_observed_at=item['observed_at'], stat_row=item['stat_row'],
            explicit_final_source=item['source_evidence'])
        ref = f"espn_schedule+espn:{game['provider_event_id']}:sha256:{digest(json.dumps(proof, sort_keys=True, separators=(',', ':')))}"
        if not verified_settlement_evidence(prediction, outcome,
                VERIFIED_SETTLEMENT_SOURCE, ref, item['observed_at'], actual, proof):
            raise ValueError('Recovery failed settlement proof contract')
        updates.append(dict(prediction_id=prediction['prediction_id'], outcome=outcome,
            actual=actual, source_ref=ref, observed_at=item['observed_at'],
            evidence=proof, payload=prediction))
    return dict(updates=updates, unresolved=unresolved)
