"""Short-lived, single-use confirmation tokens for destructive integration actions."""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import secrets
import time
from dataclasses import dataclass

TOKEN_TTL_SECONDS = 120
_consumed_nonces: set[str] = set()


class ConfirmationError(ValueError):
    pass


@dataclass(frozen=True)
class Confirmation:
    operation: str
    target: str
    expected_rows: int


def issue_confirmation(
    secret: str,
    *,
    operation: str,
    target: str,
    expected_rows: int,
    now: int | None = None,
) -> str:
    payload = {
        "operation": operation,
        "target": target,
        "expected_rows": expected_rows,
        "exp": (now or int(time.time())) + TOKEN_TTL_SECONDS,
        "nonce": secrets.token_urlsafe(18),
    }
    body = json.dumps(payload, separators=(",", ":"), sort_keys=True).encode()
    signature = hmac.new(secret.encode(), body, hashlib.sha256).digest()
    return base64.urlsafe_b64encode(body + signature).decode().rstrip("=")


def consume_confirmation(
    secret: str,
    token: str,
    *,
    operation: str,
    target: str,
    now: int | None = None,
) -> Confirmation:
    try:
        raw = base64.urlsafe_b64decode(token + "=" * (-len(token) % 4))
        body, signature = raw[:-32], raw[-32:]
        expected = hmac.new(secret.encode(), body, hashlib.sha256).digest()
        if not hmac.compare_digest(signature, expected):
            raise ConfirmationError("Invalid confirmation signature")
        payload = json.loads(body)
    except (ValueError, json.JSONDecodeError, KeyError) as exc:
        if isinstance(exc, ConfirmationError):
            raise
        raise ConfirmationError("Malformed confirmation token") from exc

    current = now or int(time.time())
    if payload.get("exp", 0) < current:
        raise ConfirmationError("Confirmation token has expired")
    if payload.get("operation") != operation or payload.get("target") != target:
        raise ConfirmationError("Confirmation token does not match this operation and target")
    nonce = payload.get("nonce")
    if not isinstance(nonce, str) or nonce in _consumed_nonces:
        raise ConfirmationError("Confirmation token has already been used")
    _consumed_nonces.add(nonce)
    return Confirmation(operation, target, int(payload.get("expected_rows", 0)))
