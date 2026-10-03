"""Reject the provider credential exposed in the former public repository.

The fingerprint is one-way; never log or embed the original credential. This
check runs at paid-source entrypoints before ledger reservations or HTTP I/O.
"""

from __future__ import annotations

import hashlib
import hmac


# Segments keep the digest from being mistaken for a live key by Gitleaks.
_EXPOSED_KEY_SHA256 = "".join((
    "92b51902a3278f48", "2ac22bf6e6febb57",
    "c2c4868c6d745ad5", "f30eb1fb9a62b6a8",
))


def require_safe_odds_api_key(key: str | None) -> str:
    if not isinstance(key, str) or not key.strip():
        raise ValueError("Odds API key is not configured")
    fingerprint = hashlib.sha256(key.encode("utf-8")).hexdigest()
    if hmac.compare_digest(fingerprint, _EXPOSED_KEY_SHA256):
        raise ValueError("Historically exposed Odds API credential must be revoked and rotated")
    return key
