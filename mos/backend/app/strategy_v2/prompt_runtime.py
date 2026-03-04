from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
from pathlib import Path
import re
from typing import Any, Mapping

from app.strategy_v2.errors import StrategyV2MissingContextError, StrategyV2SchemaValidationError


_PLACEHOLDER_PATTERN = re.compile(r"\{\{([A-Za-z0-9_]+)\}\}")
_JSON_BLOCK_PATTERN = re.compile(r"```(?:json)?\s*(.*?)```", re.IGNORECASE | re.DOTALL)


@dataclass(frozen=True)
class PromptAsset:
    absolute_path: Path
    relative_path: str
    sha256: str
    text: str


@dataclass(frozen=True)
class PromptProvenance:
    prompt_path: str
    prompt_sha256: str
    model_name: str
    input_contract_version: str
    output_contract_version: str

    def to_dict(self) -> dict[str, str]:
        return {
            "prompt_path": self.prompt_path,
            "prompt_sha256": self.prompt_sha256,
            "model_name": self.model_name,
            "input_contract_version": self.input_contract_version,
            "output_contract_version": self.output_contract_version,
        }


def locate_repo_root_with_v2_fixes() -> Path:
    for parent in Path(__file__).resolve().parents:
        candidate = parent / "V2 Fixes"
        if candidate.exists() and candidate.is_dir():
            return parent
    raise StrategyV2MissingContextError(
        "Unable to locate 'V2 Fixes' directory from backend runtime path. "
        "Remediation: run backend from repository root with V2 Fixes assets present."
    )


def resolve_prompt_asset(*, pattern: str, context: str) -> PromptAsset:
    root = locate_repo_root_with_v2_fixes()
    matches = sorted((root / "V2 Fixes").glob(pattern))
    if len(matches) != 1:
        raise StrategyV2MissingContextError(
            f"Expected exactly one file for {context} pattern '{pattern}', found {len(matches)}. "
            "Remediation: verify V2 Fixes prompt assets are present and unique."
        )
    path = matches[0]
    raw_text = path.read_text(encoding="utf-8")
    cleaned = raw_text.strip()
    if not cleaned:
        raise StrategyV2MissingContextError(
            f"Resolved prompt is empty for {context}: {path}. "
            "Remediation: restore prompt contents in V2 Fixes."
        )
    rel = path.relative_to(root).as_posix()
    sha = hashlib.sha256(raw_text.encode("utf-8")).hexdigest()
    return PromptAsset(absolute_path=path, relative_path=rel, sha256=sha, text=cleaned)


def render_prompt_template(*, template: str, variables: Mapping[str, str], context: str) -> str:
    placeholders = set(_PLACEHOLDER_PATTERN.findall(template))
    missing = sorted(name for name in placeholders if name not in variables)
    if missing:
        raise StrategyV2MissingContextError(
            f"Missing placeholders for {context} prompt: {missing}. "
            "Remediation: provide all required runtime variables before executing this prompt."
        )

    def _replace(match: re.Match[str]) -> str:
        return str(variables.get(match.group(1), ""))

    return _PLACEHOLDER_PATTERN.sub(_replace, template)


def build_prompt_provenance(
    *,
    asset: PromptAsset,
    model_name: str,
    input_contract_version: str,
    output_contract_version: str,
) -> PromptProvenance:
    return PromptProvenance(
        prompt_path=asset.relative_path,
        prompt_sha256=asset.sha256,
        model_name=model_name,
        input_contract_version=input_contract_version,
        output_contract_version=output_contract_version,
    )


def extract_json_code_blocks(raw_text: str) -> list[Any]:
    blocks = _JSON_BLOCK_PATTERN.findall(raw_text)
    parsed: list[Any] = []
    for block in blocks:
        candidate = block.strip()
        if not candidate:
            continue
        try:
            parsed.append(json.loads(candidate))
        except json.JSONDecodeError:
            continue
    return parsed


def extract_required_json_object(*, raw_text: str, field_name: str) -> dict[str, Any]:
    direct = _try_parse_json(raw_text)
    if isinstance(direct, dict):
        return direct

    for block in extract_json_code_blocks(raw_text):
        if isinstance(block, dict):
            return block

    parsed_inline = _extract_first_json_value(raw_text)
    if isinstance(parsed_inline, dict):
        return parsed_inline

    raise StrategyV2SchemaValidationError(
        f"Expected JSON object for '{field_name}' but none could be extracted."
    )


def extract_required_json_array(*, raw_text: str, field_name: str) -> list[Any]:
    direct = _try_parse_json(raw_text)
    if isinstance(direct, list):
        return direct

    for block in extract_json_code_blocks(raw_text):
        if isinstance(block, list):
            return block

    parsed_inline = _extract_first_json_value(raw_text)
    if isinstance(parsed_inline, list):
        return parsed_inline

    raise StrategyV2SchemaValidationError(
        f"Expected JSON array for '{field_name}' but none could be extracted."
    )


def extract_required_section(*, raw_text: str, heading: str, field_name: str) -> str:
    pattern = re.compile(
        rf"(?ims)^\s*#+\s*{re.escape(heading)}\s*$\n(.*?)(?=^\s*#|\Z)"
    )
    match = pattern.search(raw_text)
    if not match:
        raise StrategyV2SchemaValidationError(
            f"Missing required section '{heading}' for '{field_name}'."
        )
    content = match.group(1).strip()
    if not content:
        raise StrategyV2SchemaValidationError(
            f"Section '{heading}' is empty for '{field_name}'."
        )
    return content


def _try_parse_json(raw_text: str) -> Any:
    text = raw_text.strip()
    if not text:
        return None
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        return None


def _extract_first_json_value(raw_text: str) -> Any:
    text = raw_text.strip()
    if not text:
        return None

    decoder = json.JSONDecoder()
    for index, char in enumerate(text):
        if char not in "[{":
            continue
        try:
            parsed, _ = decoder.raw_decode(text[index:])
            return parsed
        except json.JSONDecodeError:
            continue
    return None
