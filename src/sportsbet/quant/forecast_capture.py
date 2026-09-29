"""Restore missing public capture metadata from exact retained forecast records."""
from __future__ import annotations

from copy import deepcopy
from datetime import datetime,timezone
import hashlib
import json

from sportsbet.ledger import utc_timestamp

FIELDS = {'game_id':'game_id','player':'player','sport':'sport','prop_type':'prop_type',
    'line':'line','direction':'direction','sportsbook':'sportsbook','american_odds':'american_odds',
    'model_version':'model_version','next_gen_stats':'next_gen_stats','snapped_at':'quote_time',
    'sample_size':'model_sample_size','mean_stat':'model_mean_stat','true_prob':'model_probability'}


def commitment(value):
    return hashlib.sha256(json.dumps(value,sort_keys=True,separators=(',',':'),allow_nan=False).encode()).hexdigest()


def restore_capture(snapshot, records, *, now=None):
    """Copy only a missing timestamp; all probabilities and snapshot dates stay fixed.

    records maps prediction IDs to payloads read from the immutable ledger.
    A caller applying this plan must recheck the original snapshot commitment
    under a row lock. This function performs no reads or writes itself.
    """
    now=now or datetime.now(timezone.utc)
    result=deepcopy(snapshot);restored=[];unresolved=[]
    for signal in result['signals']:
        if signal.get('next_gen_stats') is None or 'captured_at' in signal:
            continue
        key=signal.get('id');record=records.get(key)
        try:
            if not isinstance(key,str) or not key or not isinstance(record,dict):
                raise ValueError('Missing retained identity')
            if signal.get('sport')!='nfl' or any(k not in signal or target not in record
                    or signal[k]!=record[target] for k,target in FIELDS.items()):
                raise ValueError('Forecast terms differ')
            # Older public snapshots omitted the internal history ID. When
            # present it must agree; the retained prediction ID and all exact
            # public terms/NGS commitment always bind the source record.
            if 'player_id' in signal and signal['player_id']!=record.get('player_id'):
                raise ValueError('Player identity differs')
            capture=utc_timestamp(record['captured_at'])
            if (capture!=utc_timestamp(record['model_generated_at'])
                    or not utc_timestamp(record['quote_time'])<=capture<utc_timestamp(record['game_start_time'])
                    or capture>now or signal['game_start_time']!=record['game_start_time']
                    or utc_timestamp(record['next_gen_stats']['source_observed_at'])>capture):
                raise ValueError('Invalid capture chronology')
            if 'observed_before' in record['next_gen_stats']:
                cutoff=utc_timestamp(record['next_gen_stats']['observed_before'])
                if not utc_timestamp(record['next_gen_stats']['source_observed_at'])<=cutoff<=capture:
                    raise ValueError('Invalid source cutoff')
            record_digest=commitment(record)
            signal['captured_at']=record['captured_at']
            restored.append(dict(prediction_id=key,record_sha256=record_digest))
        except (KeyError,TypeError,ValueError,ArithmeticError):
            unresolved.append(key)
    return dict(before_sha256=commitment(snapshot),after_sha256=commitment(result),
        payload=result,restored=restored,unresolved=unresolved)
