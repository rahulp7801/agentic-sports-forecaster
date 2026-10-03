"""Local-only recovery cannot widen scope, rewrite proof or claim remote storage."""
import hashlib
import json
from pathlib import Path
from types import SimpleNamespace
import zipfile

import pytest

from sportsbet.quant import kalshi_paper_local_recovery as recovery
from sportsbet.quant.kalshi_market_cohort import digest


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def fixture(tmp_path,monkeypatch,*,observed=False):
    monkeypatch.chdir(tmp_path)
    root=tmp_path/'.local'/'next-nfl-stat-only-20261008T1700'
    (root/'sources').mkdir(parents=True)
    (root/'context').mkdir()
    for name in recovery.ROOT_FILES:
        raw=b'pinned schedule' if name=='schedule.parquet' else json.dumps({'artifact':name}).encode()
        (root/name).write_bytes(raw)
    sources={}
    for name in recovery.SOURCE_FILES-{'source-manifest.json'}:
        raw=('source:'+name).encode();(root/'sources'/name).write_bytes(raw)
        sources[name]=dict(filename=name,size=len(raw),sha256=sha(raw))
    (root/'sources'/'source-manifest.json').write_text(json.dumps({'assets':sources}))
    context=dict(status='observed' if observed else 'unavailable',assets={},release_metadata_sha256={})
    if observed:
        for tag,name,*_ in recovery.SOURCES:
            raw=('context:'+name).encode();(root/'context'/name).write_bytes(raw)
            meta=json.dumps({'release':tag}).encode();(root/'context'/f'{tag}-release.json').write_bytes(meta)
            context['assets'][tag]=dict(filename=name,size=len(raw),sha256=sha(raw))
            context['release_metadata_sha256'][tag]=sha(meta)
    context_raw=json.dumps(context).encode();(root/'context'/'receipt.json').write_bytes(context_raw)
    hashes={}
    for name in ('pair','market','forecast','quotes','decisions','control','schedule','source_manifest'):
        path=root/'sources'/'source-manifest.json' if name=='source_manifest' else (
            root/'schedule.parquet' if name=='schedule' else root/f'{name}.json')
        hashes[name]=sha(path.read_bytes())
    commitment=dict(input_sha256=hashes,context_receipt_sha256=sha(context_raw))
    proof=dict(commitment_sha256=digest(commitment),commit_oid='a'*40,
        preservation_ref='refs/heads/research/next-nfl-stat-only-20261008T1700-anchor')
    (root/'commitment.json').write_text(json.dumps(commitment))
    (root/'remote-anchor.json').write_text(json.dumps(proof))
    values={name:json.loads((root/f'{name}.json').read_bytes())
        for name in ('pair','market','forecast','quotes','decisions','control','role-weighting','teammate-study')}
    scans=[]
    monkeypatch.setattr(recovery,'_scan',lambda staging:scans.append(staging))
    return root,values,commitment,proof,scans


@pytest.mark.parametrize('observed',[False,True])
def test_all_original_bytes_read_back_without_changing_chronology_or_remote_claim(tmp_path,monkeypatch,observed):
    root,values,commitment,proof,scans=fixture(tmp_path,monkeypatch,observed=observed)
    original=recovery.inventory(root)
    receipt=recovery.prepare(root,values,commitment,proof)
    assert receipt['status']=='local_verified' and receipt['remote_backed_up'] is False
    assert receipt['every_file_readback_verified']
    path=Path(receipt['archive']);manifest=recovery.verify_archive(path,receipt['archive_sha256'])
    assert manifest['original_commit_oid']==proof['commit_oid']
    assert manifest['original_commitment_sha256']==digest(commitment)
    assert len(scans)==1
    with zipfile.ZipFile(path) as bundle:
        for name,raw in original.items():assert bundle.read(name)==raw
        assert set(bundle.namelist())==set(original)|{'RECOVERY-MANIFEST.json'}
    assert recovery.inventory(root)==original


def test_unexpected_credentials_or_log_files_are_never_archived(tmp_path,monkeypatch):
    root,values,commitment,proof,_=fixture(tmp_path,monkeypatch)
    (root/'.env').write_text('sensitive fake local configuration')
    with pytest.raises(ValueError,match='inventory changed'):
        recovery.prepare(root,values,commitment,proof)
    assert not list((tmp_path/'.local').glob('paper-local-recovery-*'))


@pytest.mark.parametrize('changed',['forecast.json','sources/stats_player_week_2026.parquet','context/injuries_2026.parquet','context/injuries-release.json','role-weighting.json'])
def test_changes_after_model_or_marker_replay_reject_package(tmp_path,monkeypatch,changed):
    root,values,commitment,proof,_=fixture(tmp_path,monkeypatch,observed=True)
    (root/changed).write_bytes(b'{"changed":true}')
    with pytest.raises(ValueError,match='changed|differ'):
        recovery.prepare(root,values,commitment,proof)
    assert not list((tmp_path/'.local').glob('paper-local-recovery-*'))


def test_other_commit_proof_cannot_be_used(tmp_path,monkeypatch):
    root,values,commitment,proof,_=fixture(tmp_path,monkeypatch)
    proof={**proof,'commit_oid':'b'*40}
    with pytest.raises(ValueError,match='verified pregame commitment'):
        recovery.prepare(root,values,commitment,proof)


def test_local_scanner_failure_retains_anchor_and_redacts_error(tmp_path,monkeypatch):
    root,values,commitment,proof,_=fixture(tmp_path,monkeypatch)
    retained=(root/'remote-anchor.json').read_bytes()
    def fail(*args):raise recovery.LocalRecoveryUnavailable('DO NOT LOG THIS RAW FINDING')
    monkeypatch.setattr(recovery,'_scan',fail)
    result=recovery.best_effort(root,values,commitment,proof)
    assert result['status']=='local_recovery_unavailable' and not result['remote_backed_up']
    assert 'DO NOT LOG' not in json.dumps(result)
    assert (root/'remote-anchor.json').read_bytes()==retained
    assert not list((tmp_path/'.local').rglob('*-recovery.zip'))


@pytest.mark.parametrize('bound',['MAX_FILE','MAX_TOTAL'])
def test_local_input_size_bounds_precede_archive_or_scanner(tmp_path,monkeypatch,bound):
    root,values,commitment,proof,scans=fixture(tmp_path,monkeypatch)
    monkeypatch.setattr(recovery,bound,3)
    with pytest.raises(ValueError,match='unbounded|bounds'):
        recovery.prepare(root,values,commitment,proof)
    assert not scans


def test_archive_corruption_is_detected_on_readback(tmp_path,monkeypatch):
    root,values,commitment,proof,_=fixture(tmp_path,monkeypatch)
    receipt=recovery.prepare(root,values,commitment,proof)
    path=Path(receipt['archive']);path.write_bytes(path.read_bytes()+b'changed')
    with pytest.raises(ValueError,match='archive bytes changed'):
        recovery.verify_archive(path,receipt['archive_sha256'])


def test_archive_paths_cannot_escape_capture_even_with_matching_outer_hash(tmp_path):
    path=tmp_path/'untrusted.zip'
    name='.local/next-nfl-stat-only-20261008T1700/../outside'
    raw=b'payload'
    manifest=dict(protocol=recovery.VERSION,capture_directory='next-nfl-stat-only-20261008T1700',
        files=[dict(path=name,bytes=len(raw),sha256=sha(raw))])
    with zipfile.ZipFile(path,'w') as bundle:
        bundle.writestr('RECOVERY-MANIFEST.json',json.dumps(manifest));bundle.writestr(name,raw)
    with pytest.raises(ValueError,match='archive path invalid'):
        recovery.verify_archive(path,sha(path.read_bytes()))


def test_scanner_is_pinned_and_never_returns_findings(tmp_path,monkeypatch):
    scanner=tmp_path/'gitleaks.exe';scanner.write_bytes(b'test scanner')
    monkeypatch.setattr(recovery.shutil,'which',lambda name:str(scanner))
    with pytest.raises(recovery.LocalRecoveryUnavailable,match='Pinned local'):
        recovery._scan(tmp_path)
    monkeypatch.setattr(recovery,'SCANNER_SHA256',sha(scanner.read_bytes()))
    calls=[]
    monkeypatch.setattr(recovery.subprocess,'run',lambda args,**kwargs:calls.append((args,kwargs)) or SimpleNamespace(returncode=1,stdout=b'SECRET',stderr=b'SECRET'))
    with pytest.raises(recovery.LocalRecoveryUnavailable,match='rejected') as error:
        recovery._scan(tmp_path)
    assert 'SECRET' not in str(error.value)
    assert '--redact=100' in calls[0][0] and 'shell' not in calls[0][1]


def test_existing_local_package_is_never_overwritten(tmp_path,monkeypatch):
    root,values,commitment,proof,_=fixture(tmp_path,monkeypatch)
    receipt=recovery.prepare(root,values,commitment,proof)
    path=Path(receipt['archive']);original=path.read_bytes()
    result=recovery.best_effort(root,values,commitment,proof)
    assert result['status']=='local_recovery_unavailable'
    assert path.read_bytes()==original


def test_backup_status_write_failure_does_not_erase_original_pregame_anchor(tmp_path,monkeypatch):
    root,values,commitment,proof,_=fixture(tmp_path,monkeypatch)
    retained=(root/'remote-anchor.json').read_bytes()
    monkeypatch.setattr(recovery,'prepare',lambda *args:(_ for _ in ()).throw(OSError('full local disk')))
    original_open=Path.open
    def full(path,*args,**kwargs):
        if path.name.endswith('-local-recovery-status.json'):raise OSError('still full')
        return original_open(path,*args,**kwargs)
    monkeypatch.setattr(Path,'open',full)
    result=recovery.best_effort(root,values,commitment,proof)
    assert result['status']=='local_recovery_unavailable'
    assert (root/'remote-anchor.json').read_bytes()==retained
