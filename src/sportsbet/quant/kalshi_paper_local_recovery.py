"""Prepare replayable evidence locally after an already verified pregame push.

This module has no upload, release, provider, billing or credential operation.
Remote recovery is separately pending explicit recurring-upload authorization.
"""
from __future__ import annotations

from datetime import datetime, timezone
import hashlib
from io import BytesIO
import json
from pathlib import Path
import re
import shutil
import subprocess
import zipfile

from sportsbet.quant.kalshi_market_cohort import digest
from sportsbet.quant.kalshi_stat_only_context_refresh import SOURCES

VERSION = 'sportsbet-local-pregame-recovery-v1'
ROOT = re.compile(r'next-nfl-stat-only-([0-9]{8}T[0-9]{4})\Z')
MAX_FILE = 30_000_000
MAX_TOTAL = 100_000_000
MAX_ARCHIVE = 50_000_000
SCANNER_SHA256 = '17157e2ee8b76fc8b1d8bee607a250e34b8a8023c8bc81822d4b5ee4d78fcb7c'
ROOT_FILES = frozenset({'attempt.json','market.json','pair.json','forecast.json',
    'quotes.json','decisions.json','control.json','schedule.parquet','source-week.json',
    'source-receiving.json','recent-gap.json','role-weighting.json','commitment.json',
    'teammate-study.json','remote-anchor.json'})
SOURCE_FILES = frozenset({'source-manifest.json'} | {
    f'{prefix}_{year}.parquet' for prefix in ('stats_player_week','snap_counts')
    for year in (2024,2025,2026)})
CONTEXT_FILES = frozenset({'receipt.json'} | {filename for _,filename,*_ in SOURCES}
    | {f'{tag}-release.json' for tag,*_ in SOURCES})


class LocalRecoveryUnavailable(Exception):
    """A local dependency failure; no raw scanner error or payload is exposed."""


def _linked(path: Path) -> bool:
    return path.is_symlink() or path.is_junction()


def inventory(root: Path) -> dict[str,bytes]:
    if (ROOT.fullmatch(root.name) is None or _linked(root) or _linked(root.parent)
            or root.resolve().parent != (Path.cwd()/'.local').resolve()):
        raise ValueError('Local recovery requires the original private capture directory')
    context_path = root/'context'/'receipt.json'
    if (_linked(root/'context') or _linked(root/'sources') or _linked(context_path)
            or not context_path.is_file() or not 0 < context_path.stat().st_size <= 100_000):
        raise ValueError('Local recovery context receipt missing or unbounded')
    with context_path.open('rb') as stream:context_raw=stream.read(100_001)
    if not 0 < len(context_raw) <= 100_000:
        raise ValueError('Local recovery context receipt bytes unbounded')
    context = json.loads(context_raw)
    if context.get('status') not in {'observed','unavailable'}:
        raise ValueError('Local recovery context status invalid')
    context_files = CONTEXT_FILES if context['status']=='observed' else frozenset({'receipt.json'})
    groups = ((root,ROOT_FILES|{'sources','context'}),
              (root/'sources',SOURCE_FILES),(root/'context',context_files))
    files = {}
    total = 0
    for directory,allowed in groups:
        if _linked(directory) or not directory.is_dir():
            raise ValueError('Local recovery directory missing or linked')
        children = list(directory.iterdir())
        if {path.name for path in children} != allowed:
            raise ValueError('Local recovery evidence inventory changed')
        for path in children:
            if _linked(path) or not path.resolve().is_relative_to(root.resolve()):
                raise ValueError('Local recovery path escapes or is linked')
            if path.is_dir():
                if directory != root or path.name not in {'sources','context'}:
                    raise ValueError('Unexpected local recovery directory')
                continue
            if not path.is_file() or not 0 < path.stat().st_size <= MAX_FILE:
                raise ValueError('Local recovery file empty or unbounded')
            with path.open('rb') as stream:
                raw=stream.read(MAX_FILE+1)
            total+=len(raw)
            if not 0 < len(raw) <= MAX_FILE or total > MAX_TOTAL:
                raise ValueError('Local recovery bytes exceed bounds')
            files[f'.local/{root.name}/{path.relative_to(root).as_posix()}']=raw
    return files


def _scan(staging: Path) -> None:
    scanner=shutil.which('gitleaks')
    if scanner is None or hashlib.sha256(Path(scanner).read_bytes()).hexdigest()!=SCANNER_SHA256:
        raise LocalRecoveryUnavailable('Pinned local scanner unavailable')
    try:
        result=subprocess.run([scanner,'dir',str(staging),'--config',str(Path.cwd()/'.gitleaks.toml'),
            '--redact=100','--no-banner'],capture_output=True,timeout=60,check=False)
    except (OSError,subprocess.TimeoutExpired) as exc:
        raise LocalRecoveryUnavailable('Local scanner unavailable') from exc
    if result.returncode:
        raise LocalRecoveryUnavailable('Local scanner rejected recovery package')


def verify_archive(path: Path, expected_sha: str) -> dict:
    if _linked(path) or not path.is_file() or not 0 < path.stat().st_size <= MAX_ARCHIVE:
        raise ValueError('Local recovery archive bytes changed')
    with path.open('rb') as stream:archive_raw=stream.read(MAX_ARCHIVE+1)
    if not 0 < len(archive_raw) <= MAX_ARCHIVE or hashlib.sha256(archive_raw).hexdigest()!=expected_sha:
        raise ValueError('Local recovery archive bytes changed')
    with zipfile.ZipFile(BytesIO(archive_raw)) as bundle:
        entries=bundle.infolist()
        if (len(entries)>40 or len({r.filename for r in entries})!=len(entries)
                or any(r.is_dir() or r.file_size>MAX_FILE for r in entries)
                or sum(r.file_size for r in entries)>MAX_TOTAL+100_000):
            raise ValueError('Local recovery archive entry bounds changed')
        if bundle.getinfo('RECOVERY-MANIFEST.json').file_size>100_000:
            raise ValueError('Local recovery manifest unbounded')
        manifest=json.loads(bundle.read('RECOVERY-MANIFEST.json'))
        if manifest.get('protocol')!=VERSION or ROOT.fullmatch(manifest['capture_directory']) is None:
            raise ValueError('Local recovery manifest identity changed')
        records=manifest['files']
        names={r['path'] for r in records}
        if len(records)!=len(names) or {r.filename for r in entries}!=names|{'RECOVERY-MANIFEST.json'}:
            raise ValueError('Local recovery manifest scope changed')
        prefix=f'.local/{manifest["capture_directory"]}/'
        for record in records:
            name=record['path']
            if (not name.startswith(prefix) or '\\' in name or ':' in name
                    or any(part in {'','..','.'} for part in name.split('/')[1:])):
                raise ValueError('Local recovery archive path invalid')
            raw=bundle.read(name)
            if len(raw)!=record['bytes'] or hashlib.sha256(raw).hexdigest()!=record['sha256']:
                raise ValueError('Local recovery archive read-back failed')
    return manifest


def prepare(root: Path, values: dict, commitment: dict, proof: dict) -> dict:
    """Called only after the original publisher verified all three remote markers."""
    files=inventory(root)
    prefix=f'.local/{root.name}/'
    if (json.loads(files[prefix+'remote-anchor.json'])!=proof
            or proof['commitment_sha256']!=digest(commitment)
            or json.loads(files[prefix+'commitment.json'])!=commitment):
        raise ValueError('Local recovery is not this verified pregame commitment')
    for key,expected in commitment['input_sha256'].items():
        relative='sources/source-manifest.json' if key=='source_manifest' else (
            'schedule.parquet' if key=='schedule' else f'{key}.json')
        if hashlib.sha256(files[prefix+relative]).hexdigest()!=expected:
            raise ValueError('Local recovery bytes differ from pregame commitment')
    for key,value in values.items():
        if key!='schedule' and json.loads(files[prefix+f'{key}.json'])!=value:
            raise ValueError('Local recovery input changed after source replay')
    sources=json.loads(files[prefix+'sources/source-manifest.json'])
    for asset in sources['assets'].values():
        raw=files[prefix+'sources/'+asset['filename']]
        if len(raw)!=asset['size'] or hashlib.sha256(raw).hexdigest()!=asset['sha256']:
            raise ValueError('Local recovery source bytes changed after model replay')
    context_raw=files[prefix+'context/receipt.json']
    if hashlib.sha256(context_raw).hexdigest()!=commitment.get('context_receipt_sha256'):
        raise ValueError('Local recovery context differs from pregame commitment')
    context=json.loads(context_raw)
    for tag,asset in context['assets'].items():
        raw=files[prefix+'context/'+asset['filename']]
        metadata=files[prefix+f'context/{tag}-release.json']
        if (len(raw)!=asset['size'] or hashlib.sha256(raw).hexdigest()!=asset['sha256']
                or hashlib.sha256(metadata).hexdigest()!=context['release_metadata_sha256'][tag]):
            raise ValueError('Local recovery context bytes changed after source replay')
    match=ROOT.fullmatch(root.name)
    output=Path('.local')/f'paper-local-recovery-{match[1]}'
    output.mkdir(exist_ok=False)
    staging=output/'staging';staging.mkdir()
    records=[]
    for name,raw in sorted(files.items()):
        path=staging/name
        path.parent.mkdir(parents=True,exist_ok=True)
        with path.open('xb') as stream:stream.write(raw)
        records.append(dict(path=name,bytes=len(raw),sha256=hashlib.sha256(raw).hexdigest()))
    manifest=dict(protocol=VERSION,capture_directory=root.name,
        recovery_at=datetime.now(timezone.utc).isoformat(),
        chronology_notice='Recovery time does not replace original source, model, quote or server-push clocks.',
        original_commit_oid=proof['commit_oid'],original_preserved_ref=proof['preservation_ref'],
        original_commitment_sha256=digest(commitment),files=records)
    encoded=json.dumps(manifest,indent=2,sort_keys=True,allow_nan=False).encode()
    (staging/'RECOVERY-MANIFEST.json').write_bytes(encoded)
    _scan(staging)
    path=output/f'{root.name}-recovery.zip'
    with zipfile.ZipFile(path,'x',zipfile.ZIP_DEFLATED) as bundle:
        for record in records:bundle.writestr(record['path'],files[record['path']])
        bundle.writestr('RECOVERY-MANIFEST.json',encoded)
    sha=hashlib.sha256(path.read_bytes()).hexdigest()
    verify_archive(path,sha)
    receipt=dict(protocol=VERSION,status='local_verified',remote_backed_up=False,
        archive=str(path),archive_sha256=sha,archive_bytes=path.stat().st_size,
        file_count=len(records),original_commit_oid=proof['commit_oid'],
        original_commitment_sha256=digest(commitment),every_file_readback_verified=True)
    with (output/'package.json').open('x',encoding='utf-8') as stream:
        json.dump(receipt,stream,indent=2,sort_keys=True,allow_nan=False)
    return receipt


def best_effort(root: Path, values: dict, commitment: dict, proof: dict) -> dict:
    try:
        return prepare(root,values,commitment,proof)
    except (ValueError,LocalRecoveryUnavailable,OSError,KeyError,TypeError,zipfile.BadZipFile) as exc:
        # Local backup failure cannot erase or invalidate the original anchor.
        # Never serialize scanner findings, raw errors or a fake remote success.
        result=dict(protocol=VERSION,status='local_recovery_unavailable',remote_backed_up=False,
                    error_kind=type(exc).__name__,observed_at=datetime.now(timezone.utc).isoformat())
        path=Path('.local')/f'{root.name}-local-recovery-status.json'
        try:
            if not path.exists() and not path.is_symlink():
                with path.open('x',encoding='utf-8') as stream:json.dump(result,stream,sort_keys=True)
        except OSError:
            # A full or unwritable local disk must not turn a completed
            # pregame push into a publisher exception while reporting failure.
            pass
        return result
