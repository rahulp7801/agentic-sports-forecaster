import hashlib
from pathlib import Path
import tarfile

import pytest
import yaml

from sportsbet.ingestion.pack_public_artifacts import pack, verify


def test_packed_public_evidence_is_lossless_and_deduplicates_repeated_sources(tmp_path):
    staged=tmp_path/'staged'
    (staged/'availability').mkdir(parents=True)
    common=b'{"source":"verified","body":"'+b'a'*500_000+b'"}'
    originals={}
    for index in range(3):
        relative=f'availability/{index}.json'
        data=common[:-1]+f',\"index\":{index}}}'.encode()
        (staged/relative).write_bytes(data)
        originals[relative]=data
    output=tmp_path/'public-evidence.tar.xz'
    manifest=pack(staged,output)
    assert manifest==verify(output)
    assert output.stat().st_size<sum(len(data) for data in originals.values())//10
    with tarfile.open(output,'r:xz') as archive:
        for relative,data in originals.items():
            assert archive.extractfile(relative).read()==data
            entry=next(item for item in manifest['files'] if item['path']==relative)
            assert entry['sha256']==hashlib.sha256(data).hexdigest()


def test_empty_stage_creates_no_artifact_and_unexpected_paths_fail(tmp_path):
    staged=tmp_path/'staged';staged.mkdir()
    output=tmp_path/'public-evidence.tar.xz'
    assert pack(staged,output) is None
    assert not output.exists()
    (staged/'private.json').write_text('{}')
    with pytest.raises(ValueError,match='Unexpected evidence file'):
        pack(staged,output)
    assert not output.exists()


def test_evidence_is_scanned_before_packing_and_only_archive_is_uploaded():
    for workflow in ('data.yml','public-data.yml'):
        document=yaml.safe_load((Path('.github/workflows')/workflow).read_text(encoding='utf8'))
        steps=document['jobs']['update']['steps']
        names=[step.get('name') for step in steps]
        assert names.index('Scan public evidence')<names.index('Pack verified public evidence losslessly')
        assert names.index('Pack verified public evidence losslessly')<names.index('Retain public market evidence for replay')
        scan=next(step for step in steps if step.get('name')=='Scan public evidence')
        packed=next(step for step in steps if step.get('id')=='evidence_pack')
        upload=next(step for step in steps if step.get('name')=='Retain public market evidence for replay')
        assert 'gitleaks dir "$RUNNER_TEMP/public-evidence"' in scan['run']
        assert "steps.evidence_scan.outcome == 'success'" in packed['if']
        assert "steps.evidence_pack.outputs.packaged == 'true'" in upload['if']
        assert upload['with']['path']=='${{ runner.temp }}/public-evidence.tar.xz'
        assert upload['with']['compression-level']==0
