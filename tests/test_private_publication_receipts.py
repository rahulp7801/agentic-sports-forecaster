import importlib.util
from pathlib import Path
import pytest
spec=importlib.util.spec_from_file_location('receipt_verifier',Path('.github/scripts/verify-published-snapshots.py'))
module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)

def test_exact_publication_receipts_remain_private_and_use_parameterized_snapshot_keys():
    at='2026-10-06T20:00:00+00:00'
    report={'markets':{'nfl':{'captured_at':at}},'schedules':{'nba':{'captured_at':at}}}
    seen=[]
    def read(key):seen.append(key);return {'captured_at':at}
    assert module.verify_captures(report,read)==2
    assert seen==['markets:nfl','schedule:nba']
    with pytest.raises(ValueError,match='does not match'):
        module.verify_captures(report,lambda key:{'captured_at':'2026-10-05T20:00:00+00:00'})
    for bad in ({},{'markets':{'nfl':{'captured_at':'invalid'}}},{'markets':{'nfl':{'captured_at':'2026-10-06T20:00:00'}}}):
        with pytest.raises(ValueError):module.receipt_entries(bad)
