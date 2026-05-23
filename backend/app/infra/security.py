from __future__ import annotations

import base64
import hashlib
import hmac
import json
import secrets
from datetime import UTC, datetime, timedelta
from typing import Any

from app.domain.exceptions import AuthenticationError
from app.infra.config import Settings


def hash_password(password: str, settings: Settings) -> str:
    salt = secrets.token_bytes(16)
    digest = hashlib.pbkdf2_hmac(
        "sha256",
        password.encode("utf-8"),
        salt,
        settings.password_hash_iterations,
    )
    return (
        f"pbkdf2_sha256${settings.password_hash_iterations}$"
        f"{_b64url_encode(salt)}${_b64url_encode(digest)}"
    )


def verify_password(password: str, password_hash: str | None) -> bool:
    if not password_hash:
        return False

    try:
        algorithm, iterations, salt, digest = password_hash.split("$", maxsplit=3)
        if algorithm != "pbkdf2_sha256":
            return False

        expected_digest = _b64url_decode(digest)
        actual_digest = hashlib.pbkdf2_hmac(
            "sha256",
            password.encode("utf-8"),
            _b64url_decode(salt),
            int(iterations),
        )
        return hmac.compare_digest(actual_digest, expected_digest)
    except (ValueError, TypeError):
        return False


def create_access_token(user_id: int, settings: Settings) -> tuple[str, datetime]:
    expires_at = datetime.now(UTC) + timedelta(minutes=settings.access_token_expire_minutes)
    payload = {
        "sub": str(user_id),
        "type": "access",
        "exp": int(expires_at.timestamp()),
        "iat": int(datetime.now(UTC).timestamp()),
    }
    return encode_jwt(payload, settings), expires_at


def encode_jwt(payload: dict[str, Any], settings: Settings) -> str:
    if settings.jwt_algorithm != "HS256":
        raise ValueError("Only HS256 is supported by the built-in JWT encoder")

    header = {"alg": settings.jwt_algorithm, "typ": "JWT"}
    signing_input = (
        f"{_b64url_json(header)}.{_b64url_json(payload)}".encode("ascii")
    )
    signature = hmac.new(
        settings.jwt_secret_key.encode("utf-8"),
        signing_input,
        hashlib.sha256,
    ).digest()
    return f"{signing_input.decode('ascii')}.{_b64url_encode(signature)}"


def decode_jwt(token: str, settings: Settings) -> dict[str, Any]:
    try:
        header_part, payload_part, signature_part = token.split(".", maxsplit=2)
    except ValueError as exc:
        raise AuthenticationError("Invalid access token") from exc

    signing_input = f"{header_part}.{payload_part}".encode("ascii")
    expected_signature = hmac.new(
        settings.jwt_secret_key.encode("utf-8"),
        signing_input,
        hashlib.sha256,
    ).digest()
    actual_signature = _b64url_decode(signature_part)
    if not hmac.compare_digest(actual_signature, expected_signature):
        raise AuthenticationError("Invalid access token")

    try:
        header = json.loads(_b64url_decode(header_part))
        payload = json.loads(_b64url_decode(payload_part))
    except (json.JSONDecodeError, UnicodeDecodeError) as exc:
        raise AuthenticationError("Invalid access token") from exc

    if header.get("alg") != settings.jwt_algorithm or header.get("typ") != "JWT":
        raise AuthenticationError("Invalid access token")

    expires_at = payload.get("exp")
    if not isinstance(expires_at, int) or expires_at < int(datetime.now(UTC).timestamp()):
        raise AuthenticationError("Access token has expired")

    if payload.get("type") != "access":
        raise AuthenticationError("Invalid access token")

    return payload


def _b64url_json(data: dict[str, Any]) -> str:
    return _b64url_encode(
        json.dumps(data, separators=(",", ":"), sort_keys=True).encode("utf-8")
    )


def _b64url_encode(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode("ascii")


def _b64url_decode(data: str) -> bytes:
    padding = "=" * (-len(data) % 4)
    return base64.urlsafe_b64decode(f"{data}{padding}")
