"""Restricted storage wrapper for the unchanged prospective receiving audit."""
from datetime import datetime, timezone
import hashlib
import json

import pytest

from sportsbet.quant import nfl_receiving_accuracy_v1 as frozen
from sportsbet.quant import nfl_receiving_checkpoint as checkpoint


def report():
    return {
        "protocol": frozen.PROTOCOL,
        "observed_at": datetime(2026, 10, 1, 13, tzinfo=timezone.utc).isoformat(),
        "source_audit": {"invalid_receipts": 0},
        "promote": False,
        "target_verified": False,
        "status": "collecting_fixed_cohort",
    }


def test_private_report_encoding_binds_frozen_protocol_and_digest():
    observed, payload, digest = checkpoint.encode_report(report())
    assert observed == datetime(2026, 10, 1, 13, tzinfo=timezone.utc)
    assert digest == hashlib.sha256(payload.encode()).hexdigest()
    assert json.loads(payload)["target_verified"] is False


def test_changed_promotion_and_nonfinite_report_fail_closed():
    changed = report()
    changed["promote"] = True
    with pytest.raises(ValueError, match="contract"):
        checkpoint.encode_report(changed)
    changed = report()
    changed["bad_probability"] = float("nan")
    with pytest.raises(ValueError):
        checkpoint.encode_report(changed)


def test_referenced_prediction_ids_include_evidence_and_tolerate_bad_receipt():
    receipts = [
        {"prediction_id": "original", "payload": json.dumps(
            {"evidence": [{"prediction_id": "opposite"}, {"prediction_id": "original"}]})},
        {"prediction_id": "damaged", "payload": "{"},
    ]
    assert checkpoint.referenced_ids(receipts) == ["damaged", "opposite", "original"]


def test_frozen_empty_report_round_trips_on_linux():
    import platform
    if platform.system() != "Linux":
        pytest.skip("Frozen compressed receipts require Linux CPython 3.12")
    frozen_report = frozen.audit([], [], datetime(2026, 10, 1, 13, tzinfo=timezone.utc))
    _, payload, _ = checkpoint.encode_report(frozen_report)
    assert json.loads(payload)["promote"] is False
