from __future__ import annotations

import json
import os
import re
import subprocess
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any


class DeerFlowFoundationalError(RuntimeError):
    """Raised when the DeerFlow foundational sidecar cannot complete a step."""


@dataclass(frozen=True)
class DeerFlowFoundationalResult:
    summary: str
    content: str
    handoff: dict[str, Any]
    raw_output: str
    run_meta: dict[str, Any]


_REPO_ROOT = Path(__file__).resolve().parents[4]
_BACKEND_ROOT = _REPO_ROOT / "mos" / "backend"
_RUNNER_PATH = _BACKEND_ROOT / "scripts" / "run_deerflow_foundational_step.py"
_DEFAULT_ARTIFACT_ROOT = _BACKEND_ROOT / ".tmp" / "deerflow-foundational"
_REQUIRED_ENV = ("DEEPSEEK_API_KEY", "SERPER_API_KEY", "JINA_API_KEY")


def _resolve_repo_path(value: str | os.PathLike[str]) -> Path:
    path = Path(value).expanduser()
    if path.is_absolute():
        return path
    return (_REPO_ROOT / path).resolve()


def _safe_name(value: str, *, fallback: str) -> str:
    cleaned = re.sub(r"[^a-zA-Z0-9._-]+", "-", value.strip()).strip(".-")
    return cleaned[:96] or fallback


def _load_env_file(path: Path) -> dict[str, str]:
    if not path.exists():
        return {}
    loaded: dict[str, str] = {}
    for raw_line in path.read_text(encoding="utf-8", errors="replace").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        if line.startswith("export "):
            line = line[len("export ") :].strip()
        if "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        if not key:
            continue
        value = value.strip()
        if (value.startswith('"') and value.endswith('"')) or (
            value.startswith("'") and value.endswith("'")
        ):
            value = value[1:-1]
        loaded[key] = value
    return loaded


def _build_subprocess_env(deerflow_backend_dir: Path) -> dict[str, str]:
    env = dict(os.environ)
    for key, value in _load_env_file(deerflow_backend_dir / ".env").items():
        if not env.get(key):
            env[key] = value
    missing = [key for key in _REQUIRED_ENV if not env.get(key)]
    if missing:
        raise DeerFlowFoundationalError(
            "DeerFlow foundational sidecar requires missing env vars: "
            f"{', '.join(missing)}. Set them in the backend environment or DeerFlow sidecar .env."
        )
    return env


def _resolve_sidecar_python(deerflow_backend_dir: Path) -> Path:
    if os.name == "nt":
        python_path = deerflow_backend_dir / ".venv" / "Scripts" / "python.exe"
    else:
        python_path = deerflow_backend_dir / ".venv" / "bin" / "python"
    if not python_path.exists():
        raise DeerFlowFoundationalError(
            f"DeerFlow sidecar Python is missing: {python_path}. "
            "Create the sidecar virtualenv before running foundational research."
        )
    return python_path


def _tail(value: str, *, max_chars: int = 4000) -> str:
    if len(value) <= max_chars:
        return value
    return value[-max_chars:]


def run_deerflow_foundational_step(
    *,
    prompt: str,
    step_key: str,
    model: str,
    workflow_run_id: str,
    deerflow_backend_dir: str,
    deerflow_config_path: str,
    timeout_seconds: int,
    artifact_root: str | None = None,
    extra_metadata: Mapping[str, Any] | None = None,
    mode: str | None = None,
) -> DeerFlowFoundationalResult:
    cleaned_prompt = prompt.strip()
    if not cleaned_prompt:
        raise DeerFlowFoundationalError("DeerFlow foundational step prompt is empty.")

    backend_dir = _resolve_repo_path(deerflow_backend_dir)
    config_path = _resolve_repo_path(deerflow_config_path)
    if not backend_dir.exists():
        raise DeerFlowFoundationalError(
            f"DeerFlow backend directory is missing: {backend_dir}. "
            "Set STRATEGY_V2_DEERFLOW_BACKEND_DIR or install the sidecar."
        )
    if not config_path.exists():
        raise DeerFlowFoundationalError(
            f"DeerFlow config file is missing: {config_path}. "
            "Set STRATEGY_V2_DEERFLOW_CONFIG_PATH."
        )
    if not _RUNNER_PATH.exists():
        raise DeerFlowFoundationalError(f"DeerFlow runner is missing: {_RUNNER_PATH}.")

    root = _resolve_repo_path(artifact_root) if artifact_root else _DEFAULT_ARTIFACT_ROOT
    workflow_component = _safe_name(workflow_run_id, fallback="workflow")
    step_component = _safe_name(step_key, fallback="step")
    run_dir = root / workflow_component / f"step-{step_component}"
    run_dir.mkdir(parents=True, exist_ok=True)
    input_path = run_dir / "input.json"
    output_path = run_dir / "output.json"
    input_payload = {
        "prompt": cleaned_prompt,
        "step_key": step_key,
        "model": model,
        "workflow_run_id": workflow_run_id,
        "thread_id": f"strategy-v2-foundation-{workflow_component}-{step_key}",
        "artifact_dir": str(run_dir),
        "metadata": dict(extra_metadata or {}),
    }
    if mode:
        input_payload["mode"] = mode
    input_path.write_text(
        json.dumps(input_payload, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )

    env = _build_subprocess_env(backend_dir)
    sidecar_python = _resolve_sidecar_python(backend_dir)
    command = [
        str(sidecar_python),
        str(_RUNNER_PATH),
        "--input",
        str(input_path),
        "--output",
        str(output_path),
        "--config",
        str(config_path),
    ]
    try:
        completed = subprocess.run(
            command,
            cwd=str(backend_dir),
            env=env,
            check=False,
            text=True,
            capture_output=True,
            timeout=timeout_seconds,
        )
    except subprocess.TimeoutExpired as exc:
        raise DeerFlowFoundationalError(
            f"DeerFlow foundational Step {step_key} timed out after {timeout_seconds}s."
        ) from exc
    if completed.returncode != 0:
        output_error = ""
        if output_path.exists():
            try:
                failed_payload = json.loads(output_path.read_text(encoding="utf-8"))
                output_error = f" output_error={failed_payload.get('error')!r}"
            except json.JSONDecodeError:
                output_error = ""
        raise DeerFlowFoundationalError(
            f"DeerFlow foundational Step {step_key} failed with exit code {completed.returncode}. "
            f"stdout_tail={_tail(completed.stdout)!r} "
            f"stderr_tail={_tail(completed.stderr)!r}{output_error}"
        )
    if not output_path.exists():
        raise DeerFlowFoundationalError(
            f"DeerFlow foundational Step {step_key} did not write output JSON: {output_path}."
        )

    try:
        payload = json.loads(output_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise DeerFlowFoundationalError(
            f"DeerFlow foundational Step {step_key} output JSON is invalid: {output_path}."
        ) from exc
    if payload.get("status") != "completed":
        raise DeerFlowFoundationalError(
            f"DeerFlow foundational Step {step_key} did not complete: {payload.get('status')!r}. "
            f"error={payload.get('error')!r}"
        )
    summary = str(payload.get("summary") or "").strip()
    content = str(payload.get("content") or "").strip()
    if not summary or not content:
        raise DeerFlowFoundationalError(
            f"DeerFlow foundational Step {step_key} returned empty summary/content."
        )
    return DeerFlowFoundationalResult(
        summary=summary,
        content=content,
        handoff=dict(payload.get("handoff") or {}),
        raw_output=str(payload.get("raw_output") or "").strip(),
        run_meta=dict(payload.get("run_meta") or {}),
    )


def run_deerflow_foundational_step04(
    *,
    prompt: str,
    model: str,
    workflow_run_id: str,
    deerflow_backend_dir: str,
    deerflow_config_path: str,
    timeout_seconds: int,
    artifact_root: str | None = None,
    extra_metadata: Mapping[str, Any] | None = None,
) -> DeerFlowFoundationalResult:
    """Run foundational Step 04 through the DSV4 research+synthesis sidecar path."""
    return run_deerflow_foundational_step(
        prompt=prompt,
        step_key="04",
        model=model,
        workflow_run_id=workflow_run_id,
        deerflow_backend_dir=deerflow_backend_dir,
        deerflow_config_path=deerflow_config_path,
        timeout_seconds=timeout_seconds,
        artifact_root=artifact_root,
        extra_metadata=extra_metadata,
        mode="step04_dsv4_research_synthesis",
    )
