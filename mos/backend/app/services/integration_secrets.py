from __future__ import annotations

import json
from typing import Any

from cryptography.fernet import Fernet, InvalidToken

from app.config import settings


class IntegrationSecretError(RuntimeError):
    pass


def _clean_optional_text(value: str | None) -> str | None:
    if value is None:
        return None
    cleaned = value.strip()
    return cleaned or None


def _fernet() -> Fernet:
    raw_key = _clean_optional_text(settings.INTEGRATION_SECRETS_KEY)
    if not raw_key:
        raise IntegrationSecretError(
            "INTEGRATION_SECRETS_KEY is required to create or read integration credentials."
        )
    try:
        return Fernet(raw_key.encode("utf-8"))
    except Exception as exc:  # noqa: BLE001
        raise IntegrationSecretError("INTEGRATION_SECRETS_KEY is invalid for Fernet encryption.") from exc


def encrypt_secret_json(payload: dict[str, Any]) -> str:
    encoded = json.dumps(payload, separators=(",", ":"), sort_keys=True).encode("utf-8")
    return _fernet().encrypt(encoded).decode("utf-8")


def decrypt_secret_json(token: str | None) -> dict[str, Any]:
    cleaned = _clean_optional_text(token)
    if not cleaned:
        return {}
    try:
        decrypted = _fernet().decrypt(cleaned.encode("utf-8"))
    except InvalidToken as exc:
        raise IntegrationSecretError("Stored integration credentials could not be decrypted.") from exc
    except Exception as exc:  # noqa: BLE001
        raise IntegrationSecretError("Failed to read stored integration credentials.") from exc
    try:
        parsed = json.loads(decrypted.decode("utf-8"))
    except json.JSONDecodeError as exc:
        raise IntegrationSecretError("Stored integration credentials are not valid JSON.") from exc
    if not isinstance(parsed, dict):
        raise IntegrationSecretError("Stored integration credentials must decode to a JSON object.")
    return parsed

