"""Collect bounded free-source evidence for audited NFL receiving-history gaps.

Writes local receipts and verified bundles only. Applying a bundle is a separate
reviewed-count/plan-digest operation in nfl_history_supplements.
"""
from __future__ import annotations

import argparse
from collections import defaultdict
from datetime import datetime, timezone
import json
from pathlib import Path
import re
from zoneinfo import ZoneInfo

import httpx

from sportsbet.ingestion.nfl_final_evidence import CORE, BASE, digest, inspect_bundle, _reference
from sportsbet.ledger import utc_timestamp
from sportsbet.quant.nfl_history_coverage import audit, SNAP_FIELDS
from sportsbet.quant.nfl_history_supplements import canonical, MAX_BYTES

MAX_RESPONSE_BYTES = 2_000_000
MAX_REQUESTS = 400
MAX_GAPS = 64
SITE = 'https://site.api.espn.com/apis/site/v2/sports/football/nfl/'


def allowed_url(url):
    return isinstance(url, str) and any(re.fullmatch(pattern, url) for pattern in (
        re.escape(SITE) + r'scoreboard\?dates=[0-9]{8}&limit=100',
        re.escape(SITE) + r'summary\?event=[1-9][0-9]*',
        re.escape(f'https://{CORE}{BASE}') + r'/events/[1-9][0-9]*/competitions/[1-9][0-9]*/competitors/[1-9][0-9]*/roster\?limit=100',
        re.escape(f'https://{CORE}{BASE}') + r'/events/[1-9][0-9]*/competitions/[1-9][0-9]*/competitors/[1-9][0-9]*/roster/[1-9][0-9]*/statistics/0(?:\?lang=en&region=us)?',
    ))


class ReceiptCache:
    def __init__(self, directory, *, client=None, now=None):
        self.directory = Path(directory)
        self.directory.mkdir(parents=True, exist_ok=True)
        self.client = client
        self.now = now or (lambda: datetime.now(timezone.utc))
        self.requests = 0

    def retain(self, source):
        """Seed from a previously retained receipt, preserving its timestamp."""
        self._validate(source, source['url'])
        path = self.directory / (digest(source['url']) + '.json')
        if not path.exists():
            path.write_text(canonical(source), encoding='utf-8')

    def _validate(self, source, url):
        if (not allowed_url(url) or source['url'] != url
                or not isinstance(source['response_text'], str)
                or not 0 < len(source['response_text'].encode('utf-8')) <= MAX_RESPONSE_BYTES
                or digest(source['response_text']) != source['sha256']
                or utc_timestamp(source['observed_at']) > self.now()):
            raise ValueError('Invalid cached source receipt')
        if not isinstance(json.loads(source['response_text']), dict):
            raise ValueError('Expected source object')

    def read(self, url, *, not_before=None):
        if not allowed_url(url):
            raise ValueError('Source URL outside free NFL evidence scope')
        path = self.directory / (digest(url) + '.json')
        if path.exists():
            source = json.loads(path.read_text(encoding='utf-8'))
            self._validate(source, url)
            if not_before is None or utc_timestamp(source['observed_at']) >= not_before:
                return source
        if self.client is None or self.requests >= MAX_REQUESTS:
            raise ValueError('Free-source request budget exhausted or offline')
        self.requests += 1
        # Never follow provider redirects or send API keys. Stream decoded bytes
        # so oversized or compressed responses cannot exceed the retained bound.
        with self.client.stream('GET', url, follow_redirects=False, timeout=20) as response:
            response.raise_for_status()
            chunks = []; size = 0
            for chunk in response.iter_bytes():
                size += len(chunk)
                if size > MAX_RESPONSE_BYTES:
                    raise ValueError('Oversized free-source response')
                chunks.append(chunk)
        text = b''.join(chunks).decode('utf-8')
        source = dict(url=url, response_text=text, sha256=digest(text), observed_at=self.now().isoformat())
        self._validate(source, url)
        if not_before is not None and utc_timestamp(source['observed_at']) < not_before:
            raise ValueError('Source receipt predates final status')
        path.write_text(canonical(source), encoding='utf-8')
        return source


def _event(scoreboard, gap):
    matches = []
    for event in scoreboard['events']:
        for competition in event['competitions']:
            home, = [t for t in competition['competitors'] if t['homeAway'] == 'home']
            away, = [t for t in competition['competitors'] if t['homeAway'] == 'away']
            norm = lambda t: {'LAR': 'LA', 'WSH': 'WAS'}.get(t, t)
            game_id = f"{gap['season']}_{gap['week']:02}_{norm(away['team']['abbreviation'])}_{norm(home['team']['abbreviation'])}"
            day = utc_timestamp(competition['date']).astimezone(ZoneInfo('America/New_York')).date().isoformat()
            if game_id == gap['game_id'] and day == gap['day']:
                if competition['id'] != event['id'] or not re.fullmatch('[1-9][0-9]*', event['id']):
                    raise ValueError('Invalid scoreboard event identity')
                matches.append(event['id'])
    match, = matches
    return match


def collect(data, cache):
    """Audit first; retain per-player bundles of independently verified games."""
    coverage = audit(data, now=cache.now())
    gaps = coverage['missing_games']
    if len(gaps) > MAX_GAPS or len(data['players']) > 64:
        raise ValueError('Evidence scope exceeds bounded collection plan')
    players = {p['player_id']: p for p in data['players']}
    grouped = defaultdict(list); unresolved = []
    for gap in gaps:
        try:
            receipts = {}
            def read(url, **kwargs):
                source = cache.read(url, **kwargs)
                receipts[url] = source
                return json.loads(source['response_text']), source
            board, _ = read(SITE + 'scoreboard?dates=' + gap['day'].replace('-', '') + '&limit=100')
            event = _event(board, gap)
            summary, source = read(SITE + 'summary?event=' + event)
            final_at = utc_timestamp(source['observed_at'])
            comp, = summary['header']['competitions']
            if comp['status']['type']['completed'] is not True:
                raise ValueError('Unfinished event')
            # Identity is resolved by inspect_bundle; use the same pinned GSIS
            # mapping to find the one explicit athlete-stat reference to fetch.
            import csv, io
            crosswalk = [r for r in csv.DictReader(io.StringIO(data['identity']['response_text'])) if r['gsis_id'] == gap['player_id']]
            binding, = crosswalk
            espn = binding['espn_id']; matched = []
            for team in comp['competitors']:
                tid = team['id']
                if not re.fullmatch('[1-9][0-9]*', tid):
                    raise ValueError('Invalid team identity')
                path = f'{BASE}/events/{event}/competitions/{event}/competitors/{tid}/roster'
                roster, _ = read(f'https://{CORE}{path}?limit=100', not_before=final_at)
                for entry in roster['entries']:
                    if str(entry['playerId']) == espn:
                        matched.append((entry, path))
            entry, path = matched[0] if len(matched) == 1 else (None, None)
            if entry is None or entry.get('didNotPlay') is not False:
                raise ValueError('No explicit playing record')
            stat_path = f'{path}/{espn}/statistics/0'
            stat_url = entry['statistics']['$ref']
            _reference(stat_url, stat_path)
            read(stat_url.replace('http://', 'https://', 1), not_before=final_at)
            snap, = [s for s in data['snaps'] if s['snap']['pfr_player_id'] == players[gap['player_id']]['pfr_player_id']
                     and s['snap']['game_id'] == gap['game_id']]
            participation = dict(row={k: snap['snap'][k] for k in SNAP_FIELDS},
                **{k: snap['snap'][k] for k in ('source_provider','source_sha256','source_record_sha256','source_observed_at')},
                **{k: snap[k] for k in ('game_date','home_team','away_team')})
            item = dict(identity=data['identity'], sources=list(receipts.values()), participation=[participation],
                players=[dict(player_id=gap['player_id'], espn_event_id=event, date=gap['day'])])
            evidence, = inspect_bundle(item, now=cache.now())
            if (evidence['status'] != 'verified_explicit_stats'
                    or (evidence['stat_row']['season'], evidence['stat_row']['week']) != (gap['season'], gap['week'])):
                raise ValueError('Explicit final receiving evidence unavailable')
            grouped[gap['player_id']].append(item)
        except (ValueError, KeyError, TypeError, httpx.HTTPError) as exc:
            unresolved.append(dict(player_id=gap['player_id'], game_id=gap['game_id'], reason=type(exc).__name__))
    bundles = {}
    for player, items in grouped.items():
        sources = {s['url']: s for item in items for s in item['sources']}
        bundle = dict(identity=data['identity'], sources=list(sources.values()),
            players=[p for item in items for p in item['players']], participation=[p for item in items for p in item['participation']])
        raw = canonical(bundle)
        if len(raw.encode('utf-8')) > MAX_BYTES:
            raise ValueError('Per-player source archive exceeds import bound')
        inspect_bundle(bundle, now=cache.now())
        bundles[player] = bundle
    return dict(bundles=bundles, unresolved=unresolved, requested_games=len(gaps), requests=cache.requests)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--input', type=Path, required=True, help='Auditable coverage input including pinned identity')
    parser.add_argument('--cache', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--offline', action='store_true')
    args = parser.parse_args()
    data = json.loads(args.input.read_text(encoding='utf-8'))
    with httpx.Client(trust_env=False) as client:
        cache = ReceiptCache(args.cache, client=None if args.offline else client)
        result = collect(data, cache)
    args.output.mkdir(parents=True, exist_ok=True)
    files = []
    for player, bundle in result.pop('bundles').items():
        path = args.output / (player + '.json')
        raw = canonical(bundle)
        if path.exists() and path.read_text(encoding='utf-8') != raw:
            raise ValueError('Refusing to replace a different retained evidence bundle')
        path.write_text(raw, encoding='utf-8'); files.append(dict(file=path.name, sha256=digest(raw)))
    result['files'] = files
    (args.output / 'collection-report.json').write_text(canonical(result), encoding='utf-8')
    print(canonical(result))


if __name__ == '__main__':
    main()
