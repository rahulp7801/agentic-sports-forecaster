import hashlib
import tarfile

import pytest

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
