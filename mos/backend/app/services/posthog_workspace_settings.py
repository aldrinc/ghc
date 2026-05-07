from __future__ import annotations

import ast
import re
from typing import Any, Mapping
from urllib.parse import urlsplit

from sqlalchemy.orm import Session

from app.db.models import ClientPosthogSettings
from app.db.repositories.client_posthog_settings import ClientPosthogSettingsRepository

DEFAULT_POSTHOG_DEFAULTS = "2026-01-30"
DEFAULT_POSTHOG_PERSON_PROFILES = "identified_only"
ALLOWED_POSTHOG_PERSON_PROFILES = {"identified_only", "always"}
ALLOWED_POSTHOG_SOURCE_MODES = {"structured", "snippet"}
_POSTHOG_INIT_RE = re.compile(r"posthog\s*\.\s*init\s*\(", re.IGNORECASE)
_IDENTIFIER_RE = re.compile(r"[A-Za-z_$][\w$]*")
_SNIPPET_KEY_ALIASES = {
    "api_host": "api_host",
    "apiHost": "api_host",
    "ui_host": "ui_host",
    "uiHost": "ui_host",
    "defaults": "defaults",
    "person_profiles": "person_profiles",
    "personProfiles": "person_profiles",
}


def clean_optional_text(value: object) -> str | None:
    if value is None:
        return None
    cleaned = str(value).strip()
    return cleaned or None


def _normalize_https_origin(value: object, *, field_name: str) -> str | None:
    cleaned = clean_optional_text(value)
    if not cleaned:
        return None
    parsed = urlsplit(cleaned)
    if parsed.scheme != "https" or not parsed.netloc:
        raise ValueError(f"{field_name} must be an https origin without a path.")
    if parsed.path not in ("", "/") or parsed.query or parsed.fragment:
        raise ValueError(f"{field_name} must be an https origin without a path.")
    return f"{parsed.scheme}://{parsed.netloc}"


def normalize_posthog_settings_payload(
    payload: Mapping[str, Any],
    *,
    enforce_source_contract: bool,
) -> dict[str, Any]:
    enabled = bool(payload.get("enabled"))
    project_api_key = clean_optional_text(payload.get("project_api_key"))
    api_host = _normalize_https_origin(payload.get("api_host"), field_name="apiHost")
    ui_host = _normalize_https_origin(payload.get("ui_host"), field_name="uiHost")
    defaults = clean_optional_text(payload.get("defaults")) or DEFAULT_POSTHOG_DEFAULTS
    person_profiles = (
        clean_optional_text(payload.get("person_profiles")) or DEFAULT_POSTHOG_PERSON_PROFILES
    )
    if person_profiles not in ALLOWED_POSTHOG_PERSON_PROFILES:
        raise ValueError("personProfiles must be 'identified_only' or 'always'.")

    source_mode = clean_optional_text(payload.get("source_mode")) or "structured"
    if source_mode not in ALLOWED_POSTHOG_SOURCE_MODES:
        raise ValueError("sourceMode must be 'structured' or 'snippet'.")

    source_snippet = clean_optional_text(payload.get("source_snippet"))
    if source_mode == "snippet" and enforce_source_contract and not source_snippet:
        raise ValueError("sourceSnippet is required when sourceMode is 'snippet'.")

    if enabled and not project_api_key:
        raise ValueError("projectApiKey is required when Analytics is enabled.")
    if enabled and not api_host:
        raise ValueError("apiHost is required when Analytics is enabled.")

    return {
        "enabled": enabled,
        "project_api_key": project_api_key,
        "api_host": api_host,
        "ui_host": ui_host,
        "defaults": defaults,
        "person_profiles": person_profiles,
        "source_mode": source_mode,
        "source_snippet": source_snippet,
    }


def build_posthog_tracking_payload(payload: Mapping[str, Any]) -> dict[str, str] | None:
    normalized = normalize_posthog_settings_payload(
        payload,
        enforce_source_contract=False,
    )
    if not normalized["enabled"]:
        return None
    resolved = {
        "provider": "posthog",
        "mode": "public_funnel_runtime",
        "posthogProjectApiKey": normalized["project_api_key"],
        "posthogApiHost": normalized["api_host"],
        "posthogDefaults": normalized["defaults"],
        "posthogPersonProfiles": normalized["person_profiles"],
    }
    if normalized["ui_host"]:
        resolved["posthogUiHost"] = normalized["ui_host"]
    return resolved


def serialize_posthog_settings_record(
    record: ClientPosthogSettings | None,
) -> dict[str, Any]:
    if record is None:
        return {
            "has_settings": False,
            "enabled": False,
            "project_api_key": None,
            "api_host": None,
            "ui_host": None,
            "defaults": DEFAULT_POSTHOG_DEFAULTS,
            "person_profiles": DEFAULT_POSTHOG_PERSON_PROFILES,
            "source_mode": "structured",
            "source_snippet": None,
            "resolved_tracking": None,
            "created_at": None,
            "updated_at": None,
        }

    payload = {
        "enabled": bool(record.enabled),
        "project_api_key": record.project_api_key,
        "api_host": record.api_host,
        "ui_host": record.ui_host,
        "defaults": record.defaults,
        "person_profiles": record.person_profiles,
        "source_mode": record.source_mode,
        "source_snippet": record.source_snippet,
    }
    normalized = normalize_posthog_settings_payload(
        payload,
        enforce_source_contract=False,
    )
    return {
        "has_settings": True,
        **normalized,
        "resolved_tracking": build_posthog_tracking_payload(normalized),
        "created_at": record.created_at,
        "updated_at": record.updated_at,
    }


def resolve_client_posthog_tracking(
    *,
    session: Session,
    org_id: str,
    client_id: str,
) -> dict[str, str] | None:
    record = ClientPosthogSettingsRepository(session).get(org_id=org_id, client_id=client_id)
    if record is None:
        return None
    return build_posthog_tracking_payload(
        {
            "enabled": record.enabled,
            "project_api_key": record.project_api_key,
            "api_host": record.api_host,
            "ui_host": record.ui_host,
            "defaults": record.defaults,
            "person_profiles": record.person_profiles,
            "source_mode": record.source_mode,
            "source_snippet": record.source_snippet,
        }
    )


def _strip_js_comments(source: str) -> str:
    result: list[str] = []
    index = 0
    length = len(source)
    in_single = False
    in_double = False
    in_template = False
    while index < length:
        char = source[index]
        next_char = source[index + 1] if index + 1 < length else ""
        previous = source[index - 1] if index > 0 else ""
        if in_single:
            result.append(char)
            if char == "'" and previous != "\\":
                in_single = False
            index += 1
            continue
        if in_double:
            result.append(char)
            if char == '"' and previous != "\\":
                in_double = False
            index += 1
            continue
        if in_template:
            result.append(char)
            if char == "`" and previous != "\\":
                in_template = False
            index += 1
            continue
        if char == "'":
            in_single = True
            result.append(char)
            index += 1
            continue
        if char == '"':
            in_double = True
            result.append(char)
            index += 1
            continue
        if char == "`":
            in_template = True
            result.append(char)
            index += 1
            continue
        if char == "/" and next_char == "/":
            index += 2
            while index < length and source[index] not in "\r\n":
                index += 1
            continue
        if char == "/" and next_char == "*":
            index += 2
            while index + 1 < length and not (source[index] == "*" and source[index + 1] == "/"):
                if source[index] in "\r\n":
                    result.append(source[index])
                index += 1
            index += 2
            continue
        result.append(char)
        index += 1
    return "".join(result)


def _extract_wrapped(text: str, start_index: int, *, opener: str, closer: str) -> tuple[str, int]:
    if start_index >= len(text) or text[start_index] != opener:
        raise ValueError(f"Expected '{opener}' in snippet.")
    depth = 0
    in_single = False
    in_double = False
    in_template = False
    for index in range(start_index, len(text)):
        char = text[index]
        previous = text[index - 1] if index > start_index else ""
        if in_single:
            if char == "'" and previous != "\\":
                in_single = False
            continue
        if in_double:
            if char == '"' and previous != "\\":
                in_double = False
            continue
        if in_template:
            if char == "`" and previous != "\\":
                in_template = False
            continue
        if char == "'":
            in_single = True
            continue
        if char == '"':
            in_double = True
            continue
        if char == "`":
            in_template = True
            continue
        if char == opener:
            depth += 1
            continue
        if char == closer:
            depth -= 1
            if depth == 0:
                return text[start_index + 1 : index], index
    raise ValueError(f"Snippet is missing a closing '{closer}'.")


def _split_top_level_arguments(source: str) -> list[str]:
    parts: list[str] = []
    start = 0
    depth_paren = 0
    depth_brace = 0
    depth_bracket = 0
    in_single = False
    in_double = False
    in_template = False
    index = 0
    while index < len(source):
        char = source[index]
        previous = source[index - 1] if index > 0 else ""
        if in_single:
            if char == "'" and previous != "\\":
                in_single = False
            index += 1
            continue
        if in_double:
            if char == '"' and previous != "\\":
                in_double = False
            index += 1
            continue
        if in_template:
            if char == "`" and previous != "\\":
                in_template = False
            index += 1
            continue
        if char == "'":
            in_single = True
        elif char == '"':
            in_double = True
        elif char == "`":
            in_template = True
        elif char == "(":
            depth_paren += 1
        elif char == ")":
            depth_paren -= 1
        elif char == "{":
            depth_brace += 1
        elif char == "}":
            depth_brace -= 1
        elif char == "[":
            depth_bracket += 1
        elif char == "]":
            depth_bracket -= 1
        elif char == "," and depth_paren == 0 and depth_brace == 0 and depth_bracket == 0:
            part = source[start:index].strip()
            if part:
                parts.append(part)
            start = index + 1
        index += 1

    tail = source[start:].strip()
    if tail:
        parts.append(tail)
    return parts


def _parse_js_string_literal(token: str, *, field_name: str) -> str | None:
    stripped = token.strip()
    if stripped == "null":
        return None
    if len(stripped) < 2 or stripped[0] not in {"'", '"'} or stripped[-1] != stripped[0]:
        raise ValueError(f"{field_name} must be a string literal in the snippet.")
    try:
        value = ast.literal_eval(stripped)
    except (SyntaxError, ValueError) as exc:
        raise ValueError(f"{field_name} must be a valid string literal in the snippet.") from exc
    cleaned = clean_optional_text(value)
    if cleaned is None:
        raise ValueError(f"{field_name} must not be empty in the snippet.")
    return cleaned


def _parse_next_object_key(source: str, index: int) -> tuple[str, int]:
    if source[index] in {"'", '"'}:
        quote = source[index]
        end = index + 1
        while end < len(source):
            if source[end] == quote and source[end - 1] != "\\":
                break
            end += 1
        if end >= len(source):
            raise ValueError("Snippet contains an unterminated object key.")
        key = _parse_js_string_literal(source[index : end + 1], field_name="config key")
        return key or "", end + 1

    match = _IDENTIFIER_RE.match(source, index)
    if not match:
        raise ValueError("Snippet config contains an unsupported key.")
    return match.group(0), match.end()


def _consume_js_expression(source: str, index: int) -> tuple[str, int]:
    start = index
    depth_paren = 0
    depth_brace = 0
    depth_bracket = 0
    in_single = False
    in_double = False
    in_template = False
    while index < len(source):
        char = source[index]
        previous = source[index - 1] if index > start else ""
        if in_single:
            if char == "'" and previous != "\\":
                in_single = False
            index += 1
            continue
        if in_double:
            if char == '"' and previous != "\\":
                in_double = False
            index += 1
            continue
        if in_template:
            if char == "`" and previous != "\\":
                in_template = False
            index += 1
            continue
        if char == "'":
            in_single = True
            index += 1
            continue
        if char == '"':
            in_double = True
            index += 1
            continue
        if char == "`":
            in_template = True
            index += 1
            continue
        if char == "(":
            depth_paren += 1
            index += 1
            continue
        if char == ")":
            if depth_paren == 0:
                break
            depth_paren -= 1
            index += 1
            continue
        if char == "{":
            depth_brace += 1
            index += 1
            continue
        if char == "}":
            if depth_brace == 0 and depth_paren == 0 and depth_bracket == 0:
                break
            depth_brace -= 1
            index += 1
            continue
        if char == "[":
            depth_bracket += 1
            index += 1
            continue
        if char == "]":
            depth_bracket -= 1
            index += 1
            continue
        if char == "," and depth_paren == 0 and depth_brace == 0 and depth_bracket == 0:
            break
        index += 1
    return source[start:index].strip(), index


def _parse_posthog_config_object(object_source: str) -> dict[str, str | None]:
    trimmed = object_source.strip()
    if not trimmed.startswith("{") or not trimmed.endswith("}"):
        raise ValueError("Snippet must pass a config object as the second posthog.init argument.")

    inner = trimmed[1:-1]
    parsed: dict[str, str | None] = {}
    index = 0
    while index < len(inner):
        while index < len(inner) and inner[index] in {" ", "\t", "\r", "\n", ","}:
            index += 1
        if index >= len(inner):
            break

        key, index = _parse_next_object_key(inner, index)
        while index < len(inner) and inner[index].isspace():
            index += 1
        if index >= len(inner) or inner[index] != ":":
            raise ValueError("Snippet config contains an invalid key/value pair.")
        index += 1
        while index < len(inner) and inner[index].isspace():
            index += 1
        value_source, index = _consume_js_expression(inner, index)
        normalized_key = _SNIPPET_KEY_ALIASES.get(key)
        if normalized_key:
            parsed[normalized_key] = _parse_js_string_literal(
                value_source,
                field_name=normalized_key,
            )
        if index < len(inner) and inner[index] == ",":
            index += 1
    return parsed


def parse_posthog_snippet(snippet: str) -> dict[str, Any]:
    cleaned_snippet = clean_optional_text(snippet)
    if not cleaned_snippet:
        raise ValueError("Snippet is required.")

    source = _strip_js_comments(cleaned_snippet)
    match = _POSTHOG_INIT_RE.search(source)
    if not match:
        raise ValueError("Snippet must include a posthog.init(...) call.")

    open_paren_index = source.find("(", match.start())
    if open_paren_index < 0:
        raise ValueError("Snippet must include a posthog.init(...) call.")

    args_source, _ = _extract_wrapped(source, open_paren_index, opener="(", closer=")")
    args = _split_top_level_arguments(args_source)
    if len(args) < 2:
        raise ValueError("Snippet must pass an API key and config object to posthog.init(...).")

    project_api_key = _parse_js_string_literal(args[0], field_name="projectApiKey")
    config_values = _parse_posthog_config_object(args[1])

    return normalize_posthog_settings_payload(
        {
            "enabled": True,
            "project_api_key": project_api_key,
            "api_host": config_values.get("api_host"),
            "ui_host": config_values.get("ui_host"),
            "defaults": config_values.get("defaults"),
            "person_profiles": config_values.get("person_profiles"),
            "source_mode": "snippet",
            "source_snippet": cleaned_snippet,
        },
        enforce_source_contract=True,
    )
