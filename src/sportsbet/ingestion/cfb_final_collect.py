"""Archive bounded free ESPN CFB final evidence for guarded settlement preview."""
from __future__ import annotations

import argparse
from collections import Counter
from datetime import date, datetime, timezone
import hashlib
import json
from pathlib import Path
import re

import httpx

from sportsbet.ingestion.archive import write_archive
from sportsbet.ingestion.cfb_final_evidence import GAMELOG, SUMMARY, inspect_bundle

MAX_RESPONSE_BYTES = 4_000_000
MAX_BUNDLE_BYTES = 20_000_000
MAX_ARCHIVE_BYTES = 25_000_000
IDENTITY = re.compile(r'[1-9][0-9]{0,14}\Z')


def collect_bundle(client: httpx.Client, event: str, game_date: date,
                   players: list[str]) -> tuple[dict, list[dict]]:
    """Read fixed public URLs; the existing proof parser owns all stat decisions."""
    if (not isinstance(event, str) or not IDENTITY.fullmatch(event)
            or type(game_date) is not date or type(players) is not list
            or not 1 <= len(players) <= 50
            or len(players) != len(set(players))
            or any(not isinstance(player, str) or not IDENTITY.fullmatch(player)
                   for player in players)):
        raise ValueError('Invalid CFB final collection scope')
    season = game_date.year if game_date.month >= 8 else game_date.year - 1
    if not 2004 <= season <= 2100:
        raise ValueError('Invalid CFB season')
    sources = []
    total = 0
    for url in [SUMMARY + event, *(GAMELOG.format(player=player, season=season)
                                     for player in players)]:
        with client.stream('GET', url, follow_redirects=False) as response:
            if response.status_code != 200 or response.is_redirect:
                raise ValueError('CFB final source unavailable')
            try:
                announced = int(response.headers.get('content-length', '0'))
            except ValueError:
                raise ValueError('Invalid CFB final source length') from None
            if announced < 0 or announced > MAX_RESPONSE_BYTES:
                raise ValueError('CFB final source exceeds response bound')
            chunks = []
            size = 0
            for chunk in response.iter_bytes():
                size += len(chunk)
                if size > MAX_RESPONSE_BYTES or total + size > MAX_BUNDLE_BYTES:
                    raise ValueError('CFB final source exceeds response bound')
                chunks.append(chunk)
        raw = b''.join(chunks)
        if not raw:
            raise ValueError('Empty CFB final source')
        total += len(raw)
        content = raw.decode('utf-8')
        sources.append(dict(url=url, response_text=content,
                            sha256=hashlib.sha256(content.encode('utf-8')).hexdigest(),
                            observed_at=datetime.now(timezone.utc).isoformat()))
    bundle = dict(version=1, players=[dict(player_id=player, espn_event_id=event,
                                            date=game_date.isoformat()) for player in players],
                  sources=sources)
    if len(json.dumps(bundle, indent=2).encode('utf-8')) > MAX_ARCHIVE_BYTES:
        raise ValueError('CFB final archive exceeds recovery bound')
    evidence = inspect_bundle(bundle)
    return bundle, evidence


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--event', required=True)
    parser.add_argument('--date', type=date.fromisoformat, required=True)
    parser.add_argument('--player', action='append', required=True)
    parser.add_argument('--output', type=Path)
    args = parser.parse_args()
    try:
        with httpx.Client(timeout=20, follow_redirects=False) as client:
            bundle, evidence = collect_bundle(client, args.event, args.date, args.player)
        archive = write_archive(bundle, args.output, directory=Path('.local/cfb-final'))
        print(json.dumps(dict(archive=str(archive),
                              bundle_sha256=hashlib.sha256(archive.read_bytes()).hexdigest(),
                              players=len(evidence),
                              statuses=dict(Counter(row['status'] for row in evidence)),
                              execution_ready=False)))
    except Exception as exc:
        raise SystemExit(f'CFB final collection unavailable ({type(exc).__name__})') from None


if __name__ == '__main__':
    main()
