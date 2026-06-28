from __future__ import annotations

import hashlib
import json
import os
import re
import signal
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


ROOT = Path("/Users/aldrinclement/Documents/programming/marketi")
DEERFLOW_ROOT = ROOT / ".local/deer-flow"
CONFIG_PATH = DEERFLOW_ROOT / "config.yaml"
PROOF_DIR = ROOT / "proof_pack/deerflow-step01-1to1-2026-05-21"
OUTPUT_DIR = PROOF_DIR / "outputs"
LOG_DIR = PROOF_DIR / "logs"
SOURCE_DIR = PROOF_DIR / "sources"

PROMPT_PATH = ROOT / "V2 Fixes/Foundational Docs/clean_prompts/01_competitor_research_v2.md"
STAGE0_PATH = ROOT / ".local/tenor-strategy-run-docs-prod-20260426/docs/00-stage0.json"
ACTIVITY_LOG_PATH = ROOT / ".local/tenor-strategy-run-docs-prod-20260426/metadata/activity-logs.json"
GPT_STEP01_PATH = ROOT / ".local/tenor-strategy-run-docs-prod-20260426/docs/03-v2-02.foundation.01-raw.md"

PROMPT_OUT = OUTPUT_DIR / "rendered-strategy-v2-step01-prompt.md"
PROMPT_META_OUT = OUTPUT_DIR / "rendered-strategy-v2-step01-prompt.meta.json"
EVENTS_OUT = OUTPUT_DIR / "deerflow-dsv4-step01-events.jsonl"
RAW_OUT = OUTPUT_DIR / "deerflow-dsv4-step01-raw.md"
SUMMARY_OUT = OUTPUT_DIR / "deerflow-dsv4-step01-summary.md"
CONTENT_OUT = OUTPUT_DIR / "deerflow-dsv4-step01-content.md"
RUN_META_OUT = OUTPUT_DIR / "deerflow-dsv4-step01-run.meta.json"


class RunTimedOut(Exception):
    pass


def _timeout_handler(_signum, _frame):
    raise RunTimedOut("DeerFlow Strategy V2 Step 1 run timed out")


def _sha256(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _render_template(template: str, variables: dict[str, str]) -> str:
    pattern = re.compile(r"\{\{([A-Z0-9_]+)\}\}")
    missing = sorted({match.group(1) for match in pattern.finditer(template)} - set(variables))
    if missing:
        raise RuntimeError(f"Missing prompt variables: {missing}")
    return pattern.sub(lambda match: variables.get(match.group(1), ""), template)


def _append_tagged_output_guardrails(prompt_text: str) -> str:
    return (
        prompt_text.rstrip()
        + "\n\nReturn ONLY tagged blocks in this exact structure:\n"
        + "<SUMMARY>Bounded summary.</SUMMARY>\n"
        + "<CONTENT>Full output.</CONTENT>\n"
    )


def _load_category_niche() -> str:
    logs = json.loads(ACTIVITY_LOG_PATH.read_text(encoding="utf-8"))
    for row in logs:
        if row.get("step") == "v2-02.foundation" and row.get("status") == "completed":
            out = row.get("payload_out") or {}
            value = out.get("category_niche")
            if isinstance(value, str) and value.strip():
                return value.strip()
    raise RuntimeError("Could not recover category_niche from production activity log")


def _build_recovered_onboarding_payload(stage0: dict[str, Any], category_niche: str) -> dict[str, Any]:
    return {
        "product_name": stage0["product_name"],
        "description": stage0["description"],
        "price": stage0["price"],
        "competitor_urls": stage0.get("competitor_urls") or [],
        "product_customizable": stage0.get("product_customizable"),
        "product_category": category_niche,
        "business_model": "ecommerce",
        "target_regions": ["United States", "Canada"],
        "funnel_position": "Cold",
        "target_platforms": ["Meta"],
        "existing_proof_assets": ["N/A"],
        "brand_voice": "conversational",
        "brand_story": "natural male testosterone enhancement for older men facing testosterone decline",
    }


def render_prompt() -> dict[str, Any]:
    stage0 = json.loads(STAGE0_PATH.read_text(encoding="utf-8"))
    category_niche = _load_category_niche()
    business_context = f"{stage0['product_name']}: {stage0['description']}".strip()
    recovered_onboarding_payload = _build_recovered_onboarding_payload(stage0, category_niche)
    context_payload = {
        "stage0": stage0,
        "onboarding_payload": recovered_onboarding_payload,
    }
    variables = {
        "BUSINESS_CONTEXT": business_context,
        "BUSINESS_CONTEXT_JSON": json.dumps(context_payload, ensure_ascii=True),
        "CATEGORY_NICHE": category_niche,
        "ADS_CONTEXT": "",
    }
    template = PROMPT_PATH.read_text(encoding="utf-8").strip()
    rendered = _render_template(template, variables)
    guarded = _append_tagged_output_guardrails(rendered)

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    PROMPT_OUT.write_text(guarded + "\n", encoding="utf-8")
    meta = {
        "rendered_at": datetime.now(timezone.utc).isoformat(),
        "prompt_source_path": str(PROMPT_PATH),
        "prompt_template_sha256": _sha256(template),
        "guarded_prompt_sha256": _sha256(guarded),
        "stage0_path": str(STAGE0_PATH),
        "activity_log_path": str(ACTIVITY_LOG_PATH),
        "business_context": business_context,
        "category_niche": category_niche,
        "model_under_test": "deepseek-v4-pro",
        "reference_model_from_activity_log": "gpt-5.2-2025-12-11",
        "reference_activity_elapsed_seconds": 520.16,
        "reference_gpt_output_path": str(GPT_STEP01_PATH),
        "no_output_token_cap": True,
        "deerflow_config_path": str(CONFIG_PATH),
        "tools_required": ["web_search", "web_fetch", "calculator"],
        "known_delta": (
            "Production export does not include the raw onboarding_payload DB row. "
            "onboarding_payload was reconstructed only from Stage 0, activity logs, workflow input, and Step 03 echo text."
        ),
        "variables": variables,
    }
    PROMPT_META_OUT.write_text(json.dumps(meta, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return {"prompt": guarded, "meta": meta}


def event_to_jsonable(event) -> dict[str, Any]:
    return {
        "type": getattr(event, "type", None),
        "data": getattr(event, "data", None),
    }


def parse_tagged_blocks(raw: str) -> dict[str, str]:
    summary_match = re.search(r"<SUMMARY>(.*?)</SUMMARY>", raw, flags=re.S | re.I)
    content_match = re.search(r"<CONTENT>(.*?)</CONTENT>", raw, flags=re.S | re.I)
    return {
        "summary": summary_match.group(1).strip() if summary_match else "",
        "content": content_match.group(1).strip() if content_match else raw.strip(),
    }


def run_deerflow(prompt: str) -> int:
    required = ["DEEPSEEK_API_KEY", "SERPER_API_KEY", "JINA_API_KEY"]
    missing = [name for name in required if not os.getenv(name)]
    if missing:
        print(f"Missing required env vars: {', '.join(missing)}", file=sys.stderr)
        return 2

    from deerflow.client import DeerFlowClient

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    SOURCE_DIR.mkdir(parents=True, exist_ok=True)
    EVENTS_OUT.write_text("", encoding="utf-8")

    client = DeerFlowClient(
        config_path=str(CONFIG_PATH),
        model_name="deepseek-v4-pro",
        thinking_enabled=True,
        subagent_enabled=False,
        plan_mode=False,
        available_skills=set(),
        environment="local-sidecar",
    )

    thread_id = f"marketi-strategy-v2-step01-dsv4-{int(time.time())}"
    started = time.time()
    status = "unknown"
    error = None
    final_chunks_by_id: dict[str, list[str]] = {}
    event_count = 0
    tool_counts: dict[str, int] = {}
    usage: dict[str, Any] | None = None

    signal.signal(signal.SIGALRM, _timeout_handler)
    signal.alarm(3600)
    try:
        with EVENTS_OUT.open("a", encoding="utf-8") as events_file:
            for event in client.stream(prompt, thread_id=thread_id, recursion_limit=250):
                event_count += 1
                payload = event_to_jsonable(event)
                events_file.write(json.dumps(payload, ensure_ascii=False) + "\n")
                events_file.flush()
                data = payload.get("data") or {}
                if event.type == "messages-tuple" and data.get("type") == "ai":
                    if isinstance(data.get("tool_calls"), list):
                        for tool_call in data["tool_calls"]:
                            name = str(tool_call.get("name") or "unknown")
                            tool_counts[name] = tool_counts.get(name, 0) + 1
                            print(f"[tool_call] {name}", flush=True)
                    content = data.get("content")
                    msg_id = str(data.get("id") or "default")
                    if isinstance(content, str) and content:
                        final_chunks_by_id.setdefault(msg_id, []).append(content)
                elif event.type == "end":
                    usage = data.get("usage") if isinstance(data, dict) else None
                if event_count % 25 == 0:
                    print(f"[progress] events={event_count} tools={tool_counts}", flush=True)
        status = "completed"
    except RunTimedOut as exc:
        status = "timed_out"
        error = str(exc)
    except Exception as exc:
        status = "failed"
        error = f"{type(exc).__name__}: {exc}"
    finally:
        signal.alarm(0)

    final_text_candidates = ["".join(chunks).strip() for chunks in final_chunks_by_id.values()]
    final_text_candidates = [candidate for candidate in final_text_candidates if candidate]
    final_text = final_text_candidates[-1] if final_text_candidates else ""
    if not final_text:
        final_text = "(No final AI text captured; inspect event log.)"
    RAW_OUT.write_text(final_text + "\n", encoding="utf-8")

    parsed = parse_tagged_blocks(final_text)
    SUMMARY_OUT.write_text(parsed["summary"] + "\n", encoding="utf-8")
    CONTENT_OUT.write_text(parsed["content"] + "\n", encoding="utf-8")

    run_meta = {
        "thread_id": thread_id,
        "status": status,
        "error": error,
        "elapsed_seconds": round(time.time() - started, 3),
        "event_count": event_count,
        "tool_counts": tool_counts,
        "usage": usage,
        "events_path": str(EVENTS_OUT),
        "raw_output_path": str(RAW_OUT),
        "summary_path": str(SUMMARY_OUT),
        "content_path": str(CONTENT_OUT),
        "prompt_path": str(PROMPT_OUT),
        "no_output_token_cap": True,
    }
    RUN_META_OUT.write_text(json.dumps(run_meta, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(json.dumps(run_meta, indent=2, ensure_ascii=False))
    return 0 if status == "completed" else 124


def main() -> int:
    rendered = render_prompt()
    if "--render-only" in sys.argv:
        print(json.dumps(rendered["meta"], indent=2, ensure_ascii=False))
        return 0
    return run_deerflow(rendered["prompt"])


if __name__ == "__main__":
    raise SystemExit(main())
