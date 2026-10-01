"""Losslessly package scanned public evidence for bounded Actions storage."""
from __future__ import annotations

import argparse
import hashlib
import io
import json
import os
from pathlib import Path
import tarfile

from sportsbet.ingestion.public_artifacts import DIRECTORIES


def _files(root: Path) -> list[Path]:
    if not root.is_dir() or root.is_symlink() or root.is_junction():
        raise ValueError('Staged public evidence directory is invalid')
    files=[]
    for path in root.rglob('*'):
        if path.is_symlink() or path.is_junction():
            raise ValueError('Evidence links are forbidden')
        relative=path.relative_to(root)
        if path.is_dir():
            if len(relative.parts)!=1 or relative.name not in DIRECTORIES:
                raise ValueError('Unexpected evidence directory')
            continue
        if (not path.is_file() or len(relative.parts)!=2
                or relative.parts[0] not in DIRECTORIES or path.suffix!='.json'):
            raise ValueError('Unexpected evidence file')
        files.append(path)
    return sorted(files, key=lambda path:path.relative_to(root).as_posix())


def pack(root: Path, output: Path) -> dict | None:
    """Return a SHA-256 manifest, or None for a genuinely empty stage."""
    files=_files(root)
    if not files:
        return None
    if output.exists() or output.is_symlink() or output.is_junction():
        raise FileExistsError('Evidence archive already exists')
    output.parent.mkdir(parents=True,exist_ok=True)
    if output.parent.resolve()==root.resolve() or root.resolve() in output.parent.resolve().parents:
        raise ValueError('Evidence archive must be outside the staged directory')
    manifest={'format':'sportsbet-public-evidence-xz-v1','files':[]}
    temporary=output.with_name(output.name+'.tmp')
    if temporary.exists():
        raise FileExistsError('Temporary evidence archive already exists')
    try:
        with tarfile.open(temporary,'w:xz',preset=9) as archive:
            for path in files:
                data=path.read_bytes()
                relative=path.relative_to(root).as_posix()
                manifest['files'].append({'path':relative,'size':len(data),
                                          'sha256':hashlib.sha256(data).hexdigest()})
                entry=tarfile.TarInfo(relative)
                entry.size=len(data)
                entry.mode=0o644
                archive.addfile(entry,io.BytesIO(data))
            encoded=(json.dumps(manifest,sort_keys=True,separators=(',',':'))+'\n').encode()
            entry=tarfile.TarInfo('manifest.json')
            entry.size=len(encoded)
            entry.mode=0o644
            archive.addfile(entry,io.BytesIO(encoded))
        verify(temporary)
        os.replace(temporary,output)
    finally:
        temporary.unlink(missing_ok=True)
    return manifest


def verify(archive_path: Path) -> dict:
    """Verify every byte and member before the artifact is published or replayed."""
    with tarfile.open(archive_path,'r:xz') as archive:
        members=archive.getmembers()
        if not members or members[-1].name!='manifest.json' or any(not m.isfile() for m in members):
            raise ValueError('Evidence archive contains an invalid member')
        manifest=json.load(archive.extractfile(members[-1]))
        if manifest.get('format')!='sportsbet-public-evidence-xz-v1':
            raise ValueError('Evidence archive format mismatch')
        expected=manifest.get('files')
        if not isinstance(expected,list) or not expected or len(expected)!=len(members)-1:
            raise ValueError('Evidence archive manifest mismatch')
        if [m.name for m in members[:-1]]!=[item.get('path') for item in expected]:
            raise ValueError('Evidence archive member mismatch')
        for member,item in zip(members[:-1],expected):
            parts=Path(member.name).parts
            if (len(parts)!=2 or parts[0] not in DIRECTORIES or not parts[1].endswith('.json')
                    or item.get('size')!=member.size):
                raise ValueError('Evidence archive path or size mismatch')
            stream=archive.extractfile(member)
            digest=hashlib.sha256()
            for block in iter(lambda:stream.read(1024*1024),b''):
                digest.update(block)
            if digest.hexdigest()!=item.get('sha256'):
                raise ValueError('Evidence archive checksum mismatch')
    return manifest


def main() -> None:
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--input',type=Path,required=True)
    parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args()
    try:
        manifest=pack(args.input,args.output)
    except Exception as exc:
        raise SystemExit(f'Public evidence packing failed ({type(exc).__name__})') from None
    packaged=manifest is not None
    if os.environ.get('GITHUB_OUTPUT'):
        with Path(os.environ['GITHUB_OUTPUT']).open('a',encoding='utf-8') as output:
            output.write(f'packaged={str(packaged).lower()}\n')
    print(f'Packed {len(manifest["files"]) if manifest else 0} verified public evidence files')


if __name__=='__main__':
    main()
