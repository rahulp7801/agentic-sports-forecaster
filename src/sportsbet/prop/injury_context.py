"""Descriptive recorded participation evidence for current availability risks."""
from __future__ import annotations

from datetime import date, datetime

import asyncpg

from sportsbet.prop.availability import blocks_unadjusted_teammate_context
from sportsbet.prop.nba_context_producer import nba_team_abbreviation
from sportsbet.schedules import STAT_TEAM_ALIASES

OFFENSE = frozenset({'QB','RB','FB','WR','TE','C','G','OG','OT','T','OL'})
DEFENSE = frozenset({'DE','DT','DL','NT','LB','ILB','OLB','CB','DB','S','FS','SS'})
BASKETBALL = frozenset({'PG','SG','SF','PF','C','G','F','G-F','F-G','F-C','C-F'})
NFL_SPECIAL_TEAMS = frozenset({'K','P','LS'})
RISK = frozenset({'out','inactive','injured reserve','doubtful','questionable'})


def relevant_availability_reports(context: dict | None, subject_team: str,
                                  subject_player: str, sport: str, limit: int | None = 8) -> list[dict]:
    """Return reported offensive teammates and opposing defenders that can affect the subject."""
    if not context or context.get('status') not in ('observed','partial'):
        return []
    candidates = []
    for team in context.get('teams', []):
        relation = 'teammate' if team.get('abbreviation') == subject_team else 'opponent'
        for report in team.get('reports', []):
            if relation == 'teammate' and report.get('player') == subject_player:
                continue
            position = str(report.get('position','')).strip().upper()
            if sport == 'nba':
                unit = ('offense' if relation=='teammate' else 'defense') if position in BASKETBALL else None
            else:
                unit = 'offense' if position in OFFENSE else 'defense' if position in DEFENSE else None
            if str(report.get('status','')).strip().lower() not in RISK:
                continue
            if (relation,unit) not in (('teammate','offense'),('opponent','defense')):
                continue
            row = dict(player=report['player'],status=report['status'],position=position,
                       team=team['abbreviation'],relationship=relation,unit=unit,
                       reported_at=report.get('reported_at'),source_url=team.get('injury_source_url'),
                       source_sha256=team.get('injury_source_sha256'))
            candidates.append(row)
    priority = {'out':0,'inactive':0,'injured reserve':0,'doubtful':1,'questionable':2}
    # Show gate-causing teammate absences before trimming the context list.
    # The scanner still evaluates the full report independently of this cap.
    ordered = sorted(candidates,key=lambda row:(
        not blocks_unadjusted_teammate_context(row),
        priority.get(row['status'].strip().lower(),3),row['relationship'],row['player']))
    return ordered if limit is None else ordered[:limit]


def screened_availability_reports(context: dict | None, subject_team: str,
                                  subject_player: str, sport: str,
                                  raw_teammates: list[dict]) -> list[dict]:
    """Keep relevant units and acute teammates whose unit cannot be established.

    The captured roster can identify a teammate even when its position does
    not establish offense or defense. Such a report remains a blocker and is
    retained for public explanation, without inventing a unit classification.
    """
    relevant = relevant_availability_reports(context, subject_team, subject_player, sport, limit=None)
    known = BASKETBALL if sport == 'nba' else OFFENSE | DEFENSE
    if sport == 'nfl':
        # Preserve the existing exclusion of known nonoffensive NFL specialists.
        known |= NFL_SPECIAL_TEAMS
    unknown = []
    for report in raw_teammates:
        position = str(report.get('position', '')).strip().upper()
        if (blocks_unadjusted_teammate_context(report)
                and position not in known):
            unknown.append(dict(player=report['player'], status=report['status'],
                                position=position or 'Unknown', reported_at=report['reported_at']))
    unknown.sort(key=lambda row:(row['status'].strip().lower(), row['player']))
    return unknown + relevant


def current_contexts(context: dict | None, subject_team: str, subject_player: str, sport: str) -> list[dict]:
    """Return relevant injury-report participants with exact identities for historical splits."""
    candidates = []
    pfr = context.get('pfr_player_identities', {}) if context else {}
    teams = context.get('teams', []) if context else []
    for row in relevant_availability_reports(context,subject_team,subject_player,sport):
        team=next((team for team in teams if team.get('abbreviation')==row['team']),None)
        if not team:
            continue
        row=dict(row)
        if sport == 'nfl':
            # Preserve roster ambiguity before consulting the crosswalk. A
            # missing mapping for one same-name player does not identify the other.
            matches = [identity for identity,name in team.get('roster_ids', {}).items()
                       if name == row['player']]
            if len(matches) != 1:
                continue
            player_id = pfr.get(matches[0])
            if not player_id:
                continue
            row['participant_id'] = player_id
            row['stat_team'] = STAT_TEAM_ALIASES['nfl'].get(row['team'],row['team'])
        else:
            try:
                row['stat_team'] = nba_team_abbreviation(team['name'])
            except ValueError:
                continue
        candidates.append(row)
    return candidates


def _summary(games: int, mean: object, hits: int) -> dict:
    return dict(games=games, mean=round(float(mean),2) if mean is not None else None,
                hit_rate=round(hits/games,4) if games else None)


def _sample_window(row: dict, cutoff: date) -> dict | None:
    """Retain the actual dated cohorts without changing their statistics."""
    result = {'cutoff': cutoff.isoformat()}
    for group in ('active', 'absent', 'unknown'):
        oldest, newest = row.get(group + '_oldest'), row.get(group + '_newest')
        count = int(row.get(group + '_games') or 0)
        if count == 0:
            if oldest is not None or newest is not None:
                return None
            result[group] = None
        elif type(oldest) is date and type(newest) is date and oldest <= newest < cutoff:
            result[group] = {'oldest': oldest.isoformat(), 'newest': newest.isoformat()}
        else:
            return None
    return result


def _has_observation_cutoff(observed_before: datetime | None) -> bool:
    if observed_before is None:
        return False
    if not isinstance(observed_before, datetime) or observed_before.utcoffset() is None:
        raise ValueError('Context observation cutoff requires an aware timestamp')
    return True


async def _nfl_split(conn, player_id: str, season: int, cutoff: date, prop_type: str,
                     line: float, direction: str, candidate: dict, observed_before: datetime | None = None) -> dict | None:
    _has_observation_cutoff(observed_before)
    from sportsbet.prop.nfl_participation_evidence import nfl_participation_split
    return await nfl_participation_split(conn,player_id,season,cutoff,prop_type,
        line,direction,candidate,observed_before)


async def _nba_split(conn, player_id: str, season: int, cutoff: date, prop_type: str,
                     line: float, direction: str, candidate: dict, observed_before: datetime | None = None) -> dict | None:
    _has_observation_cutoff(observed_before)
    from sportsbet.prop.nba_participation_evidence import nba_participation_split
    return await nba_participation_split(conn,player_id,season,cutoff,prop_type,
        line,direction,candidate,observed_before)


async def historical_availability_splits(pool, *, context: dict | None, subject_team: str,
        subject_player: str, sport: str, player_id: str, season: int, cutoff: date, prop_type: str,
        line: float, direction: str, observed_before: datetime | None = None) -> list[dict]:
    """Describe recorded participation cohorts; never mutate the model probability."""
    candidates = current_contexts(context,subject_team,subject_player,sport)
    if not candidates or direction not in ('over','under'):
        return []
    rows = []
    try:
        async with pool.acquire() as conn:
            for candidate in candidates:
                result = await (_nfl_split(conn,player_id,season,cutoff,prop_type,line,direction,candidate,observed_before)
                    if sport == 'nfl' else
                    _nba_split(conn,player_id,season,cutoff,prop_type,line,direction,candidate,observed_before))
                if result:
                    rows.append(result)
    except asyncpg.UndefinedTableError:
        return []
    return rows
