from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any


ROOT = Path("/Users/aldrinclement/Documents/programming/marketi")
PROOF_DIR = ROOT / "proof_pack/deerflow-foundational-steps03-04-1to1-2026-05-21"
OUTPUT_DIR = PROOF_DIR / "outputs"
SOURCES_DIR = PROOF_DIR / "sources"
RUNS_DIR = PROOF_DIR / "runs/dsv4-foundational-03-04-1to1"
CONT_DIR = PROOF_DIR / "runs-continuation/dsv4-foundational-03-04-1to1"

GPT_STEP03_ARTIFACT = (
    ROOT
    / ".local/tenor-strategy-run-docs-prod-20260426/artifacts/strategy_v2_step_payload-5e9d8334-9042-4878-9c38-88770b0f4625.json"
)
GPT_STEP04_ARTIFACT = (
    ROOT
    / ".local/tenor-strategy-run-docs-prod-20260426/artifacts/strategy_v2_step_payload-5992a9b5-3d5c-48b9-a7cd-7869d2946843.json"
)
GPT_STEP03_DOC = ROOT / ".local/tenor-strategy-run-docs-prod-20260426/docs/04-v2-02.foundation.03-raw.md"
GPT_STEP04_DOC = ROOT / ".local/tenor-strategy-run-docs-prod-20260426/docs/05-v2-02.foundation.04-raw.md"

URL_RE = re.compile(r"https?://[^\s)>\]\"']+")


def _json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _artifact_payload(path: Path) -> dict[str, Any]:
    return _json(path)["data"]["payload"]


def _text(path: Path) -> str:
    return path.read_text(encoding="utf-8", errors="replace") if path.exists() else ""


def _tool_counts(events_path: Path) -> dict[str, int]:
    counts: dict[str, int] = {}
    if not events_path.exists():
        return counts
    for line in events_path.read_text(encoding="utf-8", errors="replace").splitlines():
        if not line.strip():
            continue
        try:
            event = json.loads(line)
        except json.JSONDecodeError:
            continue
        data = event.get("data") or {}
        if data.get("type") == "ai" and isinstance(data.get("tool_calls"), list):
            for call in data["tool_calls"]:
                name = str(call.get("name") or "unknown")
                counts[name] = counts.get(name, 0) + 1
    return counts


def _usage_cost(meta: dict[str, Any], *, serper_searches: int) -> dict[str, float | int]:
    usage = meta.get("deduped_usage")
    usage = usage if isinstance(usage, dict) else {}
    input_tokens = int(usage.get("input_tokens") or 0)
    output_tokens = int(usage.get("output_tokens") or 0)
    cache_read = int(usage.get("cache_read") or 0)
    cache_miss = int(usage.get("cache_miss_input_tokens") or max(0, input_tokens - cache_read))
    deepseek_promo = (
        (cache_read / 1_000_000 * 0.003625)
        + (cache_miss / 1_000_000 * 0.435)
        + (output_tokens / 1_000_000 * 0.87)
    )
    deepseek_list = (
        (cache_read / 1_000_000 * 0.0145)
        + (cache_miss / 1_000_000 * 1.74)
        + (output_tokens / 1_000_000 * 3.48)
    )
    serper = serper_searches / 1000
    return {
        "input_tokens": input_tokens,
        "output_tokens": output_tokens,
        "cache_read": cache_read,
        "cache_miss_input_tokens": cache_miss,
        "serper_searches": serper_searches,
        "deepseek_promo_usd": deepseek_promo,
        "deepseek_list_usd": deepseek_list,
        "serper_usd": serper,
        "promo_total_usd": deepseek_promo + serper,
        "list_total_usd": deepseek_list + serper,
    }


def _events_summary(events_path: Path) -> dict[str, Any]:
    ai_chars_by_id: dict[str, int] = {}
    ended = False
    line_count = 0
    for line in events_path.read_text(encoding="utf-8", errors="replace").splitlines() if events_path.exists() else []:
        line_count += 1
        if not line.strip():
            continue
        try:
            event = json.loads(line)
        except json.JSONDecodeError:
            continue
        if event.get("type") == "end":
            ended = True
        data = event.get("data") or {}
        if data.get("type") == "ai" and isinstance(data.get("content"), str) and data.get("content"):
            message_id = str(data.get("id") or "default")
            ai_chars_by_id[message_id] = ai_chars_by_id.get(message_id, 0) + len(data["content"])
    return {
        "event_lines": line_count,
        "ended": ended,
        "tool_counts": _tool_counts(events_path),
        "ai_chars_by_id": ai_chars_by_id,
    }


def main() -> int:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    SOURCES_DIR.mkdir(parents=True, exist_ok=True)

    step03_meta = _json(OUTPUT_DIR / "dsv4-step03-run.meta.json")
    step04_meta = _json(RUNS_DIR / "step-04/run-meta.json")
    cont_meta = _json(CONT_DIR / "step-04/run-meta.json")
    gpt03 = _artifact_payload(GPT_STEP03_ARTIFACT)
    gpt04 = _artifact_payload(GPT_STEP04_ARTIFACT)
    step03_prompt = _text(OUTPUT_DIR / "dsv4-step03-step4-prompt.md")
    step04_raw = _text(RUNS_DIR / "step-04/raw.md")
    cont_raw = _text(CONT_DIR / "step-04/raw.md")
    step04_events = _events_summary(RUNS_DIR / "step-04/events.jsonl")
    cont_events = _events_summary(CONT_DIR / "step-04/events.jsonl")
    step04_searches = int(step04_events["tool_counts"].get("web_search") or 0)
    cont_searches = int(cont_events["tool_counts"].get("web_search") or 0)
    costs = {
        "step03": _usage_cost(step03_meta, serper_searches=0),
        "step04_failed": _usage_cost(step04_meta, serper_searches=step04_searches),
        "step04_continuation_failed": _usage_cost(cont_meta, serper_searches=cont_searches),
    }
    costs["total_promo_usd"] = sum(float(row["promo_total_usd"]) for row in costs.values() if isinstance(row, dict))
    costs["total_list_usd"] = sum(float(row["list_total_usd"]) for row in costs.values() if isinstance(row, dict))
    validation = {
        "pass": False,
        "scope": ["01 already tested", "03", "04"],
        "step06_run": False,
        "step03": {
            "status": "pass",
            "elapsed_seconds": step03_meta.get("elapsed_seconds"),
            "event_count": step03_meta.get("event_count"),
            "step4_prompt_chars": len(step03_prompt),
            "summary_chars": len(_text(OUTPUT_DIR / "dsv4-step03-summary.md")),
            "content_chars": len(_text(OUTPUT_DIR / "dsv4-step03-content.md")),
            "gpt_summary_chars": len(str(gpt03.get("bounded_summary") or "")),
            "gpt_content_chars": len(str(gpt03.get("content") or "")),
            "tool_counts": step03_meta.get("tool_counts") or {},
        },
        "step04": {
            "status": "fail",
            "failure": "DeerFlow DSV4 gathered research but final answer was only a status sentence, not tagged SUMMARY/CONTENT.",
            "raw_output": step04_raw.strip(),
            "raw_chars": len(step04_raw),
            "elapsed_seconds": step04_meta.get("elapsed_seconds"),
            "event_count": step04_meta.get("event_count"),
            "tool_counts": step04_meta.get("tool_counts") or {},
            "events_summary": step04_events,
            "gpt_summary_chars": len(str(gpt04.get("bounded_summary") or "")),
            "gpt_content_chars": len(str(gpt04.get("content") or "")),
            "gpt_raw_doc_chars": len(_text(GPT_STEP04_DOC)),
        },
        "step04_continuation": {
            "status": "fail",
            "failure": "Same-thread continuation returned empty raw output after tool/clarification activity.",
            "raw_output": cont_raw.strip(),
            "raw_chars": len(cont_raw),
            "elapsed_seconds": cont_meta.get("elapsed_seconds"),
            "event_count": cont_meta.get("event_count"),
            "tool_counts": cont_meta.get("tool_counts") or {},
            "events_summary": cont_events,
        },
        "costs": costs,
    }
    (OUTPUT_DIR / "dsv4-foundational-03-04-validation.json").write_text(
        json.dumps(validation, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )

    comparison = f"""# DSV4 vs GPT Foundational Steps 03/04 Comparison

## Result

Step 03: **PASS**. DSV4 produced a valid tailored Step 04 prompt.

Step 04: **FAIL**. DSV4 used the research harness heavily, then returned only: `{step04_raw.strip()}`. Same-thread continuation also failed, producing empty output.

Do **not** default Step 04 to DSV4/DeerFlow yet.

## Scope

- Step 01 was already tested in `proof_pack/deerflow-step01-1to1-2026-05-21`.
- This run covered only Step 03 and Step 04.
- Step 06 was not run.

## Metrics

| Metric | GPT Step 03 | DSV4 Step 03 | GPT Step 04 | DSV4 Step 04 |
|---|---:|---:|---:|---:|
| Summary chars | {len(str(gpt03.get("bounded_summary") or ""))} | {len(_text(OUTPUT_DIR / "dsv4-step03-summary.md"))} | {len(str(gpt04.get("bounded_summary") or ""))} | 0 |
| Content chars | {len(str(gpt03.get("content") or ""))} | {len(_text(OUTPUT_DIR / "dsv4-step03-content.md"))} | {len(str(gpt04.get("content") or ""))} | {len(step04_raw)} |
| Elapsed seconds | 91.69 | {step03_meta.get("elapsed_seconds")} | 396.83 | {step04_meta.get("elapsed_seconds")} |
| Web searches | 0 | 0 | unknown | {step04_searches} |
| Web fetches | 0 | 0 | unknown | {int(step04_events["tool_counts"].get("web_fetch") or 0)} |
| Input tokens | unknown | {costs["step03"]["input_tokens"]} | unknown | {costs["step04_failed"]["input_tokens"]} |
| Output tokens | unknown | {costs["step03"]["output_tokens"]} | unknown | {costs["step04_failed"]["output_tokens"]} |

## Cost

- Step 03 promo cost: ${costs["step03"]["promo_total_usd"]:.4f}
- Failed Step 04 promo cost: ${costs["step04_failed"]["promo_total_usd"]:.4f}
- Failed Step 04 continuation promo cost: ${costs["step04_continuation_failed"]["promo_total_usd"]:.4f}
- Total promo cost for this test: ${costs["total_promo_usd"]:.4f}
- Post-promo list equivalent: ${costs["total_list_usd"]:.4f}

## Comparison Read

Step 03 is safe to keep testing. It is slower than GPT but usable, and produced a much larger tailored Step 04 prompt.

Step 04 is not safe to default. The harness did real research, but the final-output transition failed. The failure mode is actionable: force a two-phase Step 04 harness where research evidence is persisted, then a separate no-tool synthesis pass writes the tagged report from captured evidence.

GPT production Step 04 also looks brittle in the persisted artifact: the stored content is only {len(str(gpt04.get("content") or ""))} chars while the bounded summary is {len(str(gpt04.get("bounded_summary") or ""))} chars. That means Step 04 needs output-contract repair regardless of provider.
"""
    (OUTPUT_DIR / "dsv4-vs-gpt-foundational-03-04-comparison.md").write_text(comparison, encoding="utf-8")
    print(json.dumps(validation, indent=2, ensure_ascii=False))
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
