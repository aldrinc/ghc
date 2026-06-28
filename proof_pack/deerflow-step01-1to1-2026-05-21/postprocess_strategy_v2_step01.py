from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any


ROOT = Path("/Users/aldrinclement/Documents/programming/marketi")
PROOF_DIR = ROOT / "proof_pack/deerflow-step01-1to1-2026-05-21"
OUTPUT_DIR = PROOF_DIR / "outputs"
SOURCE_DIR = PROOF_DIR / "sources"
EVENTS_PATH = OUTPUT_DIR / "deerflow-dsv4-step01-events.jsonl"
RAW_PATH = OUTPUT_DIR / "deerflow-dsv4-step01-raw.md"
CONTENT_PATH = OUTPUT_DIR / "deerflow-dsv4-step01-content.md"
GPT_PATH = ROOT / ".local/tenor-strategy-run-docs-prod-20260426/docs/03-v2-02.foundation.01-raw.md"
PROMPT_PATH = OUTPUT_DIR / "rendered-strategy-v2-step01-prompt.md"
VALIDATION_PATH = OUTPUT_DIR / "deerflow-dsv4-step01-validation.json"
TOOL_CALLS_PATH = SOURCE_DIR / "deerflow-tool-calls.json"
SOURCE_URLS_PATH = SOURCE_DIR / "deerflow-source-urls.json"


URL_RE = re.compile(r"https?://[^\s)>\]\"']+")


def _load_events() -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    if not EVENTS_PATH.exists():
        return rows
    for line in EVENTS_PATH.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        rows.append(json.loads(line))
    return rows


def _extract_tool_calls(events: list[dict[str, Any]]) -> list[dict[str, Any]]:
    calls_by_id: dict[str, dict[str, Any]] = {}
    ordered: list[dict[str, Any]] = []
    for event in events:
        data = event.get("data") or {}
        if data.get("type") == "ai" and isinstance(data.get("tool_calls"), list):
            for call in data["tool_calls"]:
                call_id = str(call.get("id") or f"call_{len(ordered) + 1}")
                row = {
                    "id": call_id,
                    "name": call.get("name"),
                    "args": call.get("args"),
                    "result": None,
                }
                calls_by_id[call_id] = row
                ordered.append(row)
        elif data.get("type") == "tool":
            call_id = str(data.get("tool_call_id") or "")
            row = calls_by_id.get(call_id)
            if row is not None:
                row["result"] = data.get("content")
    return ordered


def _extract_urls(raw: str, tool_calls: list[dict[str, Any]]) -> list[str]:
    urls = set(URL_RE.findall(raw))
    for call in tool_calls:
        args = call.get("args")
        if isinstance(args, dict):
            for value in args.values():
                if isinstance(value, str):
                    urls.update(URL_RE.findall(value))
        result = call.get("result")
        if isinstance(result, str):
            urls.update(URL_RE.findall(result))
    return sorted(url.rstrip(".,") for url in urls)


def _has_tag(raw: str, tag: str) -> bool:
    return bool(re.search(fr"<{tag}>.*?</{tag}>", raw, flags=re.S | re.I))


def _count_phase_headings(raw: str) -> int:
    return sum(1 for n in range(1, 10) if re.search(fr"Phase\s+{n}\b", raw, flags=re.I))


def _score_validation(raw: str, prompt: str, tool_calls: list[dict[str, Any]], urls: list[str]) -> dict[str, Any]:
    gpt_raw = GPT_PATH.read_text(encoding="utf-8") if GPT_PATH.exists() else ""
    tool_names = [str(call.get("name") or "") for call in tool_calls]
    web_calls = sum(1 for name in tool_names if name in {"web_search", "web_fetch"})
    validation = {
        "prompt_is_strategy_v2_step01": "Competitor & Market Intelligence Agent (v2)" in prompt,
        "prompt_is_not_older_precanon_prompt": "Master Competitor / Market Analysis Prompt" not in prompt,
        "has_summary_tag": _has_tag(raw, "SUMMARY"),
        "has_content_tag": _has_tag(raw, "CONTENT"),
        "phase_heading_count": _count_phase_headings(raw),
        "has_all_phase_1_to_9_headings": _count_phase_headings(raw) == 9,
        "has_traction_score": bool(re.search(r"Traction\s+Score", raw, flags=re.I)),
        "has_d1_to_d5_columns_or_mentions": all(token in raw for token in ["D1", "D2", "D3", "D4", "D5"]),
        "calculator_tool_called": "calculator" in tool_names,
        "web_tool_call_count": web_calls,
        "web_search_call_count": tool_names.count("web_search"),
        "web_fetch_call_count": tool_names.count("web_fetch"),
        "unique_url_count": len(urls),
        "citation_url_count": len(URL_RE.findall(raw)),
        "raw_chars": len(raw),
        "gpt_reference_chars": len(gpt_raw),
        "gpt_reference_had_tool_limit_failure": "web tool hit a hard call-limit" in gpt_raw,
        "contains_smoke_bounds": any(
            marker in raw.lower()
            for marker in ["smoke test", "at most 2 web_search", "at most 2 web_fetch", "bounded deerflow sidecar smoke"]
        ),
    }
    required = [
        "prompt_is_strategy_v2_step01",
        "prompt_is_not_older_precanon_prompt",
        "has_summary_tag",
        "has_content_tag",
        "has_all_phase_1_to_9_headings",
        "has_traction_score",
        "has_d1_to_d5_columns_or_mentions",
        "calculator_tool_called",
    ]
    validation["pass"] = all(validation[key] for key in required) and validation["citation_url_count"] >= 15 and not validation["contains_smoke_bounds"]
    validation["required_checks"] = required
    return validation


def main() -> int:
    SOURCE_DIR.mkdir(parents=True, exist_ok=True)
    events = _load_events()
    raw = RAW_PATH.read_text(encoding="utf-8") if RAW_PATH.exists() else ""
    prompt = PROMPT_PATH.read_text(encoding="utf-8") if PROMPT_PATH.exists() else ""
    tool_calls = _extract_tool_calls(events)
    urls = _extract_urls(raw, tool_calls)
    TOOL_CALLS_PATH.write_text(json.dumps(tool_calls, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    SOURCE_URLS_PATH.write_text(json.dumps(urls, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    validation = _score_validation(raw, prompt, tool_calls, urls)
    validation["tool_calls_path"] = str(TOOL_CALLS_PATH)
    validation["source_urls_path"] = str(SOURCE_URLS_PATH)
    validation["content_path"] = str(CONTENT_PATH)
    VALIDATION_PATH.write_text(json.dumps(validation, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(json.dumps(validation, indent=2, ensure_ascii=False))
    return 0 if validation["pass"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
