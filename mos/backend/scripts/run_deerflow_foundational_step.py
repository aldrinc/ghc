from __future__ import annotations

import argparse
import json
import re
import time
from pathlib import Path
from typing import Any


def _parse_tagged_blocks(raw: str) -> dict[str, str]:
    summary_match = re.search(r"<SUMMARY>(.*?)</SUMMARY>", raw, flags=re.S | re.I)
    content_match = re.search(r"<CONTENT>(.*?)</CONTENT>", raw, flags=re.S | re.I)
    return {
        "summary": summary_match.group(1).strip() if summary_match else "",
        "content": content_match.group(1).strip() if content_match else raw.strip(),
    }


_STEP04_PLACEHOLDER_PHRASES = (
    "full research document with all 9 categories",
    "...full content per instructions...",
    "[full research document containing:]",
)
_STEP04_STATUS_PHRASES = (
    "let me write",
    "let me compile",
    "i now have enough data",
    "i have sufficient research data",
    "i now have extensive research data",
)
_STEP04_REQUIRED_TERMS = (
    "signal-to-noise",
    "bayesian confidence",
    "bottleneck identification",
    "core avatar belief",
)


def validate_step04_dsv4_output(raw: str) -> list[str]:
    """Return validation errors for DSV4 Step 04 final output."""
    text = raw.strip()
    parsed = _parse_tagged_blocks(text)
    summary = parsed["summary"]
    content = parsed["content"]
    lowered = text.lower()
    content_lowered = content.lower().translate(str.maketrans({"‐": "-", "‑": "-", "‒": "-", "–": "-", "—": "-"}))
    errors: list[str] = []
    if not re.search(r"<SUMMARY>.*?</SUMMARY>", text, flags=re.S | re.I):
        errors.append("missing <SUMMARY> block")
    if not re.search(r"<CONTENT>.*?</CONTENT>", text, flags=re.S | re.I):
        errors.append("missing <CONTENT> block")
    if not summary:
        errors.append("empty summary")
    if not content:
        errors.append("empty content")
    if any(phrase in lowered for phrase in _STEP04_STATUS_PHRASES):
        errors.append("status/planning text instead of final report")
    if any(phrase in content_lowered for phrase in _STEP04_PLACEHOLDER_PHRASES):
        errors.append("placeholder content instead of full report")
    if len(content) < 8000:
        errors.append("content shorter than 8000 chars")

    missing_categories: list[str] = []
    for letter in "ABCDEFGHI":
        category_pattern = rf"(^|\n)\s*(#{{1,6}}\s*)?(category\s+{letter}\b|{letter}[\).:-]\s+)"
        if not re.search(category_pattern, content, flags=re.I):
            missing_categories.append(letter)
    if missing_categories:
        errors.append(f"missing category sections: {', '.join(missing_categories)}")

    quote_count = len(re.findall(r"(^|\n)\s*QUOTE:\s*", content, flags=re.I))
    if quote_count < 20:
        errors.append(f"quote bank too thin: {quote_count} QUOTE entries")
    source_count = len(re.findall(r"(^|\n)\s*SOURCE:\s*", content, flags=re.I))
    if source_count < 20:
        errors.append(f"source metadata too thin: {source_count} SOURCE entries")

    for term in _STEP04_REQUIRED_TERMS:
        if term not in content_lowered:
            errors.append(f"missing required section: {term}")
    return errors


def _stringify_content(value: Any) -> str:
    if isinstance(value, str):
        return value
    if isinstance(value, list):
        parts: list[str] = []
        for item in value:
            if isinstance(item, str):
                parts.append(item)
            elif isinstance(item, dict):
                text = item.get("text") or item.get("content")
                if isinstance(text, str):
                    parts.append(text)
        return "\n".join(parts)
    return str(value or "")


def _compact_text(value: str, *, max_chars: int) -> str:
    text = " ".join(value.split())
    if len(text) <= max_chars:
        return text
    return text[: max_chars - 3].rstrip() + "..."


def _format_search_tool_result(content: str, args: dict[str, Any]) -> str:
    try:
        payload = json.loads(content)
    except json.JSONDecodeError:
        raw = _compact_text(content, max_chars=1200)
        return f"SEARCH RESULT\nQUERY: {args.get('query') or ''}\nRAW: {raw}"
    if not isinstance(payload, dict):
        return f"SEARCH RESULT\nRAW: {_compact_text(content, max_chars=1200)}"
    query = str(payload.get("query") or args.get("query") or "").strip()
    lines = [f"SEARCH QUERY: {query}"]
    results = payload.get("results")
    if isinstance(results, list):
        for item in results[:6]:
            if not isinstance(item, dict):
                continue
            title = _compact_text(str(item.get("title") or ""), max_chars=180)
            url = str(item.get("url") or "").strip()
            snippet = _compact_text(
                str(item.get("content") or item.get("snippet") or ""),
                max_chars=500,
            )
            lines.append(f"- TITLE: {title}\n  URL: {url}\n  SNIPPET: {snippet}")
    return "\n".join(lines)


def _format_fetch_tool_result(content: str, args: dict[str, Any]) -> str:
    url = str(args.get("url") or args.get("source") or "").strip()
    return f"FETCHED SOURCE\nURL: {url}\nCONTENT: {_compact_text(content, max_chars=2500)}"


def _write_step04_evidence_ledger(events_path: Path, ledger_path: Path) -> str:
    tool_args_by_id: dict[str, dict[str, Any]] = {}
    evidence_blocks: list[str] = []
    for line in events_path.read_text(encoding="utf-8", errors="replace").splitlines():
        if not line.strip():
            continue
        try:
            event = json.loads(line)
        except json.JSONDecodeError:
            continue
        if event.get("type") != "messages-tuple":
            continue
        data = event.get("data") or {}
        if not isinstance(data, dict):
            continue
        if data.get("type") == "ai":
            tool_calls = data.get("tool_calls")
            if isinstance(tool_calls, list):
                for tool_call in tool_calls:
                    if not isinstance(tool_call, dict):
                        continue
                    tool_call_id = str(tool_call.get("id") or "")
                    if tool_call_id:
                        raw_args = tool_call.get("args")
                        tool_args_by_id[tool_call_id] = (
                            raw_args if isinstance(raw_args, dict) else {}
                        )
            continue
        if data.get("type") != "tool":
            continue
        name = str(data.get("name") or "")
        content = str(data.get("content") or "")
        args = tool_args_by_id.get(str(data.get("tool_call_id") or ""), {})
        if name == "web_search":
            evidence_blocks.append(_format_search_tool_result(content, args))
        elif name == "web_fetch":
            evidence_blocks.append(_format_fetch_tool_result(content, args))

    ledger = "\n\n---\n\n".join(evidence_blocks)
    if len(ledger) > 140000:
        ledger = ledger[:140000].rstrip() + "\n\n[TRUNCATED_TO_140000_CHARS]"
    ledger_path.write_text(ledger + "\n", encoding="utf-8")
    return ledger


def _build_step04_research_prompt(prompt: str, *, max_searches: int, max_fetches: int) -> str:
    return (
        prompt.rstrip()
        + "\n\n## DeerFlow Research Phase Instructions\n"
        "Use web_search and web_fetch to gather source evidence only. Keep tool use efficient. "
        f"Hard research budget: at most {max_searches} web_search calls and "
        f"at most {max_fetches} web_fetch calls. "
        "Do not write the final report in this phase. Do not say you will write it next. "
        "When enough evidence has been gathered, stop with exactly: "
        "<RESEARCH_DONE>Evidence gathered.</RESEARCH_DONE>"
    )


def _build_step04_synthesis_prompt(
    prompt: str,
    ledger: str,
    previous_output: str = "",
    errors: list[str] | None = None,
) -> str:
    repair_block = ""
    if errors:
        repair_block = (
            "\n\n## Previous Output Failed Validation\n"
            + "\n".join(f"- {error}" for error in errors)
            + "\n\nDo not repeat those mistakes.\n"
        )
    if previous_output:
        repair_block += "\n## Previous Output Excerpt\n" + previous_output[:12000] + "\n"
    return (
        "You are now in synthesis-only mode. Tools are unavailable. "
        "Write the final Step 04 report now.\n"
        "Output ONLY <SUMMARY> and <CONTENT> blocks. Do not include planning/status text. "
        "You must close both blocks. The final non-whitespace text must be exactly </CONTENT>.\n\n"
        "## Original Step 04 Prompt\n"
        f"{prompt.rstrip()}\n\n"
        "## Captured Evidence Ledger From DeerFlow Tool Use\n"
        f"{ledger}\n"
        f"{repair_block}"
    )


def _invoke_step04_synthesis_model(
    *,
    prompt: str,
    model: str,
    config_path: Path,
) -> tuple[str, dict[str, Any] | None]:
    from deerflow.config.app_config import reload_app_config
    from deerflow.models import create_chat_model
    from langchain_core.messages import HumanMessage

    reload_app_config(str(config_path))
    chat_model = create_chat_model(name=model, thinking_enabled=True, attach_tracing=False)
    response = chat_model.invoke([HumanMessage(content=prompt)])
    usage = getattr(response, "usage_metadata", None)
    usage_dict = dict(usage) if isinstance(usage, dict) else None
    return _stringify_content(getattr(response, "content", "")).strip(), usage_dict


def _jsonable_event(event: Any) -> dict[str, Any]:
    return {
        "type": getattr(event, "type", None),
        "data": getattr(event, "data", None),
    }


def _dedupe_usage_from_events(events_path: Path) -> dict[str, int]:
    by_id: dict[str, dict[str, int]] = {}
    if not events_path.exists():
        return {}
    for line in events_path.read_text(encoding="utf-8", errors="replace").splitlines():
        if not line.strip():
            continue
        try:
            event = json.loads(line)
        except json.JSONDecodeError:
            continue
        messages = (event.get("data") or {}).get("messages")
        if not isinstance(messages, list):
            continue
        for message in messages:
            if not isinstance(message, dict):
                continue
            usage = message.get("usage_metadata")
            message_id = str(message.get("id") or "")
            if not isinstance(usage, dict) or not message_id:
                continue
            raw_input_details = usage.get("input_token_details")
            raw_output_details = usage.get("output_token_details")
            input_details = raw_input_details if isinstance(raw_input_details, dict) else {}
            output_details = raw_output_details if isinstance(raw_output_details, dict) else {}
            by_id[message_id] = {
                "input_tokens": int(usage.get("input_tokens") or 0),
                "output_tokens": int(usage.get("output_tokens") or 0),
                "total_tokens": int(usage.get("total_tokens") or 0),
                "cache_read": int(input_details.get("cache_read") or 0),
                "reasoning": int(output_details.get("reasoning") or 0),
            }
    aggregate = {
        "input_tokens": 0,
        "output_tokens": 0,
        "total_tokens": 0,
        "cache_read": 0,
        "cache_miss_input_tokens": 0,
        "reasoning_tokens": 0,
        "unique_usage_messages": len(by_id),
    }
    for usage in by_id.values():
        aggregate["input_tokens"] += usage["input_tokens"]
        aggregate["output_tokens"] += usage["output_tokens"]
        aggregate["total_tokens"] += usage["total_tokens"]
        aggregate["cache_read"] += usage["cache_read"]
        aggregate["reasoning_tokens"] += usage["reasoning"]
    aggregate["cache_miss_input_tokens"] = max(
        0,
        aggregate["input_tokens"] - aggregate["cache_read"],
    )
    return aggregate


def run(input_path: Path, output_path: Path, config_path: Path) -> int:
    payload = json.loads(input_path.read_text(encoding="utf-8"))
    prompt = str(payload["prompt"])
    model = str(payload.get("model") or "deepseek-v4-pro")
    mode = str(payload.get("mode") or "").strip()
    thread_id = str(payload.get("thread_id") or f"strategy-v2-foundation-{int(time.time())}")
    artifact_dir = Path(str(payload.get("artifact_dir") or output_path.parent)).resolve()
    artifact_dir.mkdir(parents=True, exist_ok=True)
    events_path = artifact_dir / "events.jsonl"
    raw_path = artifact_dir / "raw.md"
    summary_path = artifact_dir / "summary.md"
    content_path = artifact_dir / "content.md"
    evidence_ledger_path = artifact_dir / "evidence-ledger.md"
    synthesis_path = artifact_dir / "synthesis.md"
    run_meta_path = artifact_dir / "run-meta.json"

    from deerflow.client import DeerFlowClient

    client = DeerFlowClient(
        config_path=str(config_path),
        model_name=model,
        thinking_enabled=True,
        subagent_enabled=False,
        plan_mode=False,
        available_skills=set(),
        environment="strategy-v2-foundational-sidecar",
    )

    started = time.time()
    status = "unknown"
    error: str | None = None
    event_count = 0
    tool_counts: dict[str, int] = {}
    tool_result_counts: dict[str, int] = {}
    usage: dict[str, Any] | None = None
    synthesis_usage: dict[str, Any] | None = None
    validation_errors: list[str] = []
    final_chunks_by_id: dict[str, list[str]] = {}
    events_path.write_text("", encoding="utf-8")
    step04_budget_reached = False
    max_step04_searches = int(payload.get("max_web_searches") or 36)
    max_step04_fetches = int(payload.get("max_web_fetches") or 18)
    stream_prompt = (
        _build_step04_research_prompt(
            prompt,
            max_searches=max_step04_searches,
            max_fetches=max_step04_fetches,
        )
        if mode == "step04_dsv4_research_synthesis"
        else prompt
    )
    try:
        with events_path.open("a", encoding="utf-8") as events_file:
            for event in client.stream(stream_prompt, thread_id=thread_id, recursion_limit=250):
                event_count += 1
                event_payload = _jsonable_event(event)
                events_file.write(json.dumps(event_payload, ensure_ascii=False) + "\n")
                data = event_payload.get("data") or {}
                if event.type == "messages-tuple" and data.get("type") == "ai":
                    if isinstance(data.get("tool_calls"), list):
                        for tool_call in data["tool_calls"]:
                            name = str(tool_call.get("name") or "unknown")
                            tool_counts[name] = tool_counts.get(name, 0) + 1
                    content = data.get("content")
                    message_id = str(data.get("id") or "default")
                    if isinstance(content, str) and content:
                        final_chunks_by_id.setdefault(message_id, []).append(content)
                elif event.type == "end":
                    usage = data.get("usage") if isinstance(data, dict) else None
                elif event.type == "messages-tuple" and data.get("type") == "tool":
                    tool_name = str(data.get("name") or "")
                    if tool_name:
                        tool_result_counts[tool_name] = tool_result_counts.get(tool_name, 0) + 1
                    if mode == "step04_dsv4_research_synthesis" and (
                        tool_result_counts.get("web_search", 0) >= max_step04_searches
                        or tool_result_counts.get("web_fetch", 0) >= max_step04_fetches
                    ):
                        step04_budget_reached = True
                        break
        status = "completed"
    except Exception as exc:  # pragma: no cover - integration failure path
        status = "failed"
        error = f"{type(exc).__name__}: {exc}"

    final_text_candidates = ["".join(chunks).strip() for chunks in final_chunks_by_id.values()]
    final_text = next((candidate for candidate in reversed(final_text_candidates) if candidate), "")
    if status == "completed" and mode == "step04_dsv4_research_synthesis":
        try:
            ledger = _write_step04_evidence_ledger(events_path, evidence_ledger_path)
            synthesis_prompt = _build_step04_synthesis_prompt(prompt, ledger)
            final_text, synthesis_usage = _invoke_step04_synthesis_model(
                prompt=synthesis_prompt,
                model=model,
                config_path=config_path,
            )
            validation_errors = validate_step04_dsv4_output(final_text)
            if validation_errors:
                retry_prompt = _build_step04_synthesis_prompt(
                    prompt,
                    ledger,
                    previous_output=final_text,
                    errors=validation_errors,
                )
                retry_text, retry_usage = _invoke_step04_synthesis_model(
                    prompt=retry_prompt,
                    model=model,
                    config_path=config_path,
                )
                retry_errors = validate_step04_dsv4_output(retry_text)
                if not retry_errors:
                    final_text = retry_text
                    validation_errors = []
                    synthesis_usage = retry_usage
                else:
                    final_text = retry_text
                    validation_errors = retry_errors
                    status = "failed"
                    error = "Step 04 DSV4 output validation failed: " + "; ".join(validation_errors)
            synthesis_path.write_text(final_text + "\n", encoding="utf-8")
        except Exception as exc:  # pragma: no cover - integration failure path
            status = "failed"
            error = f"Step 04 DSV4 synthesis failed: {type(exc).__name__}: {exc}"
    raw_path.write_text(final_text + "\n", encoding="utf-8")
    parsed = _parse_tagged_blocks(final_text)
    summary_path.write_text(parsed["summary"] + "\n", encoding="utf-8")
    content_path.write_text(parsed["content"] + "\n", encoding="utf-8")
    deduped_usage = _dedupe_usage_from_events(events_path)
    run_meta = {
        "thread_id": thread_id,
        "status": status,
        "error": error,
        "mode": mode or "agent_stream",
        "elapsed_seconds": round(time.time() - started, 3),
        "event_count": event_count,
        "tool_counts": tool_counts,
        "tool_result_counts": tool_result_counts,
        "step04_research_budget": (
            {
                "max_web_searches": max_step04_searches,
                "max_web_fetches": max_step04_fetches,
                "budget_reached": step04_budget_reached,
            }
            if mode == "step04_dsv4_research_synthesis"
            else None
        ),
        "usage": usage,
        "synthesis_usage": synthesis_usage,
        "validation_errors": validation_errors,
        "deduped_usage": deduped_usage,
        "events_path": str(events_path),
        "evidence_ledger_path": (
            str(evidence_ledger_path) if evidence_ledger_path.exists() else None
        ),
        "synthesis_path": str(synthesis_path) if synthesis_path.exists() else None,
        "raw_output_path": str(raw_path),
        "summary_path": str(summary_path),
        "content_path": str(content_path),
        "no_output_token_cap": True,
    }
    run_meta_path.write_text(
        json.dumps(run_meta, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    result = {
        "status": status,
        "error": error,
        "summary": parsed["summary"],
        "content": parsed["content"],
        "raw_output": final_text,
        "run_meta": run_meta,
        "handoff": {
            "deerflow": {
                "model": model,
                "thread_id": thread_id,
                "artifact_dir": str(artifact_dir),
                "events_path": str(events_path),
                "run_meta_path": str(run_meta_path),
                "tool_counts": tool_counts,
                "usage": usage,
                "deduped_usage": deduped_usage,
                "no_output_token_cap": True,
            }
        },
    }
    output_path.write_text(
        json.dumps(result, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    return 0 if status == "completed" else 1


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", required=True)
    parser.add_argument("--output", required=True)
    parser.add_argument("--config", required=True)
    args = parser.parse_args()
    return run(
        input_path=Path(args.input).resolve(),
        output_path=Path(args.output).resolve(),
        config_path=Path(args.config).resolve(),
    )


if __name__ == "__main__":
    raise SystemExit(main())
