from __future__ import annotations

import hashlib
import re
from pathlib import Path
from typing import Mapping, Set, Tuple

from .config import PROMPT_DIR

PLACEHOLDER_PATTERN = re.compile(r"\{\{([A-Z0-9_]+)\}\}")


def _resolve_prompt_path(filename: str, prompt_dir: Path | None = None) -> Path:
    base_dir = (prompt_dir or PROMPT_DIR).resolve()
    candidate = (base_dir / filename).resolve()
    if base_dir not in candidate.parents:
        raise ValueError(f"Prompt path escapes prompt dir: {filename}")
    return candidate


def extract_placeholders(template: str) -> Set[str]:
    return set(PLACEHOLDER_PATTERN.findall(template))


def validate_placeholders(template: str, variables: Mapping[str, str]) -> None:
    found = extract_placeholders(template)
    missing = {name for name in found if name not in variables}
    if missing:
        raise ValueError(f"Missing placeholders: {sorted(missing)}")


def render_prompt(template: str, variables: Mapping[str, str]) -> str:
    validate_placeholders(template, variables)

    def replacer(match: re.Match[str]) -> str:
        key = match.group(1)
        return str(variables.get(key, ""))

    return PLACEHOLDER_PATTERN.sub(replacer, template)


def read_prompt_file(filename: str, prompt_dir: Path | None = None) -> Tuple[str, str]:
    path = _resolve_prompt_path(filename, prompt_dir)
    content = path.read_text(encoding="utf-8")
    prompt_sha256 = hashlib.sha256(content.encode("utf-8")).hexdigest()
    return content, prompt_sha256


def render_prompt_file(filename: str, variables: Mapping[str, str], prompt_dir: Path | None = None) -> Tuple[str, str]:
    template, prompt_sha256 = read_prompt_file(filename, prompt_dir)
    rendered = render_prompt(template, variables)
    return rendered, prompt_sha256


def truncate_bounded(text: str, max_chars: int) -> str:
    if max_chars <= 0:
        return ""
    if len(text) <= max_chars:
        return text
    return text[:max_chars].rstrip()
