"""Separate forward minutes commitments; frozen NBA stat hashes stay unchanged."""
from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
import hashlib
import math
import re

import sqlalchemy as sa

from sportsbet.ingestion.provenance import row_sha256

FIELDS=('player_id','player_name','game_id','game_date','season','team_abbreviation','minutes')
VERSION='nba-recorded-minutes-v1'


def minute_value(value):
    if hasattr(value,'item') and callable(value.item):value=value.item()
    if value is None or isinstance(value,float) and math.isnan(value):return None
    if isinstance(value,bool) or not isinstance(value,(int,float,Decimal)):
        raise ValueError('Invalid NBA minutes')
    try:
        numeric=Decimal(str(value))
        if not numeric.is_finite() or not 0<=numeric<=Decimal('999.9'):
            raise ValueError('Invalid NBA minutes')
        return float(numeric.quantize(Decimal('.1'),rounding=ROUND_HALF_UP))
    except InvalidOperation:
        raise ValueError('Invalid NBA minutes') from None


def participation_record(row):
    result={key:row[key] for key in FIELDS}
    for key in ('player_id','season'):
        if hasattr(result[key],'item'):result[key]=result[key].item()
    day=result['game_date']
    if isinstance(day,str):day=date.fromisoformat(day)
    if (type(result['player_id']) is not int or not 0<result['player_id']<=2147483647
            or type(result['season']) is not int or not 2000<=result['season']<=2100
            or not isinstance(result['game_id'],str) or not re.fullmatch('[A-Za-z0-9_-]{1,30}',result['game_id'])
            or not isinstance(result['player_name'],str) or not 0<len(result['player_name'].strip())<=100
            or any(ord(c)<32 for c in result['player_name'])
            or type(day) is not date or not date(result['season'],7,1)<=day<=date(result['season']+1,6,30)
            or not isinstance(result['team_abbreviation'],str) or not re.fullmatch('[A-Z]{2,3}',result['team_abbreviation'])):
        raise ValueError('Invalid NBA participation identity')
    result['game_date']=day
    result['minutes']=minute_value(result['minutes'])
    return result


def prepare_participation(rows):
    """Bind actual provider input minutes, not an inferred legacy database value."""
    prepared=[];seen=set()
    for row in rows:
        record=participation_record(row)
        key=(record['player_id'],record['game_id'])
        if key in seen:raise ValueError('Duplicate NBA participation identity')
        seen.add(key)
        observed=row['source_observed_at']
        if (row['source_provider'] not in ('nba','espn') or not isinstance(observed,datetime)
                or observed.utcoffset() is None or record['game_date']>observed.date()
                or not isinstance(row['source_record_sha256'],str)
                or re.fullmatch('[0-9a-f]{64}',row['source_record_sha256']) is None):
            raise ValueError('Invalid NBA participation source')
        prepared.append(record|dict(source_provider=row['source_provider'],
            source_record_sha256=row_sha256(record),source_observed_at=observed,
            stat_record_sha256=row['source_record_sha256'],source_sha256=row['source_sha256']))
    # The official source's old normalized stat batch omits minutes. Retain a
    # separate scope-bound minutes batch; ESPN already supplies exact raw bytes.
    for season in {r['season'] for r in prepared if r['source_provider']=='nba'}:
        hashes=sorted(r['source_record_sha256'] for r in prepared
                      if r['source_provider']=='nba' and r['season']==season)
        digest=row_sha256(dict(provider='nba',version=VERSION,season=season,
            record_set_sha256=hashlib.sha256('\n'.join(hashes).encode()).hexdigest()))
        for row in prepared:
            if row['source_provider']=='nba' and row['season']==season:row['source_sha256']=digest
    if any(not isinstance(r['source_sha256'],str) or re.fullmatch('[0-9a-f]{64}',r['source_sha256']) is None for r in prepared):
        raise ValueError('Invalid NBA participation source commitment')
    return sorted(prepared,key=lambda r:(r['player_id'],r['game_id']))


def store_participation(conn,rows,*,complete_season=None):
    """Append accepted provider rows in the same transaction as the stat write."""
    if not rows:return
    if complete_season is not None:
        if (any(r['source_provider']!='nba' or r['season']!=complete_season for r in rows)
                or len({(r['source_sha256'],r['source_observed_at']) for r in rows})!=1):
            raise ValueError('Invalid complete NBA participation scope')
        # An omitted row in a complete official season is unknown, not a DNP.
        # Select latest identities first so an old season/team is not resurrected.
        prior=conn.execute(sa.text('''WITH latest AS (
            SELECT DISTINCT ON (player_id,game_id) * FROM public.nba_participation_versions
            ORDER BY player_id,game_id,recorded_at DESC,version_id DESC)
            SELECT * FROM latest WHERE season=:season AND source_provider='nba'
              AND minutes IS NOT NULL'''),{'season':complete_season}).mappings().all()
        incoming={(r['player_id'],r['game_id']) for r in rows}
        removed=[]
        for previous in prior:
            if (previous['player_id'],previous['game_id']) in incoming:continue
            record=participation_record(dict(previous)|{'minutes':None})
            removed.append(record|dict(source_provider='nba',source_sha256=rows[0]['source_sha256'],
                source_observed_at=rows[0]['source_observed_at'],source_record_sha256=row_sha256(record)))
        if removed:
            conn.execute(sa.text('''INSERT INTO public.nba_participation_versions
                (player_id,player_name,game_id,game_date,season,team_abbreviation,minutes,
                 source_provider,source_sha256,source_record_sha256,source_observed_at)
                VALUES (:player_id,:player_name,:game_id,:game_date,:season,:team_abbreviation,:minutes,
                    :source_provider,:source_sha256,:source_record_sha256,:source_observed_at)'''),removed)
    conn.execute(sa.text('''INSERT INTO public.nba_participation_versions
        (player_id,player_name,game_id,game_date,season,team_abbreviation,minutes,
         source_provider,source_sha256,source_record_sha256,source_observed_at)
        SELECT i.* FROM (SELECT CAST(:player_id AS integer) AS player_id,
            CAST(:player_name AS varchar(100)) AS player_name,
            CAST(:game_id AS varchar(30)) AS game_id,CAST(:game_date AS date) AS game_date,
            CAST(:season AS smallint) AS season,CAST(:team_abbreviation AS varchar(3)) AS team_abbreviation,
            CAST(:minutes AS numeric(4,1)) AS minutes,CAST(:source_provider AS varchar(10)) AS source_provider,
            CAST(:source_sha256 AS varchar(64)) AS source_sha256,
            CAST(:source_record_sha256 AS varchar(64)) AS source_record_sha256,
            CAST(:source_observed_at AS timestamptz) AS source_observed_at) i
        WHERE EXISTS (SELECT 1 FROM public.nba_player_gamelogs n
            WHERE n.player_id=i.player_id AND n.game_id=i.game_id
              AND n.game_date=i.game_date AND n.season=i.season
              AND n.team_abbreviation=i.team_abbreviation
              AND n.source_provider=i.source_provider
              AND n.source_record_sha256=:stat_record_sha256)'''),rows)
