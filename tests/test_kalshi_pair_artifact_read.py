"""Archived private evidence is pinned, bounded, and replayed before restore."""
import hashlib
import json
import stat
import warnings
from pathlib import Path
import zipfile

import pytest

from sportsbet.quant import kalshi_pair_artifact as writer
from sportsbet.quant import kalshi_pair_artifact_read as reader
from tests.test_kalshi_pair_artifact import setup


def packed(tmp_path, monkeypatch):
    pair, sources, markets = setup(tmp_path, monkeypatch)
    output = tmp_path / "private.zip"
    writer.pack(pair, sources, markets, output)
    raw = output.read_bytes()
    return output, hashlib.sha256(raw).hexdigest()


def rewrite(original: Path, target: Path, changes: dict[str, bytes]) -> str:
    with zipfile.ZipFile(original) as source:
        files = {name: source.read(name) for name in source.namelist()}
    files.update(changes)
    with zipfile.ZipFile(target, "w", compression=zipfile.ZIP_DEFLATED) as output:
        for name, content in files.items():
            output.writestr(name, content)
    return hashlib.sha256(target.read_bytes()).hexdigest()


def test_valid_archive_restores_exact_replay_inputs(tmp_path, monkeypatch):
    archive, digest = packed(tmp_path, monkeypatch)
    destination = tmp_path / "restored"
    report = reader.verify_and_extract(archive, digest, destination)
    assert report["files"] == 11
    assert (destination / "pair.json").is_file()
    assert len(list((destination / "sources").glob("*.parquet"))) == 6
    assert (destination / "manifest.json").is_file()
    with pytest.raises(FileExistsError):
        reader.verify_and_extract(archive, digest, destination)


def test_external_preoutcome_commitment_cannot_be_changed(tmp_path, monkeypatch):
    archive, digest = packed(tmp_path, monkeypatch)
    raw = bytearray(archive.read_bytes())
    raw[-1] ^= 1
    archive.write_bytes(raw)
    destination = tmp_path / "restored"
    with pytest.raises(ValueError, match="external SHA256"):
        reader.verify_and_extract(archive, digest, destination)
    assert not destination.exists()


def test_extra_path_and_duplicate_zip_entry_are_rejected(tmp_path, monkeypatch):
    archive, _ = packed(tmp_path, monkeypatch)
    evil = tmp_path / "evil.zip"
    digest = rewrite(archive, evil, {"../outside.txt": b"no"})
    destination = tmp_path / "restored"
    with pytest.raises(ValueError, match="scope"):
        reader.verify_and_extract(evil, digest, destination)
    assert not destination.exists()
    with zipfile.ZipFile(archive) as original:
        files = [(name, original.read(name)) for name in original.namelist()]
    duplicate = tmp_path / "duplicate.zip"
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", UserWarning)
        with zipfile.ZipFile(duplicate, "w", compression=zipfile.ZIP_DEFLATED) as output:
            for name, content in files:
                output.writestr(name, content)
            output.writestr("pair.json", files[0][1])
    digest = hashlib.sha256(duplicate.read_bytes()).hexdigest()
    with pytest.raises(ValueError, match="scope"):
        reader.verify_and_extract(duplicate, digest, destination)
    assert not destination.exists()


def test_recommitted_tampered_pair_still_fails_model_replay(tmp_path, monkeypatch):
    archive, _ = packed(tmp_path, monkeypatch)
    with zipfile.ZipFile(archive) as source:
        files = {name: source.read(name) for name in source.namelist()}
    pair = json.loads(files["pair.json"])
    from sportsbet.quant.kalshi_market_cohort import digest as model_digest
    from sportsbet.quant.kalshi_ask_policy import freeze as freeze_ask
    from sportsbet.quant.kalshi_prior20_ask_policy import freeze as freeze_prior
    pair["shadow"]["forecasts"][0]["model_over_probability"] = .99
    pair["shadow"]["forecasts_sha256"] = model_digest(pair["shadow"]["forecasts"])
    pair["forecasts_sha256"] = pair["shadow"]["forecasts_sha256"]
    pair["ask_policy"] = freeze_ask(pair)
    pair["prior20_ask_policy"] = freeze_prior(pair)
    files["pair.json"] = json.dumps(pair).encode()
    receipt = json.loads(files["manifest.json"])
    receipt["pair.json"] = dict(size=len(files["pair.json"]),
                                sha256=hashlib.sha256(files["pair.json"]).hexdigest())
    files["manifest.json"] = json.dumps(receipt).encode()
    altered = tmp_path / "altered.zip"
    digest = rewrite(archive, altered, files)
    destination = tmp_path / "restored"
    with pytest.raises(ValueError, match="replay changed"):
        reader.verify_and_extract(altered, digest, destination)
    assert not destination.exists()



def test_symlink_zip_member_is_rejected_even_with_external_hash(tmp_path, monkeypatch):
    archive, _ = packed(tmp_path, monkeypatch)
    with zipfile.ZipFile(archive) as original:
        files = [(name, original.read(name)) for name in original.namelist()]
    altered = tmp_path / "symlink.zip"
    with zipfile.ZipFile(altered, "w", compression=zipfile.ZIP_DEFLATED) as output:
        for name, content in files:
            if name == "pair.json":
                info = zipfile.ZipInfo(name)
                info.compress_type = zipfile.ZIP_DEFLATED
                info.create_system = 3
                info.external_attr = (stat.S_IFLNK | 0o777) << 16
                output.writestr(info, content)
            else:
                output.writestr(name, content)
    digest = hashlib.sha256(altered.read_bytes()).hexdigest()
    destination = tmp_path / "restored"
    with pytest.raises(ValueError, match="unsafe"):
        reader.verify_and_extract(altered, digest, destination)
    assert not destination.exists()


def test_forward_v4_artifact_restores_under_its_saved_protocol(tmp_path, monkeypatch):
    from datetime import timedelta
    from sportsbet.quant import kalshi_role_shadow_v4 as v4
    from sportsbet.quant.kalshi_ask_policy import freeze as freeze_ask
    from sportsbet.quant.kalshi_prior20_ask_policy import freeze as freeze_prior
    from tests.test_kalshi_pair_artifact import NOW

    pair_path, source_dir, market_dir = setup(tmp_path, monkeypatch)
    pair = json.loads(pair_path.read_text(encoding="utf-8"))
    market = json.loads((market_dir / "market.json").read_text(encoding="utf-8"))
    source = pair["shadow"]["source_manifest"]
    pair["shadow"] = v4.build_report(market, pair["cohort"], source_dir, source, now=NOW)
    pair["forecasts_sha256"] = pair["shadow"]["forecasts_sha256"]
    pair["ask_policy"] = freeze_ask(pair, decided_at=NOW + timedelta(seconds=3))
    pair["prior20_ask_policy"] = freeze_prior(
        pair, decided_at=NOW + timedelta(seconds=3))
    pair_path.write_text(json.dumps(pair), encoding="utf-8")
    archive = tmp_path / "forward.zip"
    writer.pack(pair_path, source_dir, market_dir, archive)
    digest = hashlib.sha256(archive.read_bytes()).hexdigest()
    report = reader.verify_and_extract(archive, digest, tmp_path / "restored")
    assert report["model_version"] == v4.VERSION
    assert report["forecasts_sha256"] == pair["forecasts_sha256"]
