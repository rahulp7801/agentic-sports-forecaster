"""Aggregate-only feasibility audit for corrected NFL target history on a frozen pair.

This checks coverage, not probability skill or market edge. No provider calls.
"""
from __future__ import annotations

import argparse
from collections import Counter
import json
from pathlib import Path
import statistics

from sportsbet.quant import kalshi_role_shadow as role
from sportsbet.quant import kalshi_role_shadow_v2 as v3
from sportsbet.quant import kalshi_role_shadow_v4 as v4
from sportsbet.quant.kalshi_pair_capture import MAX_PAIR_BYTES, unpack
from sportsbet.quant.kalshi_market_cohort import MAX_ARCHIVE_BYTES, clock
from sportsbet.quant.kalshi_market_settlement import verify_cohort

SUPPORTED = frozenset({'rec_yds','receptions'})


def audit(root: Path) -> dict:
    pair_path=root/'pair.json';market_path=root/'market-archive.json'
    manifest_path=root/'sources'/'source-manifest.json'
    for path,limit in ((pair_path,MAX_PAIR_BYTES),(market_path,MAX_ARCHIVE_BYTES),
                       (manifest_path,2_000_000)):
        if path.is_symlink() or not path.is_file() or not 0<path.stat().st_size<=limit:
            raise ValueError('Missing or oversized private pair input')
    pair=json.loads(pair_path.read_text(encoding='utf-8'))
    market=json.loads(market_path.read_text(encoding='utf-8'))
    manifest=json.loads(manifest_path.read_text(encoding='utf-8'))
    cohort,shadow=unpack(pair)
    verify_cohort(market,cohort)
    if manifest!=shadow.get('source_manifest'):
        raise ValueError('Source manifest mismatch')
    source_dir=root/'sources';when=clock(cohort['captured_at'])
    builder={v3.VERSION:v3.build_report,v4.VERSION:v4.build_report}.get(shadow['protocol'])
    if builder is None or builder(market,cohort,source_dir,manifest,now=clock(shadow['generated_at']))!=shadow:
        raise ValueError('Frozen prequote model replay changed')
    stats,snaps=v3.load_sources(source_dir,when,manifest)
    by_player,by_pfr,_=role._index(stats,snaps)
    crosswalk=role.identity_index(source_dir/'nfl_role_sources.json.gz',when)
    offers={item['ticker']:item for item in cohort['selections']}
    targets=market['evidence']['sources']['kalshi']['prop_inventory']['targets']
    counts=Counter();unavailable=Counter();seen=set()
    counts['quoted_receiving_contracts']=sum(r['prop_type'] in SUPPORTED for r in cohort['selections'])
    for forecast in shadow['forecasts']:
        offer=offers[forecast['ticker']];prop=offer['prop_type']
        if prop not in SUPPORTED:
            continue
        counts['role_forecast_contracts']+=1
        player=forecast['gsis_player_id'];key=(player,prop)
        if key in seen:
            continue
        seen.add(key);counts['unique_forecast_player_props']+=1
        name=role._name(targets[offer['player_target_id']]['player_name'])
        identities=crosswalk.get(name,set())
        if len(identities)!=1 or next(iter(identities))[0]!=player:
            unavailable['identity_mismatch']+=1
            continue
        gsis,pfr=next(iter(identities))
        try:
            history=role._player_history(gsis,pfr,role.STAT[prop],by_player,by_pfr)
        except (ValueError,KeyError,TypeError):
            unavailable['invalid_played_history']+=1
            continue
        sample=history[-40:]
        if len(sample)<20:
            unavailable['fewer_than_20_played_games']+=1
            continue
        raw=[by_player[gsis].get((r['season'],r['week'])) for r in sample]
        if any(row is None for row in raw):
            unavailable['positive_snap_without_stat_row']+=1
        elif any(row.get(role.STAT[prop]) is None for row in raw):
            unavailable['missing_recorded_stat']+=1
        elif any(row.get('targets') is None for row in raw):
            unavailable['missing_recorded_targets']+=1
        elif statistics.fmean(float(row['targets']) for row in raw[-5:])<2:
            unavailable['low_recent_targets']+=1
        else:
            counts['complete_target_history']+=1
    if counts['unique_forecast_player_props'] != counts['complete_target_history']+sum(unavailable.values()):
        raise ValueError('Coverage denominator mismatch')
    return dict(scope='Frozen Kalshi-quoted NFL receiving players only; source feasibility, not sportsbook prediction or edge',
                captured_at=cohort['captured_at'],model_version=shadow['protocol'],
                source_manifest_sha256=shadow['source_manifest_sha256'],
                pair_replayed=True,source_assets_prequote=True,
                counts=dict(sorted(counts.items())),unavailable=dict(sorted(unavailable.items())))


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root',type=Path,required=True)
    parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args()
    result=audit(args.root)
    args.output.parent.mkdir(parents=True,exist_ok=True)
    with args.output.open('x',encoding='utf-8') as stream:
        stream.write(json.dumps(result,sort_keys=True,indent=2,allow_nan=False)+'\n')
    print(json.dumps(result,sort_keys=True))


if __name__=='__main__':
    main()
