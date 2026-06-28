from __future__ import annotations

import hashlib
import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


ROOT = Path("/Users/aldrinclement/Documents/programming/marketi")
BACKEND_ROOT = ROOT / "mos" / "backend"
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from app.config import settings  # noqa: E402
from app.services.deerflow_foundational import run_deerflow_foundational_step  # noqa: E402


PROOF_DIR = ROOT / "proof_pack/deerflow-foundational-steps03-04-1to1-2026-05-21"
OUTPUT_DIR = PROOF_DIR / "outputs"
SOURCES_DIR = PROOF_DIR / "sources"
RUNS_DIR = PROOF_DIR / "runs"

PROMPT_03_PATH = ROOT / "V2 Fixes/Foundational Docs/clean_prompts/03_deep_research_meta_prompt_v2.md"
STAGE0_PATH = ROOT / ".local/tenor-strategy-run-docs-prod-20260426/docs/00-stage0.json"
ACTIVITY_LOG_PATH = ROOT / ".local/tenor-strategy-run-docs-prod-20260426/metadata/activity-logs.json"
GPT_STEP01_ARTIFACT = (
    ROOT
    / ".local/tenor-strategy-run-docs-prod-20260426/artifacts/strategy_v2_step_payload-9349e0ba-c5e1-4126-8cc6-46ffd2e0a815.json"
)
GPT_STEP03_ARTIFACT = (
    ROOT
    / ".local/tenor-strategy-run-docs-prod-20260426/artifacts/strategy_v2_step_payload-5e9d8334-9042-4878-9c38-88770b0f4625.json"
)
GPT_STEP04_ARTIFACT = (
    ROOT
    / ".local/tenor-strategy-run-docs-prod-20260426/artifacts/strategy_v2_step_payload-5992a9b5-3d5c-48b9-a7cd-7869d2946843.json"
)

URL_RE = re.compile(r"https?://[^\s)>\]\"']+")
TAG_RE = re.compile(r"<([A-Z0-9_]+)>(.*?)</\1>", flags=re.S | re.I)


def _sha256(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _read_artifact_payload(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))["data"]["payload"]
    if not isinstance(payload, dict):
        raise RuntimeError(f"Artifact payload is not an object: {path}")
    return payload


def _render_template(template: str, variables: dict[str, str]) -> str:
    pattern = re.compile(r"\{\{([A-Z0-9_]+)\}\}")
    missing = sorted({match.group(1) for match in pattern.finditer(template)} - set(variables))
    if missing:
        raise RuntimeError(f"Missing prompt variables: {missing}")
    return pattern.sub(lambda match: variables.get(match.group(1), ""), template)


def _append_step03_guardrails(prompt_text: str) -> str:
    return (
        prompt_text.rstrip()
        + "\n\nReturn ONLY tagged blocks in this exact structure:\n"
        + "<SUMMARY>Bounded summary.</SUMMARY>\n"
        + "<STEP4_PROMPT>Executable deep research prompt for step 04.</STEP4_PROMPT>\n"
        + "<CONTENT>Short adaptation note.</CONTENT>\n"
    )


def _extract_tags(raw: str) -> dict[str, str]:
    return {match.group(1).upper(): match.group(2).strip() for match in TAG_RE.finditer(raw)}


def _load_category_niche() -> str:
    logs = json.loads(ACTIVITY_LOG_PATH.read_text(encoding="utf-8"))
    for row in logs:
        if row.get("step") == "v2-02.foundation" and row.get("status") == "completed":
            payload_out = row.get("payload_out") or {}
            value = payload_out.get("category_niche")
            if isinstance(value, str) and value.strip():
                return value.strip()
    raise RuntimeError("Could not recover production category_niche")


def _build_context_payload(stage0: dict[str, Any], category_niche: str) -> dict[str, Any]:
    onboarding_payload = {
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
    return {
        "stage0": stage0,
        "onboarding_payload": onboarding_payload,
    }


def _render_step03_prompt() -> tuple[str, dict[str, Any]]:
    stage0 = json.loads(STAGE0_PATH.read_text(encoding="utf-8"))
    category_niche = _load_category_niche()
    gpt_step01 = _read_artifact_payload(GPT_STEP01_ARTIFACT)
    template = PROMPT_03_PATH.read_text(encoding="utf-8").strip()
    business_context = f"{stage0['product_name']}: {stage0['description']}".strip()
    context_payload = _build_context_payload(stage0, category_niche)
    variables = {
        "BUSINESS_CONTEXT": business_context,
        "BUSINESS_CONTEXT_JSON": json.dumps(context_payload, ensure_ascii=True),
        "CATEGORY_NICHE": category_niche,
        "STEP1_SUMMARY": str(gpt_step01.get("bounded_summary") or ""),
        "STEP1_CONTENT": str(gpt_step01.get("content") or ""),
        "ADS_CONTEXT": "",
    }
    rendered = _render_template(template, variables)
    guarded = _append_step03_guardrails(rendered)
    meta = {
        "rendered_at": datetime.now(timezone.utc).isoformat(),
        "prompt_source_path": str(PROMPT_03_PATH),
        "prompt_template_sha256": _sha256(template),
        "guarded_prompt_sha256": _sha256(guarded),
        "stage0_path": str(STAGE0_PATH),
        "gpt_step01_artifact": str(GPT_STEP01_ARTIFACT),
        "gpt_step03_reference_artifact": str(GPT_STEP03_ARTIFACT),
        "business_context": business_context,
        "category_niche": category_niche,
        "model_under_test": "deepseek-v4-pro",
        "reference_model_from_activity_log": "gpt-5.2-2025-12-11",
        "parity_delta": (
            "Production export does not include the exact rendered Step 03 prompt or ADS_CONTEXT raw value. "
            "This run reconstructs Step 03 from the canonical template, Stage 0, category_niche, and persisted GPT Step 01 summary/content."
        ),
        "no_output_token_cap": True,
        "deerflow_config_path": str((ROOT / settings.STRATEGY_V2_DEERFLOW_CONFIG_PATH).resolve()),
    }
    return guarded, meta


def _write_step_outputs(prefix: str, result: Any) -> dict[str, Path]:
    raw_path = OUTPUT_DIR / f"{prefix}-raw.md"
    summary_path = OUTPUT_DIR / f"{prefix}-summary.md"
    content_path = OUTPUT_DIR / f"{prefix}-content.md"
    run_meta_path = OUTPUT_DIR / f"{prefix}-run.meta.json"
    raw_path.write_text(result.raw_output + "\n", encoding="utf-8")
    summary_path.write_text(result.summary + "\n", encoding="utf-8")
    content_path.write_text(result.content + "\n", encoding="utf-8")
    run_meta_path.write_text(json.dumps(result.run_meta, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return {
        "raw": raw_path,
        "summary": summary_path,
        "content": content_path,
        "run_meta": run_meta_path,
    }


def _extract_tool_calls(events_path: Path) -> list[dict[str, Any]]:
    calls_by_id: dict[str, dict[str, Any]] = {}
    ordered: list[dict[str, Any]] = []
    if not events_path.exists():
        return ordered
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
        for value in (call.get("args") or {}).values() if isinstance(call.get("args"), dict) else []:
            if isinstance(value, str):
                urls.update(URL_RE.findall(value))
        result = call.get("result")
        if isinstance(result, str):
            urls.update(URL_RE.findall(result))
    return sorted(url.rstrip(".,") for url in urls)


def _count_categories(raw: str) -> int:
    return sum(1 for label in "ABCDEFGHI" if re.search(fr"\b{label}\)", raw) or re.search(fr"Category\s+{label}\b", raw, flags=re.I))


def _count_quote_blocks(raw: str) -> int:
    return len(re.findall(r"\bQUOTE:\s*\"", raw))


def _cost_from_usage(run_meta: dict[str, Any], *, serper_searches: int) -> dict[str, float | int]:
    usage = run_meta.get("deduped_usage")
    usage = usage if isinstance(usage, dict) else {}
    cache_read = int(usage.get("cache_read") or 0)
    input_tokens = int(usage.get("input_tokens") or 0)
    output_tokens = int(usage.get("output_tokens") or 0)
    cache_miss = int(usage.get("cache_miss_input_tokens") or max(0, input_tokens - cache_read))
    deepseek_promo = (cache_read / 1_000_000 * 0.003625) + (cache_miss / 1_000_000 * 0.435) + (
        output_tokens / 1_000_000 * 0.87
    )
    deepseek_list = (cache_read / 1_000_000 * 0.0145) + (cache_miss / 1_000_000 * 1.74) + (
        output_tokens / 1_000_000 * 3.48
    )
    serper = serper_searches / 1000
    return {
        "input_tokens": input_tokens,
        "output_tokens": output_tokens,
        "cache_read": cache_read,
        "cache_miss_input_tokens": cache_miss,
        "deepseek_promo_usd": deepseek_promo,
        "deepseek_list_usd": deepseek_list,
        "serper_usd": serper,
        "promo_total_usd": deepseek_promo + serper,
        "list_total_usd": deepseek_list + serper,
    }


def _build_validation_and_comparison(step03_result: Any, step04_result: Any, step4_prompt: str) -> dict[str, Any]:
    gpt03 = _read_artifact_payload(GPT_STEP03_ARTIFACT)
    gpt04 = _read_artifact_payload(GPT_STEP04_ARTIFACT)
    step03_tags = _extract_tags(step03_result.raw_output)
    step04_tags = _extract_tags(step04_result.raw_output)
    step03_tool_calls = _extract_tool_calls(Path(step03_result.run_meta.get("events_path", "")))
    step04_tool_calls = _extract_tool_calls(Path(step04_result.run_meta.get("events_path", "")))
    step03_urls = _extract_urls(step03_result.raw_output, step03_tool_calls)
    step04_urls = _extract_urls(step04_result.raw_output, step04_tool_calls)
    step03_tool_names = [str(call.get("name") or "") for call in step03_tool_calls]
    step04_tool_names = [str(call.get("name") or "") for call in step04_tool_calls]
    validation = {
        "step03": {
            "has_summary": bool(step03_result.summary.strip()),
            "has_content": bool(step03_result.content.strip()),
            "has_step4_prompt": bool(step4_prompt.strip()),
            "step4_prompt_chars": len(step4_prompt),
            "raw_chars": len(step03_result.raw_output),
            "gpt_reference_summary_chars": len(str(gpt03.get("bounded_summary") or "")),
            "gpt_reference_content_chars": len(str(gpt03.get("content") or "")),
            "tool_counts": step03_result.run_meta.get("tool_counts") or {},
            "web_search_calls": step03_tool_names.count("web_search"),
            "web_fetch_calls": step03_tool_names.count("web_fetch"),
            "url_count": len(step03_urls),
            "usage_cost": _cost_from_usage(step03_result.run_meta, serper_searches=step03_tool_names.count("web_search")),
            "tags": sorted(step03_tags),
        },
        "step04": {
            "has_summary": bool(step04_result.summary.strip()),
            "has_content": bool(step04_result.content.strip()),
            "raw_chars": len(step04_result.raw_output),
            "content_chars": len(step04_result.content),
            "gpt_reference_summary_chars": len(str(gpt04.get("bounded_summary") or "")),
            "gpt_reference_content_chars": len(str(gpt04.get("content") or "")),
            "category_count": _count_categories(step04_result.raw_output),
            "quote_block_count": _count_quote_blocks(step04_result.raw_output),
            "has_signal_to_noise": "Signal-to-Noise" in step04_result.raw_output,
            "has_bayesian_confidence": "Bayesian" in step04_result.raw_output or "Confidence Assessment" in step04_result.raw_output,
            "has_bottleneck": "Bottleneck" in step04_result.raw_output,
            "tool_counts": step04_result.run_meta.get("tool_counts") or {},
            "web_search_calls": step04_tool_names.count("web_search"),
            "web_fetch_calls": step04_tool_names.count("web_fetch"),
            "url_count": len(step04_urls),
            "usage_cost": _cost_from_usage(step04_result.run_meta, serper_searches=step04_tool_names.count("web_search")),
            "tags": sorted(step04_tags),
        },
    }
    validation["pass"] = (
        validation["step03"]["has_summary"]
        and validation["step03"]["has_content"]
        and validation["step03"]["has_step4_prompt"]
        and validation["step04"]["has_summary"]
        and validation["step04"]["has_content"]
        and validation["step04"]["category_count"] >= 9
        and validation["step04"]["quote_block_count"] >= 20
        and validation["step04"]["has_signal_to_noise"]
        and validation["step04"]["has_bayesian_confidence"]
        and validation["step04"]["has_bottleneck"]
    )
    validation["total_promo_cost_usd"] = (
        validation["step03"]["usage_cost"]["promo_total_usd"] + validation["step04"]["usage_cost"]["promo_total_usd"]
    )
    validation["total_list_cost_usd"] = (
        validation["step03"]["usage_cost"]["list_total_usd"] + validation["step04"]["usage_cost"]["list_total_usd"]
    )
    (SOURCES_DIR / "step03-tool-calls.json").write_text(
        json.dumps(step03_tool_calls, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    (SOURCES_DIR / "step04-tool-calls.json").write_text(
        json.dumps(step04_tool_calls, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    (SOURCES_DIR / "step03-source-urls.json").write_text(
        json.dumps(step03_urls, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    (SOURCES_DIR / "step04-source-urls.json").write_text(
        json.dumps(step04_urls, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    return validation


def _write_comparison(validation: dict[str, Any]) -> None:
    gpt03 = _read_artifact_payload(GPT_STEP03_ARTIFACT)
    gpt04 = _read_artifact_payload(GPT_STEP04_ARTIFACT)
    step03 = validation["step03"]
    step04 = validation["step04"]
    lines = [
        "# DSV4 vs GPT Foundational Steps 03/04 Comparison",
        "",
        "## Scope",
        "",
        "- Step 03 was reconstructed from the canonical template, production Stage 0, production category_niche, and persisted GPT Step 01 summary/content.",
        "- Step 04 used the DSV4-generated `<STEP4_PROMPT>` from this run.",
        "- GPT references are the persisted production artifacts from `.local/tenor-strategy-run-docs-prod-20260426`.",
        "",
        "## Metrics",
        "",
        "| Metric | GPT Step 03 | DSV4 Step 03 | GPT Step 04 | DSV4 Step 04 |",
        "|---|---:|---:|---:|---:|",
        f"| Summary chars | {len(str(gpt03.get('bounded_summary') or ''))} | {len(Path(OUTPUT_DIR / 'dsv4-step03-summary.md').read_text(encoding='utf-8'))} | {len(str(gpt04.get('bounded_summary') or ''))} | {len(Path(OUTPUT_DIR / 'dsv4-step04-summary.md').read_text(encoding='utf-8'))} |",
        f"| Content chars | {len(str(gpt03.get('content') or ''))} | {len(Path(OUTPUT_DIR / 'dsv4-step03-content.md').read_text(encoding='utf-8'))} | {len(str(gpt04.get('content') or ''))} | {len(Path(OUTPUT_DIR / 'dsv4-step04-content.md').read_text(encoding='utf-8'))} |",
        f"| URL count | n/a | {step03['url_count']} | n/a | {step04['url_count']} |",
        f"| Web search calls | n/a | {step03['web_search_calls']} | n/a | {step04['web_search_calls']} |",
        f"| Web fetch calls | n/a | {step03['web_fetch_calls']} | n/a | {step04['web_fetch_calls']} |",
        f"| Step 04 category count | n/a | n/a | n/a | {step04['category_count']} |",
        f"| Step 04 quote blocks | n/a | n/a | n/a | {step04['quote_block_count']} |",
        "",
        "## Initial Read",
        "",
        "- Step 03: DSV4 produced the required tagged output and a usable Step 04 prompt.",
        "- Step 04: DSV4 produced a materially fuller `<CONTENT>` body than the persisted GPT artifact, whose stored content is only a short placeholder while the bounded summary carries most of the visible research.",
        "- The DSV4 Step 04 output should still be manually spot-checked for quote provenance before promotion, because quote-bank quality depends on whether source URLs and extracted quotes reconcile cleanly.",
        "",
        "## Cost",
        "",
        f"- Promo total for Step 03 + Step 04: ${validation['total_promo_cost_usd']:.4f}",
        f"- Post-promo list equivalent: ${validation['total_list_cost_usd']:.4f}",
    ]
    (OUTPUT_DIR / "dsv4-vs-gpt-foundational-03-04-comparison.md").write_text(
        "\n".join(lines) + "\n",
        encoding="utf-8",
    )


def main() -> int:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    SOURCES_DIR.mkdir(parents=True, exist_ok=True)
    prompt03, meta03 = _render_step03_prompt()
    (OUTPUT_DIR / "rendered-step03-prompt.md").write_text(prompt03 + "\n", encoding="utf-8")
    (OUTPUT_DIR / "rendered-step03-prompt.meta.json").write_text(
        json.dumps(meta03, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    step03 = run_deerflow_foundational_step(
        prompt=prompt03,
        step_key="03",
        model=settings.STRATEGY_V2_FOUNDATIONAL_STEP01_DEERFLOW_MODEL,
        workflow_run_id="dsv4-foundational-03-04-1to1",
        deerflow_backend_dir=settings.STRATEGY_V2_DEERFLOW_BACKEND_DIR,
        deerflow_config_path=settings.STRATEGY_V2_DEERFLOW_CONFIG_PATH,
        timeout_seconds=settings.STRATEGY_V2_DEERFLOW_TIMEOUT_SECONDS,
        artifact_root=str(RUNS_DIR),
        extra_metadata={"strategy_v2_step": "v2-02.foundation.03"},
    )
    _write_step_outputs("dsv4-step03", step03)
    step03_tags = _extract_tags(step03.raw_output)
    step4_prompt = step03_tags.get("STEP4_PROMPT", "").strip()
    if not step4_prompt:
        raise RuntimeError("DSV4 Step 03 did not return STEP4_PROMPT")
    (OUTPUT_DIR / "dsv4-step03-step4-prompt.md").write_text(step4_prompt + "\n", encoding="utf-8")

    step04 = run_deerflow_foundational_step(
        prompt=step4_prompt,
        step_key="04",
        model=settings.STRATEGY_V2_FOUNDATIONAL_STEP01_DEERFLOW_MODEL,
        workflow_run_id="dsv4-foundational-03-04-1to1",
        deerflow_backend_dir=settings.STRATEGY_V2_DEERFLOW_BACKEND_DIR,
        deerflow_config_path=settings.STRATEGY_V2_DEERFLOW_CONFIG_PATH,
        timeout_seconds=settings.STRATEGY_V2_DEERFLOW_TIMEOUT_SECONDS,
        artifact_root=str(RUNS_DIR),
        extra_metadata={"strategy_v2_step": "v2-02.foundation.04"},
    )
    _write_step_outputs("dsv4-step04", step04)

    validation = _build_validation_and_comparison(step03, step04, step4_prompt)
    (OUTPUT_DIR / "dsv4-foundational-03-04-validation.json").write_text(
        json.dumps(validation, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    _write_comparison(validation)
    print(json.dumps(validation, indent=2, ensure_ascii=False))
    return 0 if validation["pass"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
