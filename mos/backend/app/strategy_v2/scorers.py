from __future__ import annotations

from contextlib import redirect_stdout
import io
import importlib.util
import os
import re
import tempfile
import time
from pathlib import Path
from threading import Lock
from types import ModuleType
from typing import Callable, cast

from app.strategy_v2.errors import StrategyV2ScorerError


_MODULE_CACHE: dict[str, ModuleType] = {}
_MODULE_CACHE_LOCK = Lock()
_HEADLINE_QA_TRANSIENT_RETRY_ATTEMPTS = max(
    1,
    int(os.getenv("STRATEGY_V2_HEADLINE_QA_TRANSIENT_RETRY_ATTEMPTS", "6")),
)
_HEADLINE_QA_TRANSIENT_RETRY_BASE_SECONDS = max(
    0.0,
    float(os.getenv("STRATEGY_V2_HEADLINE_QA_TRANSIENT_RETRY_BASE_SECONDS", "3.0")),
)
_HEADLINE_QA_REQUEST_ID_RE = re.compile(r"\breq_[A-Za-z0-9]+\b")
_HEADLINE_QA_CALL_TIMEOUT_SECONDS = max(
    1.0,
    float(os.getenv("STRATEGY_V2_HEADLINE_QA_CALL_TIMEOUT_SECONDS", "90")),
)
_HEADLINE_QA_CALL_MAX_RETRIES = max(
    0,
    int(os.getenv("STRATEGY_V2_HEADLINE_QA_CALL_MAX_RETRIES", "2")),
)


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[4]


def _resolve_single_v2_file(pattern: str) -> Path:
    base_dir = _repo_root() / "V2 Fixes"
    matches = sorted(base_dir.glob(pattern))
    if len(matches) != 1:
        raise StrategyV2ScorerError(
            f"Expected exactly one scorer file for pattern '{pattern}', found {len(matches)}."
        )
    target = matches[0]
    if not target.exists():
        raise StrategyV2ScorerError(f"Scorer file does not exist: {target}")
    return target


def _load_module(module_key: str, pattern: str) -> ModuleType:
    with _MODULE_CACHE_LOCK:
        cached = _MODULE_CACHE.get(module_key)
        if cached is not None:
            return cached

        file_path = _resolve_single_v2_file(pattern)
        spec = importlib.util.spec_from_file_location(f"strategy_v2_ext_{module_key}", file_path)
        if spec is None or spec.loader is None:
            raise StrategyV2ScorerError(f"Failed to create module spec for scorer file: {file_path}")

        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        _MODULE_CACHE[module_key] = module
        return module


def _get_callable(module: ModuleType, function_name: str) -> Callable[..., object]:
    candidate = getattr(module, function_name, None)
    if not callable(candidate):
        raise StrategyV2ScorerError(
            f"Scorer function '{function_name}' not found in module '{module.__name__}'."
        )
    return cast(Callable[..., object], candidate)


def _require_dict_result(result: object, scorer_name: str) -> dict[str, object]:
    if not isinstance(result, dict):
        raise StrategyV2ScorerError(
            f"Scorer '{scorer_name}' returned '{type(result).__name__}', expected dict."
        )
    return cast(dict[str, object], result)


def _safe_int(value: object) -> int:
    if isinstance(value, bool):
        return int(value)
    if isinstance(value, int):
        return value
    if isinstance(value, float):
        return int(value)
    if isinstance(value, str):
        cleaned = value.strip()
        if not cleaned:
            return 0
        try:
            return int(float(cleaned))
        except ValueError:
            return 0
    return 0


def _safe_float(value: object) -> float:
    if isinstance(value, bool):
        return float(int(value))
    if isinstance(value, (int, float)):
        return float(value)
    if isinstance(value, str):
        cleaned = value.strip()
        if not cleaned:
            return 0.0
        try:
            return float(cleaned)
        except ValueError:
            return 0.0
    return 0.0


def _unique_strings(value: object, *, limit: int = 25) -> list[str]:
    if not isinstance(value, list):
        return []
    cleaned: list[str] = []
    for item in value:
        if item is None:
            continue
        text = str(item).strip()
        if not text or text in cleaned:
            continue
        cleaned.append(text)
        if len(cleaned) >= limit:
            break
    return cleaned


def _collect_headline_qa_stdout_diagnostics(*, stdout_text: str) -> dict[str, object]:
    warning_lines = [
        line.strip()
        for line in stdout_text.splitlines()
        if "WARNING: LLM call failed:" in line
    ]
    overloaded_error_count = sum(
        1
        for line in warning_lines
        if "overloaded_error" in line.lower() or "error code: 529" in line.lower()
    )
    timeout_error_count = sum(
        1
        for line in warning_lines
        if "timed out" in line.lower() or "timeout" in line.lower()
    )
    diagnostics: dict[str, object] = {
        "warning_count": len(warning_lines),
        "overloaded_error_count": overloaded_error_count,
        "timeout_error_count": timeout_error_count,
    }
    request_ids: list[str] = []
    for match in _HEADLINE_QA_REQUEST_ID_RE.findall(stdout_text):
        if match not in request_ids:
            request_ids.append(match)
    if request_ids:
        diagnostics["request_ids"] = request_ids
    if warning_lines:
        diagnostics["warning_samples"] = warning_lines[:3]
    return diagnostics


def _is_headline_qa_transient_provider_failure(
    *,
    serialized: dict[str, object],
    diagnostics: dict[str, object],
) -> bool:
    status = str(serialized.get("status") or "").strip().upper()
    total_iterations = _safe_int(serialized.get("total_iterations"))
    overloaded_errors = _safe_int(diagnostics.get("overloaded_error_count"))
    timeout_errors = _safe_int(diagnostics.get("timeout_error_count"))
    return status != "PASS" and total_iterations <= 1 and (overloaded_errors > 0 or timeout_errors > 0)


def score_habitats(habitats: list[dict[str, object]]) -> dict[str, object]:
    module = _load_module(
        "voc_score_habitats",
        "VOC + Angle Engine (2-21-26)/scoring/score_habitats.py",
    )
    scorer = _get_callable(module, "score_all_habitats")
    return _require_dict_result(scorer(habitats), "score_all_habitats")


def score_videos(videos: list[dict[str, object]]) -> dict[str, object]:
    module = _load_module(
        "voc_score_videos",
        "VOC + Angle Engine (2-21-26)/scoring/score_virality.py",
    )
    scorer = _get_callable(module, "score_all_videos")
    return _require_dict_result(scorer(videos), "score_all_videos")


def score_voc_items(items: list[dict[str, object]]) -> dict[str, object]:
    module = _load_module(
        "voc_score_items",
        "VOC + Angle Engine (2-21-26)/scoring/score_voc.py",
    )
    scorer = _get_callable(module, "score_all_voc")
    return _require_dict_result(scorer(items), "score_all_voc")


def score_angles(angles: list[dict[str, object]], saturated_count: int) -> dict[str, object]:
    module = _load_module(
        "voc_score_angles",
        "VOC + Angle Engine (2-21-26)/scoring/score_angles.py",
    )
    scorer = _get_callable(module, "score_all_angles")
    return _require_dict_result(scorer(angles, saturated_count), "score_all_angles")


def calibration_consistency_checker(calibration: dict[str, object]) -> dict[str, object]:
    module = _load_module(
        "offer_scoring_tools",
        "Offer Agent */scoring-tools/scoring_tools.py",
    )
    scorer = _get_callable(module, "calibration_consistency_checker")
    return _require_dict_result(scorer(calibration), "calibration_consistency_checker")


def ump_ums_scorer(pairs: list[dict[str, object]]) -> dict[str, object]:
    module = _load_module(
        "offer_scoring_tools",
        "Offer Agent */scoring-tools/scoring_tools.py",
    )
    scorer = _get_callable(module, "ump_ums_scorer")
    return _require_dict_result(scorer(pairs), "ump_ums_scorer")


def hormozi_scorer(value_stack: dict[str, object]) -> dict[str, object]:
    module = _load_module(
        "offer_scoring_tools",
        "Offer Agent */scoring-tools/scoring_tools.py",
    )
    scorer = _get_callable(module, "hormozi_scorer")
    return _require_dict_result(scorer(value_stack), "hormozi_scorer")


def objection_coverage_calculator(mapping: dict[str, object]) -> dict[str, object]:
    module = _load_module(
        "offer_scoring_tools",
        "Offer Agent */scoring-tools/scoring_tools.py",
    )
    scorer = _get_callable(module, "objection_coverage_calculator")
    return _require_dict_result(scorer(mapping), "objection_coverage_calculator")


def novelty_calculator(elements: dict[str, object]) -> dict[str, object]:
    module = _load_module(
        "offer_scoring_tools",
        "Offer Agent */scoring-tools/scoring_tools.py",
    )
    scorer = _get_callable(module, "novelty_calculator")
    return _require_dict_result(scorer(elements), "novelty_calculator")


def composite_scorer(
    evaluation: dict[str, object],
    config: dict[str, object] | None = None,
) -> dict[str, object]:
    module = _load_module(
        "offer_scoring_tools",
        "Offer Agent */scoring-tools/scoring_tools.py",
    )
    scorer = _get_callable(module, "composite_scorer")
    result = scorer(evaluation, config)
    return _require_dict_result(result, "composite_scorer")


def score_headline(headline: str, page_type: str | None = None) -> dict[str, object]:
    module = _load_module(
        "copy_headline_scorer",
        "Copywriting Agent */03_scorers/headline_scorer_v2.py",
    )
    score_fn = _get_callable(module, "score_headline")
    composite_fn = _get_callable(module, "compute_composite")
    json_fn = _get_callable(module, "to_json")

    result_obj = score_fn(headline, page_type)
    result = _require_dict_result(result_obj, "headline_scorer_v2.score_headline")

    composite_obj = composite_fn(result)
    composite = _require_dict_result(composite_obj, "headline_scorer_v2.compute_composite")

    serialized_obj = json_fn(result, composite)
    serialized = _require_dict_result(serialized_obj, "headline_scorer_v2.to_json")

    return {
        "result": result,
        "composite": composite,
        "json": serialized,
    }


def build_page_data_from_body_text(body_text: str, page_type: str | None = None) -> dict[str, object]:
    module = _load_module(
        "copy_congruency_scorer",
        "Copywriting Agent */03_scorers/headline_body_congruency.py",
    )
    normalized_page_type = (page_type or "").strip().lower()

    if normalized_page_type in {"advertorial", "sales_page"}:
        loader_name = "load_advertorial_md" if normalized_page_type == "advertorial" else "load_sales_page_md"
        loader = _get_callable(module, loader_name)
        with tempfile.NamedTemporaryFile(mode="w", suffix=".md", delete=False, encoding="utf-8") as tmp_file:
            tmp_file.write(body_text)
            tmp_path = Path(tmp_file.name)
        try:
            return _require_dict_result(loader(str(tmp_path)), f"headline_body_congruency.{loader_name}")
        finally:
            tmp_path.unlink(missing_ok=True)

    builder = _get_callable(module, "build_listicle_data_from_body_text")
    return _require_dict_result(builder(body_text), "headline_body_congruency.build_listicle_data_from_body_text")


def score_congruency_extended(
    *,
    headline: str,
    page_data: dict[str, object],
    promise_contract: dict[str, object] | None,
) -> dict[str, object]:
    module = _load_module(
        "copy_congruency_scorer",
        "Copywriting Agent */03_scorers/headline_body_congruency.py",
    )
    score_fn = _get_callable(module, "score_congruency_extended")
    composite_fn = _get_callable(module, "compute_composite_extended")

    result_obj = score_fn(headline, page_data, promise_contract)
    result = _require_dict_result(result_obj, "headline_body_congruency.score_congruency_extended")

    composite_obj = composite_fn(result)
    composite = _require_dict_result(composite_obj, "headline_body_congruency.compute_composite_extended")

    return {
        "result": result,
        "composite": composite,
    }


def run_headline_qa_loop(
    *,
    headline: str,
    page_type: str | None,
    max_iterations: int,
    min_tier: str,
    api_key: str,
    model: str,
) -> dict[str, object]:
    cleaned_api_key = api_key.strip()
    if not cleaned_api_key:
        raise StrategyV2ScorerError(
            "Headline QA loop requires a non-empty API key; refusing dry-run fallback."
        )

    cleaned_model = model.strip()
    if not cleaned_model:
        raise StrategyV2ScorerError("Headline QA loop requires an explicit model value.")

    # Ensure external QA utility runs with resilient transient retry/timeouts.
    os.environ["STRATEGY_V2_HEADLINE_QA_CALL_TIMEOUT_SECONDS"] = str(_HEADLINE_QA_CALL_TIMEOUT_SECONDS)
    os.environ["STRATEGY_V2_HEADLINE_QA_CALL_MAX_RETRIES"] = str(_HEADLINE_QA_CALL_MAX_RETRIES)

    module = _load_module(
        "copy_headline_qa_loop",
        "Copywriting Agent */03_scorers/headline_qa_loop.py",
    )
    run_fn = _get_callable(module, "run_qa_loop")
    to_json_fn = _get_callable(module, "to_json")

    # External QA loop utility reads Anthropic base URL from env and treats
    # an empty string as a real endpoint, which breaks requests. Normalize
    # blank values to "unset" before invoking it.
    for env_key in ("ANTHROPIC_API_BASE_URL", "ANTHROPIC_BASE_URL"):
        env_value = os.getenv(env_key)
        if env_value is not None and not env_value.strip():
            os.environ.pop(env_key, None)
    qa_call_timeout_seconds = _safe_float(getattr(module, "LLM_CALL_TIMEOUT_SECONDS", 0.0))
    qa_call_max_retries = _safe_int(getattr(module, "LLM_CALL_MAX_RETRIES", 0))
    attempt_diagnostics: list[dict[str, object]] = []
    for attempt_index in range(1, _HEADLINE_QA_TRANSIENT_RETRY_ATTEMPTS + 1):
        stdout_buffer = io.StringIO()
        with redirect_stdout(stdout_buffer):
            raw_result = run_fn(
                headline,
                page_type,
                max_iterations,
                min_tier,
                cleaned_api_key,
                cleaned_model,
                False,
            )
        serialized = _require_dict_result(to_json_fn(raw_result), "headline_qa_loop.to_json")
        raw_payload = _require_dict_result(raw_result, "headline_qa_loop.run_qa_loop")

        attempt_diag = _collect_headline_qa_stdout_diagnostics(stdout_text=stdout_buffer.getvalue())
        metadata = serialized.get("metadata")
        metadata_request_ids = _unique_strings(metadata.get("request_ids"), limit=20) if isinstance(metadata, dict) else []
        if metadata_request_ids:
            existing_request_ids = _unique_strings(attempt_diag.get("request_ids"), limit=20)
            attempt_diag["request_ids"] = _unique_strings(existing_request_ids + metadata_request_ids, limit=40)
        attempt_diag["attempt_index"] = attempt_index
        attempt_diagnostics.append(attempt_diag)

        aggregate_diagnostics = {
            "attempt_count": attempt_index,
            "model": cleaned_model,
            "max_iterations": max_iterations,
            "min_tier": min_tier,
            "call_timeout_seconds": qa_call_timeout_seconds,
            "call_max_retries": qa_call_max_retries,
            "warning_count": sum(_safe_int(row.get("warning_count")) for row in attempt_diagnostics),
            "overloaded_error_count": sum(
                _safe_int(row.get("overloaded_error_count")) for row in attempt_diagnostics
            ),
            "timeout_error_count": sum(_safe_int(row.get("timeout_error_count")) for row in attempt_diagnostics),
            "attempts": list(attempt_diagnostics),
        }
        request_id_flat: list[str] = []
        for row in attempt_diagnostics:
            request_id_flat.extend(_unique_strings(row.get("request_ids"), limit=20))
        aggregate_request_ids = _unique_strings(request_id_flat, limit=80)
        if aggregate_request_ids:
            aggregate_diagnostics["request_ids"] = aggregate_request_ids

        should_retry = (
            attempt_index < _HEADLINE_QA_TRANSIENT_RETRY_ATTEMPTS
            and _is_headline_qa_transient_provider_failure(
                serialized=serialized,
                diagnostics=attempt_diag,
            )
        )
        if should_retry:
            delay_seconds = _HEADLINE_QA_TRANSIENT_RETRY_BASE_SECONDS * attempt_index
            if delay_seconds > 0:
                time.sleep(delay_seconds)
            continue

        return {
            "result": raw_payload,
            "json": serialized,
            "diagnostics": aggregate_diagnostics,
        }

    raise StrategyV2ScorerError("Headline QA loop exhausted transient retry attempts without a terminal result.")
