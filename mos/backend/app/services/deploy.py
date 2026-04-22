from __future__ import annotations

import asyncio
import base64
import copy
import hashlib
import io
import json
import os
import re
import shutil
import signal
import sys
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import quote, urlsplit
from typing import Any, Optional
from uuid import UUID, uuid4

import httpx
from sqlalchemy import select

from app.config import settings
from app.services.funnel_metadata import build_public_page_metadata_for_context
from app.services.imported_html_runtime import resolve_funnel_page_stage
from app.services import namecheap_dns as namecheap_dns_service
from app.services.public_runtime_tracking import resolve_public_runtime_tracking


class DeployError(RuntimeError):
    pass


_DEPLOY_JOB_LOG_TAIL_CHARS = 12000
_ORG_SCOPED_PORT_RANGE_START = 20000
_ORG_SCOPED_PORT_RANGE_END = 29999
_HOSTNAME_RE = re.compile(
    r"^(?=.{1,253}$)(?:[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?)(?:\.[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?)*$"
)
_ARTIFACT_ASSET_PUBLIC_ID_KEYS = {
    "assetPublicId",
    "thumbAssetPublicId",
    "posterAssetPublicId",
    "iconAssetPublicId",
    "swatchAssetPublicId",
}
_DEPLOY_ARTIFACT_MAX_EMBEDDED_ASSET_BYTES = int(
    os.getenv("DEPLOY_ARTIFACT_MAX_EMBEDDED_ASSET_BYTES", str(150 * 1024 * 1024))
)
_DEPLOY_ARTIFACT_EMBED_IMAGE_MAX_DIMENSION = int(
    os.getenv("DEPLOY_ARTIFACT_EMBED_IMAGE_MAX_DIMENSION", "1600")
)
_DEPLOY_ARTIFACT_EMBED_IMAGE_QUALITY = int(os.getenv("DEPLOY_ARTIFACT_EMBED_IMAGE_QUALITY", "80"))
_PUBLIC_ASSET_URL_PREFIXES = (
    "/public/assets/",
    "public/assets/",
    "/api/public/assets/",
    "api/public/assets/",
)
_FUNNEL_ARTIFACT_RENDER_MODE_RUNTIME_BUNDLE = "runtime_bundle"
_FUNNEL_ARTIFACT_RENDER_MODE_STANDALONE_IMPORTED_HTML = "standalone_imported_html"
_PUBLIC_ASSET_URL_IN_TEXT_RE = re.compile(
    r"(?i)(?:https?://[^\s\"'<>]+)?/?(?:api/)?public/assets/[^\s\"'<>?#]+"
)
_DEPLOY_TRACKING_VALIDATION_PAGE_TIMEOUT_MS = int(
    os.getenv("DEPLOY_TRACKING_VALIDATION_PAGE_TIMEOUT_MS", "30000")
)
_DEPLOY_TRACKING_VALIDATION_STEP_WAIT_MS = int(
    os.getenv("DEPLOY_TRACKING_VALIDATION_STEP_WAIT_MS", "1200")
)
_DEPLOY_TRACKING_VALIDATION_STORAGE_KEY = "__mos_deploy_tracking_validation__"
_DEPLOY_TRACKING_VALIDATION_INIT_SCRIPT = """
(() => {
  const STORAGE_KEY = "__mos_deploy_tracking_validation__";
  const defaultState = () => ({
    meta: [],
    posthog: { inits: [], captures: [] },
    internal: [],
  });
  const loadState = () => {
    try {
      const raw = window.sessionStorage.getItem(STORAGE_KEY);
      if (!raw) return defaultState();
      const parsed = JSON.parse(raw);
      if (!parsed || typeof parsed !== "object") return defaultState();
      if (!Array.isArray(parsed.meta)) parsed.meta = [];
      if (!parsed.posthog || typeof parsed.posthog !== "object") parsed.posthog = { inits: [], captures: [] };
      if (!Array.isArray(parsed.posthog.inits)) parsed.posthog.inits = [];
      if (!Array.isArray(parsed.posthog.captures)) parsed.posthog.captures = [];
      if (!Array.isArray(parsed.internal)) parsed.internal = [];
      return parsed;
    } catch (_error) {
      return defaultState();
    }
  };
  const state = loadState();
  const persist = () => {
    try {
      window.sessionStorage.setItem(STORAGE_KEY, JSON.stringify(state));
    } catch (_error) {
      // ignore storage write failures
    }
    window.__mosDeployTrackingValidation = state;
  };
  persist();

  try {
    navigator.sendBeacon = () => false;
  } catch (_error) {
    // ignore immutable navigator environments
  }

  const originalFetch = window.fetch.bind(window);
  window.fetch = async (input, init) => {
    const url =
      typeof input === "string"
        ? input
        : input && typeof input === "object" && typeof input.url === "string"
          ? input.url
          : "";
    if (url.includes("/api/public/events")) {
      try {
        const body = typeof init?.body === "string" ? init.body : null;
        if (body) {
          const parsed = JSON.parse(body);
          const events = Array.isArray(parsed?.events) ? parsed.events : [];
          for (const event of events) {
            const eventType = typeof event?.eventType === "string" ? event.eventType : null;
            if (!eventType) continue;
            state.internal.push({
              eventType,
              props: event && typeof event === "object" ? event.props || null : null,
            });
          }
          persist();
        }
      } catch (_error) {
        // ignore malformed payloads during validation capture
      }
    }
    return originalFetch(input, init);
  };

  let currentFbq = null;
  const wrapFbq = (candidate) => {
    if (typeof candidate !== "function") return candidate;
    if (candidate.__mosTrackingValidationWrapped === true) return candidate;
    const wrapped = function(...args) {
      state.meta.push(args);
      persist();
      return candidate.apply(this, args);
    };
    try {
      Object.defineProperties(wrapped, Object.getOwnPropertyDescriptors(candidate));
    } catch (_error) {
      // ignore descriptor copy failures
    }
    wrapped.__mosTrackingValidationWrapped = true;
    return wrapped;
  };
  Object.defineProperty(window, "fbq", {
    configurable: true,
    get() {
      return currentFbq;
    },
    set(value) {
      currentFbq = wrapFbq(value);
    },
  });
  Object.defineProperty(window, "_fbq", {
    configurable: true,
    get() {
      return currentFbq;
    },
    set(value) {
      currentFbq = wrapFbq(value);
    },
  });

  let currentPosthog = null;
  const wrapPosthogInstance = (instance) => {
    if (!instance || instance.__mosTrackingValidationWrapped === true) return instance;
    if (typeof instance.capture === "function") {
      const originalCapture = instance.capture;
      instance.capture = function(...args) {
        state.posthog.captures.push(args);
        persist();
        return originalCapture.apply(this, args);
      };
      instance.__mosTrackingValidationWrapped = true;
      return instance;
    }
    if (Array.isArray(instance) && typeof instance.push === "function") {
      const originalPush = instance.push;
      instance.push = function(entry) {
        if (Array.isArray(entry) && entry[0] === "capture") {
          state.posthog.captures.push(entry.slice(1));
          persist();
        }
        return originalPush.call(this, entry);
      };
      instance.__mosTrackingValidationWrapped = true;
      return instance;
    }
    return instance;
  };
  const wrapPosthogRoot = (candidate) => {
    if (!candidate || (typeof candidate !== "object" && typeof candidate !== "function")) {
      return candidate;
    }
    if (typeof candidate.init === "function" && candidate.__mosTrackingValidationInitWrapped !== true) {
      const originalInit = candidate.init;
      candidate.init = function(...args) {
        state.posthog.inits.push(args);
        persist();
        const result = originalInit.apply(this, args);
        const instanceName = typeof args[2] === "string" && args[2] ? args[2] : "posthog";
        if (candidate[instanceName]) {
          wrapPosthogInstance(candidate[instanceName]);
        }
        persist();
        return result;
      };
      candidate.__mosTrackingValidationInitWrapped = true;
    }
    if (candidate.mosFunnel) {
      wrapPosthogInstance(candidate.mosFunnel);
    }
    return candidate;
  };
  Object.defineProperty(window, "posthog", {
    configurable: true,
    get() {
      return currentPosthog;
    },
    set(value) {
      currentPosthog = wrapPosthogRoot(value);
    },
  });
})();
"""


def _require_standalone_upstream_api_origin(*, upstream_api_base_url: str) -> str:
    normalized = upstream_api_base_url.strip().rstrip("/")
    parsed = urlsplit(normalized)
    if not parsed.scheme or not parsed.netloc:
        raise DeployError("Deploy upstreamApiBaseUrl must start with http:// or https://.")
    if parsed.path not in ("", "/") or parsed.query or parsed.fragment:
        raise DeployError(
            "Standalone imported HTML deploys require deploy.upstreamApiBaseUrl to be an origin URL without a path, "
            f"for example 'https://api.example.com'; got '{normalized}'."
        )
    return f"{parsed.scheme}://{parsed.netloc}"


def _find_repo_root(start: Path) -> Path:
    """
    Locate the ghc repo root by walking upwards from `start`.

    We intentionally do not assume cwd is the repo root (in production we `cd mos/backend`).
    """
    start = start.resolve()
    for candidate in [start, *start.parents]:
        if (candidate / "mos" / "backend").is_dir() and (candidate / "mos" / "frontend").is_dir():
            return candidate
    raise DeployError(
        "Unable to locate repo root (expected to find mos/backend and mos/frontend). "
        "Run the server from inside the repo or set DEPLOY_ROOT_DIR to an absolute path."
    )


def _cloudhand_dir() -> Path:
    """
    Runtime directory for plans + Terraform state.

    NOTE: This is intentionally NOT the Python package `cloudhand/` under mos/backend/.
    """
    raw = Path(settings.DEPLOY_ROOT_DIR)
    if raw.is_absolute():
        return raw
    repo_root = _find_repo_root(Path.cwd())
    return (repo_root / raw).resolve()


def _terraform_dir() -> Path:
    return _cloudhand_dir() / "terraform"


def _resolve_terraform_bin() -> str:
    tf_bin = shutil.which("terraform")
    if not tf_bin:
        raise DeployError(
            "Terraform binary 'terraform' not found in PATH. Install Terraform on the MOS API host."
        )
    return tf_bin


def _find_latest_plan() -> Optional[Path]:
    ch_dir = _cloudhand_dir()
    if not ch_dir.exists():
        return None
    plans = sorted(
        (path for path in ch_dir.glob("plan-*.json") if not path.name.startswith("plan-apply-")),
        key=lambda p: p.stat().st_mtime,
        reverse=True,
    )
    return plans[0] if plans else None


def _assert_under_cloudhand(path: Path) -> Path:
    ch_dir = _cloudhand_dir().resolve()
    resolved = path.expanduser().resolve()
    if not resolved.is_relative_to(ch_dir):
        raise DeployError("plan_path must be inside the deploy plan directory (DEPLOY_ROOT_DIR).")
    return resolved


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _read_positive_timeout_from_env(*, env_name: str, default_seconds: float) -> float | None:
    raw_value = str(os.getenv(env_name, "")).strip()
    if not raw_value:
        return default_seconds
    try:
        timeout_seconds = float(raw_value)
    except ValueError as exc:
        raise DeployError(f"{env_name} must be a valid number of seconds.") from exc
    if timeout_seconds <= 0:
        return None
    return timeout_seconds


def _deploy_apply_timeout_seconds() -> float | None:
    return _read_positive_timeout_from_env(
        env_name="DEPLOY_APPLY_TIMEOUT_SECONDS",
        default_seconds=30 * 60,
    )


async def _collect_subprocess_output(
    stream: asyncio.StreamReader | None,
    *,
    logs: list[str],
) -> None:
    if stream is None:
        return
    async for raw in stream:
        logs.append(raw.decode(errors="ignore"))


async def _terminate_subprocess(proc: asyncio.subprocess.Process) -> None:
    if proc.returncode is not None:
        return

    try:
        if os.name == "posix":
            os.killpg(proc.pid, signal.SIGTERM)
        else:  # pragma: no cover - windows
            proc.terminate()
        await asyncio.wait_for(proc.wait(), timeout=10)
        return
    except ProcessLookupError:
        return
    except asyncio.TimeoutError:
        pass

    try:
        if os.name == "posix":
            os.killpg(proc.pid, signal.SIGKILL)
        else:  # pragma: no cover - windows
            proc.kill()
    except ProcessLookupError:
        return

    try:
        await asyncio.wait_for(proc.wait(), timeout=5)
    except asyncio.TimeoutError:  # pragma: no cover - defensive
        return


def _jobs_dir() -> Path:
    return _cloudhand_dir() / "jobs"


def _job_path(job_id: str) -> Path:
    safe = (job_id or "").strip()
    if not safe:
        raise DeployError("job_id is required.")
    if "/" in safe or "\\" in safe:
        raise DeployError("job_id is invalid.")
    return _jobs_dir() / f"{safe}.json"


def _write_json_atomic(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp_path = path.with_suffix(path.suffix + ".tmp")
    tmp_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    tmp_path.replace(path)


def _read_job(job_id: str) -> dict[str, Any]:
    path = _job_path(job_id)
    if not path.exists():
        raise DeployError(f"Deploy job '{job_id}' not found.")
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except Exception as exc:
        raise DeployError(f"Failed to read deploy job '{job_id}': {exc}") from exc
    if not isinstance(raw, dict):
        raise DeployError(f"Deploy job '{job_id}' is invalid.")
    return raw


def _publish_jobs_dir() -> Path:
    return _cloudhand_dir() / "publish-jobs"


def _publish_job_path(job_id: str) -> Path:
    safe = (job_id or "").strip()
    if not safe:
        raise DeployError("job_id is required.")
    if "/" in safe or "\\" in safe:
        raise DeployError("job_id is invalid.")
    return _publish_jobs_dir() / f"{safe}.json"


def _read_publish_job(job_id: str) -> dict[str, Any]:
    path = _publish_job_path(job_id)
    if not path.exists():
        raise DeployError(f"Publish job '{job_id}' not found.")
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except Exception as exc:
        raise DeployError(f"Failed to read publish job '{job_id}': {exc}") from exc
    if not isinstance(raw, dict):
        raise DeployError(f"Publish job '{job_id}' is invalid.")
    return raw


def get_latest_plan() -> dict[str, str]:
    plan_path = _find_latest_plan()
    if not plan_path:
        raise DeployError("No plan found.")
    try:
        content = plan_path.read_text(encoding="utf-8")
    except Exception as exc:  # pragma: no cover
        raise DeployError(f"Failed to read plan: {exc}") from exc
    return {"path": str(plan_path), "content": content}


def get_workload_domains_from_plan(
    *,
    workload_name: str,
    plan_path: str | None = None,
    instance_name: str | None = None,
) -> dict[str, Any]:
    name = (workload_name or "").strip()
    if not name:
        raise DeployError("workload_name is required.")

    base_plan_path = _assert_under_cloudhand(Path(plan_path)) if plan_path else _find_latest_plan()
    if not base_plan_path or not base_plan_path.exists():
        raise DeployError("No plan found.")

    try:
        plan = json.loads(base_plan_path.read_text(encoding="utf-8"))
    except Exception as exc:
        raise DeployError(f"Failed to read plan JSON: {exc}") from exc

    new_spec = plan.get("new_spec") or {}
    instances = new_spec.get("instances") or []
    if not isinstance(instances, list):
        raise DeployError("Plan new_spec.instances must be a list.")

    found = False
    server_names: list[str] = []
    https: bool | None = None
    workspace_server_names: list[str] | None = None

    for inst in instances:
        if instance_name and inst.get("name") != instance_name:
            continue
        workloads = inst.get("workloads") or []
        if not isinstance(workloads, list):
            continue
        for workload in workloads:
            if (workload.get("name") or "").strip() != name:
                continue
            found = True

            service_config = workload.get("service_config") or {}
            if not isinstance(service_config, dict):
                break

            if "workspace_server_names" in workload:
                raw_workspace_server_names = workload.get("workspace_server_names")
                if raw_workspace_server_names is None:
                    raw_workspace_server_names = []
                if not isinstance(raw_workspace_server_names, list):
                    raise DeployError("Workload workspace_server_names must be a list.")

                cleaned_workspace: list[str] = []
                seen_workspace: set[str] = set()
                for raw in raw_workspace_server_names:
                    if not isinstance(raw, str):
                        raise DeployError(
                            "Workload workspace_server_names entries must be strings."
                        )
                    hostname = raw.strip().lower()
                    if not hostname or hostname in seen_workspace:
                        continue
                    seen_workspace.add(hostname)
                    cleaned_workspace.append(hostname)
                workspace_server_names = cleaned_workspace

            raw_server_names = service_config.get("server_names") or []
            if raw_server_names is None:
                raw_server_names = []
            if not isinstance(raw_server_names, list):
                raise DeployError("Workload service_config.server_names must be a list.")

            cleaned: list[str] = []
            seen: set[str] = set()
            for raw in raw_server_names:
                if not isinstance(raw, str):
                    raise DeployError(
                        "Workload service_config.server_names entries must be strings."
                    )
                hostname = raw.strip()
                if not hostname:
                    continue
                if hostname in seen:
                    continue
                seen.add(hostname)
                cleaned.append(hostname)
            server_names = cleaned

            https_value = service_config.get("https")
            if isinstance(https_value, bool):
                https = https_value

            break
        if found:
            break

    result = {
        "plan_path": str(base_plan_path),
        "workload_found": found,
        "server_names": server_names,
        "https": https,
    }
    if workspace_server_names is not None:
        result["workspace_server_names"] = workspace_server_names
    return result


def save_plan(*, content: str, path: str | None = None) -> dict[str, str]:
    # Validate JSON early
    try:
        json.loads(content)
    except Exception as exc:
        raise DeployError(f"Plan content is not valid JSON: {exc}") from exc

    ch_dir = _cloudhand_dir()
    ch_dir.mkdir(parents=True, exist_ok=True)

    if path:
        plan_path = _assert_under_cloudhand(Path(path))
    else:
        ts = datetime.utcnow().strftime("%Y-%m-%dT%H-%M-%SZ")
        plan_path = ch_dir / f"plan-{ts}.json"

    try:
        plan_path.write_text(content, encoding="utf-8")
    except Exception as exc:  # pragma: no cover
        raise DeployError(f"Failed to write plan: {exc}") from exc

    return {"path": str(plan_path)}


def _deep_merge(dst: Any, patch: Any) -> Any:
    """
    Recursive merge for dict patches.

    - dict + dict => merge keys recursively
    - all other types (including lists) => patch overwrites dst
    """
    if isinstance(dst, dict) and isinstance(patch, dict):
        out = dict(dst)
        for k, v in patch.items():
            out[k] = _deep_merge(out.get(k), v)
        return out
    return patch


def _coerce_service_port(*, raw_port: Any, context: str) -> int:
    try:
        port = int(raw_port)
    except Exception as exc:
        raise DeployError(f"{context} port '{raw_port}' is invalid.") from exc
    if port < 1 or port > 65535:
        raise DeployError(f"{context} port {port} is out of range (1-65535).")
    return port


def _extract_primary_service_port(*, workload: dict[str, Any], context: str) -> int | None:
    service_config = workload.get("service_config")
    if service_config is None:
        return None
    if not isinstance(service_config, dict):
        raise DeployError(f"{context} service_config must be an object.")
    ports = service_config.get("ports")
    if ports is None:
        return None
    if not isinstance(ports, list):
        raise DeployError(f"{context} service_config.ports must be a list.")
    if not ports:
        return None
    return _coerce_service_port(raw_port=ports[0], context=f"{context} service_config")


def _extract_workload_server_names(*, workload: dict[str, Any], context: str) -> list[str]:
    service_config = workload.get("service_config")
    if not isinstance(service_config, dict):
        raise DeployError(f"{context} service_config must be an object.")
    raw_server_names = service_config.get("server_names")
    if raw_server_names is None:
        return []
    if not isinstance(raw_server_names, list):
        raise DeployError(f"{context} service_config.server_names must be a list.")
    server_names: list[str] = []
    for idx, value in enumerate(raw_server_names):
        if not isinstance(value, str):
            raise DeployError(f"{context} service_config.server_names[{idx}] must be a string.")
        hostname = value.strip()
        if hostname:
            server_names.append(hostname)
    return server_names


def _collect_used_instance_ports(*, plan: dict[str, Any], instance_name: str | None) -> set[int]:
    new_spec = plan.get("new_spec")
    if not isinstance(new_spec, dict):
        raise DeployError("Plan new_spec must be an object.")
    instances = new_spec.get("instances")
    if not isinstance(instances, list):
        raise DeployError("Plan new_spec.instances must be a list.")

    target_instance_name = (instance_name or "").strip()
    used_ports: set[int] = set()
    for inst in instances:
        if not isinstance(inst, dict):
            continue
        current_instance_name = str(inst.get("name") or "").strip()
        if target_instance_name and current_instance_name != target_instance_name:
            continue
        workloads = inst.get("workloads")
        if not isinstance(workloads, list):
            continue
        for workload in workloads:
            if not isinstance(workload, dict):
                continue
            service_config = workload.get("service_config")
            if not isinstance(service_config, dict):
                continue
            raw_ports = service_config.get("ports")
            if raw_ports is None:
                continue
            if not isinstance(raw_ports, list):
                raise DeployError("Workload service_config.ports must be a list.")
            for raw_port in raw_ports:
                used_ports.add(
                    _coerce_service_port(raw_port=raw_port, context="Workload service_config")
                )
    return used_ports


def _org_scoped_service_port(*, org_id: str, used_ports: set[int]) -> int:
    normalized_org = (org_id or "").strip().lower()
    if not normalized_org:
        raise DeployError("org_id is required for deterministic workload port assignment.")

    span = _ORG_SCOPED_PORT_RANGE_END - _ORG_SCOPED_PORT_RANGE_START + 1
    if span <= 0:
        raise DeployError("Invalid org-scoped port range configuration.")

    seed = hashlib.sha256(normalized_org.encode("utf-8")).hexdigest()
    offset = int(seed[:8], 16) % span
    for step in range(span):
        candidate = _ORG_SCOPED_PORT_RANGE_START + ((offset + step) % span)
        if candidate not in used_ports:
            return candidate
    raise DeployError(
        f"No free org-scoped ports available in range {_ORG_SCOPED_PORT_RANGE_START}-{_ORG_SCOPED_PORT_RANGE_END}."
    )


def _ensure_org_scoped_workload_port(
    *,
    workload: dict[str, Any],
    existing_workload: dict[str, Any] | None,
    org_id: str,
    plan: dict[str, Any],
    instance_name: str | None,
) -> dict[str, Any]:
    service_config = workload.get("service_config")
    if not isinstance(service_config, dict):
        raise DeployError("Workload service_config must be an object.")

    server_names = _extract_workload_server_names(workload=workload, context="Workload patch")
    # Domain-based routing does not require an org-scoped origin port.
    if server_names:
        return workload

    explicit_port = _extract_primary_service_port(workload=workload, context="Workload patch")
    if explicit_port is not None:
        return workload

    if existing_workload is not None:
        existing_port = _extract_primary_service_port(
            workload=existing_workload, context="Existing workload"
        )
        if existing_port is not None:
            service_config["ports"] = [existing_port]
            workload["service_config"] = service_config
            return workload

    used_ports = _collect_used_instance_ports(plan=plan, instance_name=instance_name)
    assigned_port = _org_scoped_service_port(org_id=org_id, used_ports=used_ports)
    service_config["ports"] = [assigned_port]
    workload["service_config"] = service_config
    return workload


def build_funnel_publication_workload_patch(
    *,
    workload_name: str,
    client_id: str,
    upstream_base_url: str,
    upstream_api_base_url: str,
    server_names: list[str],
    https: bool,
    destination_path: str,
    artifact_render_mode: str = _FUNNEL_ARTIFACT_RENDER_MODE_RUNTIME_BUNDLE,
) -> dict[str, Any]:
    name = workload_name.strip()
    if not name:
        raise DeployError("Deploy workloadName must be non-empty.")
    _ = upstream_base_url

    resolved_client_id = client_id.strip()
    if not resolved_client_id:
        raise DeployError("Deploy client_id must be non-empty.")

    api_base_root = upstream_api_base_url.strip().rstrip("/")
    if not api_base_root.startswith(("http://", "https://")):
        raise DeployError("Deploy upstreamApiBaseUrl must start with http:// or https://.")

    seen_server_names: set[str] = set()
    normalized_server_names: list[str] = []
    for raw in server_names:
        hostname = raw.strip().lower()
        if not hostname:
            continue
        if " " in hostname:
            raise DeployError(f"Invalid hostname in deploy serverNames: '{raw}'.")
        if hostname in seen_server_names:
            continue
        seen_server_names.add(hostname)
        normalized_server_names.append(hostname)

    destination = destination_path.strip()
    if not destination:
        raise DeployError("Deploy destinationPath must be non-empty.")

    normalized_render_mode = str(artifact_render_mode or "").strip().lower()
    if normalized_render_mode not in {
        _FUNNEL_ARTIFACT_RENDER_MODE_RUNTIME_BUNDLE,
        _FUNNEL_ARTIFACT_RENDER_MODE_STANDALONE_IMPORTED_HTML,
    }:
        raise DeployError(
            "Deploy renderMode must be 'runtime_bundle' or 'standalone_imported_html'."
        )

    if normalized_render_mode == _FUNNEL_ARTIFACT_RENDER_MODE_STANDALONE_IMPORTED_HTML:
        api_base_root = _require_standalone_upstream_api_origin(upstream_api_base_url=api_base_root)

    https_enabled = https and bool(normalized_server_names)

    source_ref: dict[str, Any] = {
        "client_id": resolved_client_id,
        "upstream_api_base_root": api_base_root,
        "artifact_render_mode": normalized_render_mode,
        "artifact": {
            "meta": {
                "clientId": resolved_client_id,
            },
            "products": {},
        },
    }
    if normalized_render_mode == _FUNNEL_ARTIFACT_RENDER_MODE_RUNTIME_BUNDLE:
        source_ref["runtime_dist_path"] = settings.DEPLOY_ARTIFACT_RUNTIME_DIST_PATH

    return {
        "name": name,
        "source_type": "funnel_artifact",
        "source_ref": source_ref,
        "repo_url": None,
        "runtime": "static",
        "build_config": {
            "install_command": None,
            "build_command": None,
            "system_packages": [],
        },
        "service_config": {
            "command": None,
            "environment": {},
            "ports": [],
            "server_names": normalized_server_names,
            "https": https_enabled,
        },
        "destination_path": destination,
    }


def build_funnel_artifact_workload_patch(
    *,
    workload_name: str,
    client_id: str,
    upstream_base_url: str,
    upstream_api_base_url: str,
    server_names: list[str],
    https: bool,
    destination_path: str,
    artifact_render_mode: str = _FUNNEL_ARTIFACT_RENDER_MODE_RUNTIME_BUNDLE,
) -> dict[str, Any]:
    return build_funnel_publication_workload_patch(
        workload_name=workload_name,
        client_id=client_id,
        upstream_base_url=upstream_base_url,
        upstream_api_base_url=upstream_api_base_url,
        server_names=server_names,
        https=https,
        destination_path=destination_path,
        artifact_render_mode=artifact_render_mode,
    )


def _walk_json_dicts(node: Any):
    if isinstance(node, dict):
        yield node
        for value in node.values():
            yield from _walk_json_dicts(value)
    elif isinstance(node, list):
        for item in node:
            yield from _walk_json_dicts(item)


def _resolve_design_system_brand_logo_override(
    *,
    design_system_tokens: dict[str, Any] | None,
) -> tuple[str, str | None] | None:
    if not isinstance(design_system_tokens, dict):
        return None
    brand = design_system_tokens.get("brand")
    if not isinstance(brand, dict):
        return None

    raw_asset_public_id = brand.get("logoAssetPublicId")
    if not isinstance(raw_asset_public_id, str) or not raw_asset_public_id.strip():
        return None
    asset_public_id = raw_asset_public_id.strip()

    alt: str | None = None
    raw_logo_alt = brand.get("logoAlt")
    if isinstance(raw_logo_alt, str) and raw_logo_alt.strip():
        alt = raw_logo_alt.strip()
    else:
        raw_brand_name = brand.get("name")
        if isinstance(raw_brand_name, str) and raw_brand_name.strip():
            alt = raw_brand_name.strip()

    return asset_public_id, alt


def _parse_json_object_string(raw_value: Any) -> dict[str, Any] | None:
    if not isinstance(raw_value, str) or not raw_value.strip():
        return None
    try:
        parsed = json.loads(raw_value)
    except json.JSONDecodeError:
        return None
    if not isinstance(parsed, dict):
        return None
    return parsed


def _apply_brand_logo_override_to_logo_node(
    logo_node: Any,
    *,
    asset_public_id: str,
    alt: str | None,
) -> bool:
    if not isinstance(logo_node, dict):
        return False

    changed = False
    if logo_node.get("assetPublicId") != asset_public_id:
        logo_node["assetPublicId"] = asset_public_id
        changed = True

    if "referenceAssetPublicId" in logo_node:
        logo_node.pop("referenceAssetPublicId", None)
        changed = True

    if alt and logo_node.get("alt") != alt:
        logo_node["alt"] = alt
        changed = True

    return changed


def _apply_brand_logo_override_to_path(
    root: Any,
    *,
    path: tuple[str, ...],
    asset_public_id: str,
    alt: str | None,
) -> bool:
    node = root
    for segment in path:
        if not isinstance(node, dict):
            return False
        node = node.get(segment)
    return _apply_brand_logo_override_to_logo_node(
        node,
        asset_public_id=asset_public_id,
        alt=alt,
    )


def _materialize_design_system_brand_logo_in_puck_data(
    *,
    puck_data: dict[str, Any],
    design_system_tokens: dict[str, Any] | None,
) -> dict[str, Any]:
    override = _resolve_design_system_brand_logo_override(design_system_tokens=design_system_tokens)
    if override is None:
        return puck_data

    asset_public_id, alt = override
    cloned = copy.deepcopy(puck_data)

    def walk(node: Any) -> None:
        if isinstance(node, list):
            for item in node:
                walk(item)
            return
        if not isinstance(node, dict):
            return

        block_type = node.get("type")
        props = node.get("props")
        if isinstance(block_type, str) and isinstance(props, dict):
            config = props.get("config")
            if isinstance(config, dict):
                if block_type == "SalesPdpHeader":
                    _apply_brand_logo_override_to_path(
                        config,
                        path=("logo",),
                        asset_public_id=asset_public_id,
                        alt=alt,
                    )
                elif block_type == "SalesPdpHero":
                    _apply_brand_logo_override_to_path(
                        config,
                        path=("header", "logo"),
                        asset_public_id=asset_public_id,
                        alt=alt,
                    )
                elif block_type in {"SalesPdpFooter", "PreSalesFooter"}:
                    _apply_brand_logo_override_to_path(
                        config,
                        path=("logo",),
                        asset_public_id=asset_public_id,
                        alt=alt,
                    )
                elif block_type == "SalesPdpTemplate":
                    _apply_brand_logo_override_to_path(
                        config,
                        path=("hero", "header", "logo"),
                        asset_public_id=asset_public_id,
                        alt=alt,
                    )
                    _apply_brand_logo_override_to_path(
                        config,
                        path=("footer", "logo"),
                        asset_public_id=asset_public_id,
                        alt=alt,
                    )
                elif block_type == "PreSalesTemplate":
                    _apply_brand_logo_override_to_path(
                        config,
                        path=("footer", "logo"),
                        asset_public_id=asset_public_id,
                        alt=alt,
                    )

            parsed_config_json = _parse_json_object_string(props.get("configJson"))
            if parsed_config_json is not None:
                changed_json = False
                if block_type == "SalesPdpHeader":
                    changed_json = _apply_brand_logo_override_to_path(
                        parsed_config_json,
                        path=("logo",),
                        asset_public_id=asset_public_id,
                        alt=alt,
                    )
                elif block_type == "SalesPdpHero":
                    changed_json = _apply_brand_logo_override_to_path(
                        parsed_config_json,
                        path=("header", "logo"),
                        asset_public_id=asset_public_id,
                        alt=alt,
                    )
                elif block_type in {"SalesPdpFooter", "PreSalesFooter"}:
                    changed_json = _apply_brand_logo_override_to_path(
                        parsed_config_json,
                        path=("logo",),
                        asset_public_id=asset_public_id,
                        alt=alt,
                    )
                elif block_type == "SalesPdpTemplate":
                    changed_json = _apply_brand_logo_override_to_path(
                        parsed_config_json,
                        path=("hero", "header", "logo"),
                        asset_public_id=asset_public_id,
                        alt=alt,
                    )
                    changed_json |= _apply_brand_logo_override_to_path(
                        parsed_config_json,
                        path=("footer", "logo"),
                        asset_public_id=asset_public_id,
                        alt=alt,
                    )
                elif block_type == "PreSalesTemplate":
                    changed_json = _apply_brand_logo_override_to_path(
                        parsed_config_json,
                        path=("footer", "logo"),
                        asset_public_id=asset_public_id,
                        alt=alt,
                    )

                if changed_json:
                    props["configJson"] = json.dumps(parsed_config_json, ensure_ascii=False)

        for value in node.values():
            walk(value)

    walk(cloned)
    return cloned


def _classify_public_asset_url(raw_value: str) -> tuple[str | None, str | None]:
    value = str(raw_value or "").strip()
    if not value:
        return None, None

    path = value
    if value.startswith(("http://", "https://")):
        path = urlsplit(value).path or ""

    trimmed_path = path.strip()
    lowered_path = trimmed_path.lower()
    for prefix in _PUBLIC_ASSET_URL_PREFIXES:
        if not lowered_path.startswith(prefix):
            continue
        remainder = trimmed_path[len(prefix) :]
        remainder = remainder.split("?", 1)[0].split("#", 1)[0].strip()
        token, has_nested_path, _rest = remainder.partition("/")
        token = token.strip()
        if not token:
            return None, None
        if "." in token:
            token = token.split(".", 1)[0]
        if not token:
            return None, None
        try:
            return str(UUID(token)), None
        except ValueError:
            if has_nested_path:
                # Relative standalone assets like public/assets/generated/foo.jpg are
                # handled by the standalone deployer and are not canonical MOS asset ids.
                return None, None
            return None, token

    return None, None


def _extract_public_asset_id_from_url(raw_value: str) -> str | None:
    public_id, _invalid_token = _classify_public_asset_url(raw_value)
    return public_id


def _extract_public_asset_refs_from_text(raw_value: str) -> tuple[set[str], list[str]]:
    value = str(raw_value or "").strip()
    if not value:
        return set(), []

    matches = set()
    invalid_urls: list[str] = []
    for match in _PUBLIC_ASSET_URL_IN_TEXT_RE.finditer(value):
        candidate = str(match.group(0) or "").strip()
        if not candidate:
            continue
        public_id, invalid_token = _classify_public_asset_url(candidate)
        if public_id:
            matches.add(public_id)
            continue
        if invalid_token:
            invalid_urls.append(candidate)
    return matches, invalid_urls


def _extract_embedded_asset_public_ids(
    *,
    puck_data: dict[str, Any],
    design_system_tokens: dict[str, Any] | None,
    context_label: str,
) -> set[str]:
    public_ids: set[str] = set()

    for obj in _walk_json_dicts(puck_data):
        for key in _ARTIFACT_ASSET_PUBLIC_ID_KEYS:
            if key not in obj:
                continue
            raw_value = obj.get(key)
            if not isinstance(raw_value, str) or not raw_value.strip():
                raise DeployError(
                    f"{context_label} includes invalid {key}. Expected a non-empty UUID string."
                )
            cleaned = raw_value.strip()
            try:
                normalized = str(UUID(cleaned))
            except ValueError as exc:
                raise DeployError(
                    f"{context_label} includes invalid {key} '{cleaned}'. Expected a UUID."
                ) from exc
            public_ids.add(normalized)

        for raw_value in obj.values():
            if not isinstance(raw_value, str):
                continue
            matched_public_ids, invalid_urls = _extract_public_asset_refs_from_text(raw_value)
            if invalid_urls:
                raise DeployError(
                    f"{context_label} includes invalid public asset URL '{invalid_urls[0]}'. "
                    "Expected /public/assets/<uuid>."
                )
            if not matched_public_ids:
                public_id_from_url, invalid_token = _classify_public_asset_url(raw_value)
                if public_id_from_url:
                    matched_public_ids = {public_id_from_url}
                elif invalid_token:
                    raise DeployError(
                        f"{context_label} includes invalid public asset URL '{raw_value}'. "
                        "Expected /public/assets/<uuid>."
                    )
            for public_id_from_url in matched_public_ids:
                public_ids.add(public_id_from_url)

    if isinstance(design_system_tokens, dict):
        brand = design_system_tokens.get("brand")
        if isinstance(brand, dict):
            for token_key in ("logoAssetPublicId", "logoOnDarkAssetPublicId"):
                if brand.get(token_key) is None:
                    continue
                raw_logo_public_id = brand.get(token_key)
                if not isinstance(raw_logo_public_id, str) or not raw_logo_public_id.strip():
                    raise DeployError(
                        f"{context_label} designSystemTokens.brand.{token_key} must be a non-empty UUID string."
                    )
                cleaned_logo_public_id = raw_logo_public_id.strip()
                try:
                    normalized_logo_public_id = str(UUID(cleaned_logo_public_id))
                except ValueError as exc:
                    raise DeployError(
                        f"{context_label} designSystemTokens.brand.{token_key} "
                        f"'{cleaned_logo_public_id}' is not a valid UUID."
                    ) from exc
                public_ids.add(normalized_logo_public_id)

    return public_ids


def _build_embedded_asset_payload(
    *,
    session: Any,
    org_id: str,
    client_id: str,
    public_ids: list[str],
) -> tuple[dict[str, dict[str, Any]], int]:
    if not public_ids:
        return {}, 0

    from sqlalchemy import select

    from app.db.models import Asset
    from app.services.media_storage import MediaStorage

    asset_public_ids = [UUID(value) for value in public_ids]
    assets = list(
        session.scalars(
            select(Asset).where(
                Asset.org_id == org_id,
                Asset.client_id == client_id,
                Asset.public_id.in_(asset_public_ids),
            )
        ).all()
    )
    assets_by_public_id = {str(asset.public_id): asset for asset in assets}
    missing_public_ids = [
        public_id for public_id in public_ids if public_id not in assets_by_public_id
    ]
    if missing_public_ids:
        raise DeployError(
            "Funnel artifact references assetPublicId values that do not exist for this client: "
            + ", ".join(missing_public_ids)
        )

    storage = MediaStorage()
    output: dict[str, dict[str, Any]] = {}
    total_bytes = 0

    for public_id in public_ids:
        asset = assets_by_public_id[public_id]
        if asset.asset_kind != "image":
            raise DeployError(
                f"Asset {public_id} has kind '{asset.asset_kind}'. Only image assets can be embedded in funnel artifacts."
            )
        if asset.file_status != "ready":
            raise DeployError(
                f"Asset {public_id} is not ready (file_status={asset.file_status or 'null'})."
            )
        if not asset.storage_key:
            raise DeployError(f"Asset {public_id} is missing storage_key.")

        data, downloaded_content_type = storage.download_bytes(key=asset.storage_key)
        if not data:
            raise DeployError(f"Asset {public_id} downloaded empty bytes from object storage.")

        content_type = (
            (asset.content_type or downloaded_content_type or "").split(";")[0].strip().lower()
        )
        if not content_type.startswith("image/"):
            raise DeployError(
                f"Asset {public_id} has unsupported content type '{content_type or 'unknown'}'. Expected image/*."
            )

        data, content_type = _optimize_embedded_artifact_image_bytes(
            data=data,
            content_type=content_type,
            public_id=public_id,
        )

        total_bytes += len(data)
        if total_bytes > _DEPLOY_ARTIFACT_MAX_EMBEDDED_ASSET_BYTES:
            raise DeployError(
                "Embedded funnel artifact assets exceed DEPLOY_ARTIFACT_MAX_EMBEDDED_ASSET_BYTES "
                f"(current={total_bytes} bytes, limit={_DEPLOY_ARTIFACT_MAX_EMBEDDED_ASSET_BYTES} bytes)."
            )

        output[public_id] = {
            "contentType": content_type,
            "sizeBytes": len(data),
            "bytesBase64": base64.b64encode(data).decode("ascii"),
        }

    return output, total_bytes


def _optimize_embedded_artifact_image_bytes(
    *,
    data: bytes,
    content_type: str,
    public_id: str,
) -> tuple[bytes, str]:
    """
    Reduce embedded artifact size by resizing and re-encoding common raster assets to WebP.

    We intentionally keep strict behavior: invalid optimization config or unreadable image bytes
    fail fast with a descriptive error.
    """

    normalized_content_type = str(content_type or "").strip().lower()
    if normalized_content_type not in {"image/png", "image/jpeg", "image/jpg", "image/webp"}:
        return data, normalized_content_type

    max_dimension = _DEPLOY_ARTIFACT_EMBED_IMAGE_MAX_DIMENSION
    quality = _DEPLOY_ARTIFACT_EMBED_IMAGE_QUALITY
    if max_dimension <= 0:
        raise DeployError("DEPLOY_ARTIFACT_EMBED_IMAGE_MAX_DIMENSION must be greater than zero.")
    if quality < 1 or quality > 100:
        raise DeployError("DEPLOY_ARTIFACT_EMBED_IMAGE_QUALITY must be between 1 and 100.")

    from PIL import Image

    try:
        with Image.open(io.BytesIO(data)) as source:
            image = source.copy()
    except Exception as exc:
        raise DeployError(
            f"Failed to decode embedded artifact asset image bytes for {public_id}: {exc}"
        ) from exc

    width, height = image.size
    if width <= 0 or height <= 0:
        raise DeployError(
            f"Embedded artifact asset {public_id} has invalid image dimensions ({width}x{height})."
        )

    longest_edge = max(width, height)
    if longest_edge > max_dimension:
        scale = max_dimension / float(longest_edge)
        resized = (
            max(1, int(round(width * scale))),
            max(1, int(round(height * scale))),
        )
        image = image.resize(resized, Image.Resampling.LANCZOS)

    # Preserve alpha when present; otherwise use RGB for denser encoding.
    if "A" in image.getbands():
        if image.mode != "RGBA":
            image = image.convert("RGBA")
    elif image.mode != "RGB":
        image = image.convert("RGB")

    output = io.BytesIO()
    try:
        image.save(output, format="WEBP", quality=quality, method=6)
    except Exception as exc:
        raise DeployError(
            f"Failed to encode embedded artifact asset {public_id} to WebP: {exc}"
        ) from exc

    optimized = output.getvalue()
    if not optimized:
        raise DeployError(f"Embedded artifact asset {public_id} optimized to empty bytes.")
    return optimized, "image/webp"


def build_client_funnel_runtime_artifact_payload(
    *,
    session: Any,
    org_id: str,
    client_id: str,
    updated_from_funnel_id: str,
    updated_from_publication_id: str,
    publication_id_overrides: dict[str, str] | None = None,
) -> dict[str, Any]:
    from fastapi.encoders import jsonable_encoder
    from sqlalchemy import select

    from app.db.enums import FunnelStatusEnum
    from app.db.models import Funnel, FunnelPage, Product, ProductVariant
    from app.db.repositories.funnels import FunnelPublicRepository
    from app.services.design_systems import resolve_design_system_tokens
    from app.services.funnel_template_categories import resolve_funnel_template_artifact_slug
    from app.services.funnel_templates import resolve_funnel_template_page_type
    from app.services.paid_ads_qa import clean_optional_text
    from app.services.public_routing import require_product_route_slug

    template_to_artifact: dict[str, str] = {
        "pre-sales-listicle": "presales",
        "pre_sales_listicle": "presales",
        "sales-pdp": "sales",
        "sales_pdp": "sales",
    }
    def _artifact_page_slug(*, publication_slug: Any, template_id: str) -> str:
        artifact_slug = resolve_funnel_template_artifact_slug(template_id)
        if artifact_slug == "presales":
            return artifact_slug

        normalized_publication_slug = str(publication_slug or "").strip().lower()
        if normalized_publication_slug:
            if normalized_publication_slug == "pre-sales":
                return "presales"
            return normalized_publication_slug

        artifact_slug = template_to_artifact.get(template_id)
        if artifact_slug:
            return artifact_slug
        raise DeployError(
            f"Unsupported template '{template_id or 'unknown'}' for deploy artifact page slug."
        )


    client_funnels = list(
        session.scalars(
            select(Funnel)
            .where(
                Funnel.org_id == org_id,
                Funnel.client_id == client_id,
                Funnel.active_publication_id.is_not(None),
                Funnel.status != FunnelStatusEnum.disabled,
            )
            .order_by(Funnel.created_at.asc(), Funnel.id.asc())
        ).all()
    )
    if not client_funnels:
        raise DeployError("No published funnels found for client deploy artifact.")

    product_ids: set[str] = set()
    normalized_publication_overrides = {
        str(raw_funnel_id or "").strip(): str(raw_publication_id or "").strip()
        for raw_funnel_id, raw_publication_id in (publication_id_overrides or {}).items()
        if str(raw_funnel_id or "").strip() and str(raw_publication_id or "").strip()
    }

    for client_funnel in client_funnels:
        if not client_funnel.product_id:
            raise DeployError(f"Published funnel '{client_funnel.id}' is missing product_id.")
        product_ids.add(str(client_funnel.product_id))

    products = list(
        session.scalars(
            select(Product).where(
                Product.org_id == org_id,
                Product.id.in_(product_ids),
            )
        ).all()
    )
    products_by_id = {str(product.id): product for product in products}
    missing_product_ids = sorted(pid for pid in product_ids if pid not in products_by_id)
    if missing_product_ids:
        raise DeployError(
            "Missing products for published funnels in deploy artifact generation: "
            + ", ".join(missing_product_ids)
        )

    public_repo = FunnelPublicRepository(session)
    products_payload: dict[str, dict[str, Any]] = {}
    product_slug_to_product_id: dict[str, str] = {}
    embedded_asset_public_ids: set[str] = set()

    for client_funnel in client_funnels:
        route_slug = (client_funnel.route_slug or "").strip()
        if not route_slug:
            raise DeployError("Published funnel is missing route_slug.")

        product_id = str(client_funnel.product_id)
        product = products_by_id.get(product_id)
        if not product:
            raise DeployError(f"Product '{product_id}' not found while creating deploy artifact.")

        try:
            product_slug = require_product_route_slug(product=product)
        except ValueError as exc:
            raise DeployError(str(exc)) from exc

        existing_product_id = product_slug_to_product_id.get(product_slug)
        if existing_product_id and existing_product_id != product_id:
            raise DeployError(
                f"Product route slug '{product_slug}' is used by multiple products. "
                "Ensure product ids have unique 8-character prefixes."
            )
        product_slug_to_product_id[product_slug] = product_id

        active_publication_id = normalized_publication_overrides.get(
            str(client_funnel.id),
            str(client_funnel.active_publication_id or "").strip(),
        )
        if not active_publication_id:
            raise DeployError(f"Published funnel '{client_funnel.id}' has no active publication.")
        active_publication = public_repo.get_active_publication(
            funnel_id=str(client_funnel.id),
            publication_id=active_publication_id,
        )
        if not active_publication:
            raise DeployError(f"Active publication not found for funnel '{client_funnel.id}'.")
        publication_pages = public_repo.list_publication_pages(publication_id=active_publication_id)
        if not publication_pages:
            raise DeployError(f"Publication '{active_publication_id}' contains no pages.")

        page_details: list[tuple[str, str, Any, FunnelPage | None]] = []
        entry_slug: str | None = None
        seen_artifacts: set[str] = set()

        for item in publication_pages:
            version = public_repo.get_page_version(version_id=str(item.page_version_id))
            if not version:
                raise DeployError(f"Publication page '{item.page_id}' has no version.")
            page = session.scalars(select(FunnelPage).where(FunnelPage.id == item.page_id)).first()
            template_id = (page.template_id if page else None) or ""
            artifact_slug = _artifact_page_slug(
                publication_slug=getattr(item, "slug_at_publish", None),
                template_id=template_id,
            )
            if artifact_slug in seen_artifacts:
                raise DeployError(
                    f"Funnel '{client_funnel.id}' has multiple pages mapped to artifact '{artifact_slug}'."
                )
            seen_artifacts.add(artifact_slug)
            page_details.append((artifact_slug, str(item.page_id), version, page))
            if str(item.page_id) == str(active_publication.entry_page_id):
                entry_slug = artifact_slug

        if not entry_slug:
            raise DeployError(
                f"Entry page artifact slug not found for funnel '{client_funnel.id}'."
            )

        page_map = {page_id: artifact_slug for artifact_slug, page_id, _, _ in page_details}
        page_stage_map = {
            page_id: resolve_funnel_page_stage(
                slug=artifact_slug,
                template_id=page.template_id if page else None,
                page_name=page.name if page else None,
            )
            for artifact_slug, page_id, _, page in page_details
        }
        page_type_map = {
            page_id: page_type
            for _, page_id, _, page in page_details
            for page_type in [
                (clean_optional_text(page.page_type) if page else None)
                or resolve_funnel_template_page_type(page.template_id if page else None)
            ]
            if page_type
        }
        try:
            tracking = resolve_public_runtime_tracking(
                session=session,
                funnel=client_funnel,
                include_posthog=True,
            ) or {}
        except RuntimeError as exc:
            raise DeployError(str(exc)) from exc
        from app.db.repositories.client_compliance_profiles import ClientComplianceProfilesRepository

        compliance_profile = ClientComplianceProfilesRepository(session).get(
            org_id=str(client_funnel.org_id),
            client_id=str(client_funnel.client_id),
        )
        compliance_support_email = (
            str(compliance_profile.support_email or "").strip()
            if compliance_profile is not None
            else ""
        )
        pages_payload: dict[str, dict[str, Any]] = {}
        for artifact_slug, page_id, version, page in page_details:
            tokens = resolve_design_system_tokens(
                session=session,
                org_id=str(client_funnel.org_id),
                client_id=str(client_funnel.client_id),
                funnel=client_funnel,
                page=page,
            )
            materialized_puck_data = _materialize_design_system_brand_logo_in_puck_data(
                puck_data=version.puck_data,
                design_system_tokens=tokens if isinstance(tokens, dict) else None,
            )
            _apply_compliance_support_email_to_puck_data(
                puck_data=materialized_puck_data,
                support_email=compliance_support_email,
            )
            metadata = build_public_page_metadata_for_context(
                session=session,
                org_id=str(client_funnel.org_id),
                funnel=client_funnel,
                page=page,
                puck_data=version.puck_data,
            )
            page_context_label = f"Funnel '{client_funnel.id}' page '{page_id}' ({product_slug}/{route_slug}/{artifact_slug})"
            page_asset_public_ids = _extract_embedded_asset_public_ids(
                puck_data=materialized_puck_data,
                design_system_tokens=tokens if isinstance(tokens, dict) else None,
                context_label=page_context_label,
            )
            embedded_asset_public_ids.update(page_asset_public_ids)
            pages_payload[artifact_slug] = {
                "productSlug": product_slug,
                "funnelId": str(client_funnel.id),
                "funnelSlug": route_slug,
                "publicationId": active_publication_id,
                "pageId": page_id,
                "slug": artifact_slug,
                "stage": page_stage_map.get(page_id, "custom"),
                "puckData": materialized_puck_data,
                "pageMap": page_map,
                "pageStageMap": page_stage_map,
                "pageTypeMap": page_type_map,
                "designSystemTokens": tokens,
                "metadata": metadata,
                "tracking": tracking or None,
                "nextPageId": str(page.next_page_id) if page and page.next_page_id else None,
            }

        variants_query = select(ProductVariant).where(ProductVariant.product_id == product.id)
        if client_funnel.selected_offer_id:
            variants_query = variants_query.where(
                ProductVariant.offer_id == client_funnel.selected_offer_id
            )
        variants = session.scalars(variants_query).all()
        serialized_variants: list[dict[str, Any]] = []
        for variant in variants:
            data = jsonable_encoder(variant)
            data.pop("external_price_id", None)
            serialized_variants.append(data)

        commerce_payload: dict[str, Any] | None = None
        if serialized_variants:
            commerce_payload = {
                "productSlug": product_slug,
                "funnelSlug": route_slug,
                "funnelId": str(client_funnel.id),
                "product": {
                    **jsonable_encoder(product),
                    "variants": serialized_variants,
                    "variants_count": len(serialized_variants),
                },
            }

        product_bucket = products_payload.setdefault(
            product_slug,
            {
                "meta": {
                    "productId": product_id,
                    "productSlug": product_slug,
                },
                "funnels": {},
            },
        )
        funnels_payload = product_bucket.get("funnels")
        if not isinstance(funnels_payload, dict):
            raise DeployError(f"Artifact product '{product_slug}' has an invalid funnels payload.")
        if route_slug in funnels_payload:
            raise DeployError(
                f"Duplicate funnel route slug '{route_slug}' within artifact product '{product_slug}'."
            )

        funnels_payload[route_slug] = {
            "meta": {
                "productSlug": product_slug,
                "funnelSlug": route_slug,
                "funnelId": str(client_funnel.id),
                "publicationId": active_publication_id,
                "entrySlug": entry_slug,
                "pages": [
                    {"pageId": page_id, "slug": artifact_slug}
                    for artifact_slug, page_id, _, _ in page_details
                ],
            },
            "pages": pages_payload,
            "commerce": commerce_payload,
        }

    embedded_assets, total_embedded_asset_bytes = _build_embedded_asset_payload(
        session=session,
        org_id=org_id,
        client_id=client_id,
        public_ids=sorted(embedded_asset_public_ids),
    )

    return {
        "meta": {
            "clientId": str(client_id),
            "updatedFromFunnelId": updated_from_funnel_id,
            "updatedFromPublicationId": updated_from_publication_id,
        },
        "products": products_payload,
        "assets": {
            "totalBytes": total_embedded_asset_bytes,
            "items": embedded_assets,
        },
    }


def persist_client_funnel_runtime_artifact(
    *,
    session: Any,
    org_id: str,
    funnel_id: str,
    publication_id: str,
    created_by_user_id: str | None = None,
) -> dict[str, Any]:
    from sqlalchemy import select

    from app.db.enums import ArtifactTypeEnum
    from app.db.models import Funnel
    from app.db.repositories.artifacts import ArtifactsRepository

    funnel = session.scalars(
        select(Funnel).where(Funnel.org_id == org_id, Funnel.id == funnel_id)
    ).first()
    if not funnel:
        raise DeployError("Funnel not found while creating deploy artifact.")

    client_id = str(funnel.client_id)
    payload = build_client_funnel_runtime_artifact_payload(
        session=session,
        org_id=org_id,
        client_id=client_id,
        updated_from_funnel_id=str(funnel.id),
        updated_from_publication_id=publication_id,
        publication_id_overrides={str(funnel.id): publication_id},
    )

    artifacts_repo = ArtifactsRepository(session)
    latest = artifacts_repo.get_latest_by_type(
        org_id=org_id,
        client_id=client_id,
        artifact_type=ArtifactTypeEnum.funnel_runtime_bundle,
    )
    next_version = int(latest.version) + 1 if latest and latest.version else 1
    artifact = artifacts_repo.insert(
        org_id=org_id,
        client_id=client_id,
        artifact_type=ArtifactTypeEnum.funnel_runtime_bundle,
        data=payload,
        created_by_user=created_by_user_id,
        version=next_version,
    )
    return {
        "artifact_id": str(artifact.id),
        "artifact_version": int(artifact.version),
        "client_id": client_id,
    }


def _apply_compliance_support_email_to_puck_data(
    *,
    puck_data: dict[str, Any],
    support_email: str | None,
) -> None:
    normalized_support_email = str(support_email or "").strip()
    if not normalized_support_email:
        return

    def walk(node: Any) -> None:
        if isinstance(node, dict):
            if str(node.get("type") or "").strip() == "FunnelCompliancePage":
                props = node.get("props")
                if isinstance(props, dict) and not str(props.get("supportEmail") or "").strip():
                    props["supportEmail"] = normalized_support_email
            for value in node.values():
                walk(value)
        elif isinstance(node, list):
            for item in node:
                walk(item)

    walk(puck_data)


def _page_payload_supports_standalone_imported_html(*, page_payload: dict[str, Any]) -> bool:
    puck_data = page_payload.get("puckData")
    if not isinstance(puck_data, dict):
        return False

    content = puck_data.get("content")
    if not isinstance(content, list) or len(content) != 1:
        return False

    block = content[0]
    if not isinstance(block, dict) or str(block.get("type") or "").strip() != "ImportedHtmlDocument":
        return False

    props = block.get("props")
    if not isinstance(props, dict):
        return False

    html_document = props.get("htmlDocument")
    if not isinstance(html_document, str) or not html_document.strip():
        return False

    from app.services.imported_html_runtime import coerce_imported_html_instrumentation_manifest

    try:
        coerce_imported_html_instrumentation_manifest(props.get("instrumentationManifest"))
    except Exception:
        return False

    return True


def _page_payload_supports_standalone_compliance(*, page_payload: dict[str, Any]) -> bool:
    puck_data = page_payload.get("puckData")
    if not isinstance(puck_data, dict):
        return False

    content = puck_data.get("content")
    if not isinstance(content, list) or len(content) != 1:
        return False

    block = content[0]
    if not isinstance(block, dict) or str(block.get("type") or "").strip() != "FunnelCompliancePage":
        return False

    props = block.get("props")
    if not isinstance(props, dict):
        return False

    page_key = str(props.get("pageKey") or "").strip()
    return bool(page_key)


def _artifact_payload_supports_standalone_imported_html(*, artifact_payload: dict[str, Any]) -> bool:
    products = artifact_payload.get("products")
    if not isinstance(products, dict) or not products:
        return False

    for product_payload in products.values():
        if not isinstance(product_payload, dict):
            return False
        funnels = product_payload.get("funnels")
        if not isinstance(funnels, dict) or not funnels:
            return False
        for funnel_payload in funnels.values():
            if not isinstance(funnel_payload, dict):
                return False
            pages = funnel_payload.get("pages")
            if not isinstance(pages, dict) or not pages:
                return False
            for page_payload in pages.values():
                if not isinstance(page_payload, dict):
                    return False
                if (
                    not _page_payload_supports_standalone_imported_html(page_payload=page_payload)
                    and not _page_payload_supports_standalone_compliance(page_payload=page_payload)
                ):
                    return False

    return True


def _resolve_publish_job_artifact_render_mode(
    *,
    artifact_payload: dict[str, Any],
    requested_render_mode: str | None,
    render_mode_was_explicit: bool,
) -> str:
    normalized_requested_mode = str(requested_render_mode or "").strip().lower()
    if render_mode_was_explicit:
        return (
            normalized_requested_mode or _FUNNEL_ARTIFACT_RENDER_MODE_RUNTIME_BUNDLE
        )
    if _artifact_payload_supports_standalone_imported_html(artifact_payload=artifact_payload):
        return _FUNNEL_ARTIFACT_RENDER_MODE_STANDALONE_IMPORTED_HTML
    return _FUNNEL_ARTIFACT_RENDER_MODE_RUNTIME_BUNDLE


def _apply_publish_job_artifact_render_mode(
    *,
    workload_patch: dict[str, Any],
    artifact_payload: dict[str, Any],
    requested_render_mode: str | None,
    render_mode_was_explicit: bool,
) -> dict[str, Any]:
    source_ref = workload_patch.get("source_ref")
    if not isinstance(source_ref, dict):
        raise DeployError("Hydrated funnel deploy workload is missing source_ref.")

    resolved_render_mode = _resolve_publish_job_artifact_render_mode(
        artifact_payload=artifact_payload,
        requested_render_mode=requested_render_mode,
        render_mode_was_explicit=render_mode_was_explicit,
    )
    source_ref["artifact_render_mode"] = resolved_render_mode
    if resolved_render_mode == _FUNNEL_ARTIFACT_RENDER_MODE_STANDALONE_IMPORTED_HTML:
        source_ref["upstream_api_base_root"] = _require_standalone_upstream_api_origin(
            upstream_api_base_url=str(source_ref.get("upstream_api_base_root") or "")
        )
        source_ref.pop("runtime_dist_path", None)
    else:
        source_ref["runtime_dist_path"] = settings.DEPLOY_ARTIFACT_RUNTIME_DIST_PATH
    workload_patch["source_ref"] = source_ref
    return workload_patch


def _build_funnel_page_route_path(*, product_slug: str, funnel_slug: str, page_slug: str) -> str:
    return (
        f"/{quote(str(product_slug or '').strip(), safe='')}"
        f"/{quote(str(funnel_slug or '').strip(), safe='')}"
        f"/{quote(str(page_slug or '').strip(), safe='')}/"
    )


def _resolve_funnel_page_manifest(*, page_payload: dict[str, Any]) -> dict[str, Any]:
    puck_data = page_payload.get("puckData")
    content = puck_data.get("content") if isinstance(puck_data, dict) else None
    block = content[0] if isinstance(content, list) and len(content) == 1 and isinstance(content[0], dict) else None
    props = block.get("props") if isinstance(block, dict) else None
    manifest = props.get("instrumentationManifest") if isinstance(props, dict) else None
    if not isinstance(manifest, dict):
        raise DeployError("Imported HTML page is missing instrumentationManifest for tracking validation.")
    return manifest


def _resolve_consistent_tracking_config(*, page_payloads: list[dict[str, Any]]) -> dict[str, str]:
    keys = (
        "metaPixelId",
        "posthogProjectApiKey",
        "posthogApiHost",
        "posthogUiHost",
        "posthogDefaults",
        "posthogPersonProfiles",
    )
    resolved: dict[str, str] = {}
    for key in keys:
        seen_values = {
            str(tracking.get(key) or "").strip()
            for page_payload in page_payloads
            for tracking in [page_payload.get("tracking")]
            if isinstance(tracking, dict) and str(tracking.get(key) or "").strip()
        }
        if len(seen_values) > 1:
            raise DeployError(
                f"Post-deploy tracking validation requires a consistent '{key}' across the validated funnel pages."
            )
        if seen_values:
            resolved[key] = next(iter(seen_values))
    return resolved


def _assert_event_subsequence(*, observed: list[str], expected: list[str], label: str) -> None:
    cursor = 0
    matched: list[str] = []
    for event_name in observed:
        if cursor >= len(expected):
            break
        if event_name == expected[cursor]:
            matched.append(event_name)
            cursor += 1
    if cursor != len(expected):
        raise DeployError(
            f"Post-deploy tracking validation failed for {label}: expected event sequence "
            f"{expected!r}, observed relevant events {observed!r}."
        )


def _extract_recorded_event_names(*, observed_events: list[Any]) -> list[str]:
    names: list[str] = []
    for entry in observed_events:
        if not isinstance(entry, list) or len(entry) < 2:
            continue
        event_name = str(entry[1] or "").strip()
        method = str(entry[0] or "").strip()
        if not event_name or method not in {"track", "trackCustom"}:
            continue
        names.append(event_name)
    return names


def _extract_recorded_posthog_event_names(*, observed_events: list[Any]) -> list[str]:
    names: list[str] = []
    for entry in observed_events:
        if not isinstance(entry, list) or not entry:
            continue
        event_name = str(entry[0] or "").strip()
        if event_name:
            names.append(event_name)
    return names


def _build_funnel_tracking_validation_plan(
    *,
    artifact_payload: dict[str, Any],
    funnel_id: str,
    publication_id: str,
    access_urls: list[str],
    render_mode: str,
) -> dict[str, Any]:
    normalized_access_urls = _normalize_access_urls(access_urls)
    if not normalized_access_urls:
        raise DeployError("Post-deploy tracking validation requires at least one public access URL.")

    origin_url = normalized_access_urls[0]
    parsed_origin = urlsplit(origin_url)
    if not parsed_origin.scheme or not parsed_origin.netloc:
        raise DeployError(f"Invalid public access URL '{origin_url}' for post-deploy tracking validation.")
    origin = f"{parsed_origin.scheme}://{parsed_origin.netloc}"

    products = artifact_payload.get("products")
    if not isinstance(products, dict):
        raise DeployError("Funnel artifact payload is missing products for post-deploy tracking validation.")

    matched_product_slug = ""
    matched_funnel_slug = ""
    matched_funnel_payload: dict[str, Any] | None = None
    for raw_product_slug, product_payload in products.items():
        if not isinstance(product_payload, dict):
            continue
        funnels = product_payload.get("funnels")
        if not isinstance(funnels, dict):
            continue
        for raw_funnel_slug, funnel_payload in funnels.items():
            if not isinstance(funnel_payload, dict):
                continue
            funnel_meta = funnel_payload.get("meta")
            if not isinstance(funnel_meta, dict):
                continue
            if str(funnel_meta.get("funnelId") or "").strip() != funnel_id:
                continue
            if str(funnel_meta.get("publicationId") or "").strip() != publication_id:
                continue
            matched_product_slug = str(raw_product_slug or "").strip()
            matched_funnel_slug = str(raw_funnel_slug or "").strip()
            matched_funnel_payload = funnel_payload
            break
        if matched_funnel_payload is not None:
            break

    if matched_funnel_payload is None:
        raise DeployError(
            f"Could not find funnel '{funnel_id}' publication '{publication_id}' in the runtime artifact payload."
        )

    pages = matched_funnel_payload.get("pages")
    funnel_meta = matched_funnel_payload.get("meta")
    if not isinstance(pages, dict) or not isinstance(funnel_meta, dict):
        raise DeployError("Matched funnel artifact payload is missing pages or meta for tracking validation.")

    page_entries: list[dict[str, Any]] = []
    for raw_page_slug, page_payload in pages.items():
        if not isinstance(page_payload, dict):
            continue
        page_slug = str(raw_page_slug or "").strip()
        page_stage = str(page_payload.get("stage") or "").strip()
        page_id = str(page_payload.get("pageId") or "").strip()
        if not page_slug or not page_stage or not page_id:
            continue
        page_entries.append(
            {
                "slug": page_slug,
                "stage": page_stage,
                "page_id": page_id,
                "payload": page_payload,
                "url": origin + _build_funnel_page_route_path(
                    product_slug=matched_product_slug,
                    funnel_slug=matched_funnel_slug,
                    page_slug=page_slug,
                ),
            }
        )

    if not page_entries:
        raise DeployError("Matched funnel artifact payload contains no pages for tracking validation.")

    sales_page = next((entry for entry in page_entries if entry["stage"] == "sales"), None)
    if sales_page is None:
        raise DeployError("Post-deploy tracking validation requires a sales page in the published funnel.")
    pre_sales_page = next((entry for entry in page_entries if entry["stage"] == "pre_sales"), None)
    start_page = pre_sales_page or sales_page

    sales_manifest = _resolve_funnel_page_manifest(page_payload=sales_page["payload"])
    checkout_binding = next(
        (
            binding
            for binding in sales_manifest.get("bindings", [])
            if isinstance(binding, dict) and str(binding.get("type") or "").strip() == "checkout"
        ),
        None,
    )
    if checkout_binding is None:
        raise DeployError("Post-deploy tracking validation requires a checkout binding on the sales page.")
    checkout_selector = str(checkout_binding.get("selector") or "").strip()
    if not checkout_selector:
        raise DeployError("Sales-page checkout binding is missing a selector for tracking validation.")

    pre_sales_click_selector: str | None = None
    if pre_sales_page is not None:
        pre_sales_manifest = _resolve_funnel_page_manifest(page_payload=pre_sales_page["payload"])
        pre_sales_binding = next(
            (
                binding
                for binding in pre_sales_manifest.get("bindings", [])
                if isinstance(binding, dict)
                and str(binding.get("type") or "").strip() == "internal_navigation"
                and str(binding.get("targetPageId") or "").strip() == str(sales_page["page_id"])
            ),
            None,
        )
        if pre_sales_binding is None:
            raise DeployError(
                "Post-deploy tracking validation requires a pre-sales internal navigation binding to the sales page."
            )
        pre_sales_click_selector = str(pre_sales_binding.get("selector") or "").strip()
        if not pre_sales_click_selector:
            raise DeployError(
                "Pre-sales to sales binding is missing a selector for post-deploy tracking validation."
            )

    unified_tracking = _resolve_consistent_tracking_config(
        page_payloads=[
            start_page["payload"],
            sales_page["payload"],
        ]
    )
    has_meta = bool(unified_tracking.get("metaPixelId"))
    has_posthog = bool(
        unified_tracking.get("posthogProjectApiKey") and unified_tracking.get("posthogApiHost")
    )

    expected_internal_events = ["Entered Funnel"]
    expected_meta_events: list[str] = []
    expected_posthog_events: list[str] = []
    if pre_sales_page is not None:
        expected_internal_events.extend(
            [
                "pre_sales_page_view",
                "pre_sales_to_sales_click",
                "sales_page_view",
                "sales_to_checkout_click",
            ]
        )
        expected_meta_events.extend(
            [
                "Entered Funnel",
                "PageView",
                "PreSalesToSalesClick",
                "PageView",
                "EnteredSales",
                "AddToCart",
            ]
        )
        expected_posthog_events.extend(expected_meta_events)
    else:
        expected_internal_events.extend(
            [
                "sales_page_view",
                "sales_to_checkout_click",
            ]
        )
        expected_meta_events.extend(
            [
                "Entered Funnel",
                "PageView",
                "ViewContent",
                "AddToCart",
            ]
        )
        expected_posthog_events.extend(expected_meta_events)

    checkout_config = checkout_binding.get("checkout")
    external_checkout_urls = [
        str(item.get("url") or "").strip()
        for item in (
            checkout_config.get("externalUrlsByVariant")
            if isinstance(checkout_config, dict)
            else []
        )
        if isinstance(item, dict) and str(item.get("url") or "").strip()
    ]

    return {
        "origin": origin,
        "render_mode": render_mode,
        "start_page": start_page,
        "sales_page": sales_page,
        "pages_to_validate": list(
            {
                page["url"]: page
                for page in [start_page, sales_page]
            }.values()
        ),
        "pre_sales_click_selector": pre_sales_click_selector,
        "checkout_selector": checkout_selector,
        "checkout_mode": (
            str(checkout_config.get("mode") or "").strip()
            if isinstance(checkout_config, dict)
            else ""
        ),
        "external_checkout_urls": external_checkout_urls,
        "tracking": unified_tracking,
        "expected_internal_events": expected_internal_events,
        "expected_meta_events": expected_meta_events if has_meta else [],
        "expected_posthog_events": expected_posthog_events if has_posthog else [],
    }


def _validate_deployed_tracking_html(*, validation_plan: dict[str, Any]) -> None:
    if validation_plan.get("render_mode") != _FUNNEL_ARTIFACT_RENDER_MODE_STANDALONE_IMPORTED_HTML:
        return

    tracking = validation_plan.get("tracking") or {}
    expected_meta_pixel_id = str(tracking.get("metaPixelId") or "").strip()
    expected_posthog_api_key = str(tracking.get("posthogProjectApiKey") or "").strip()
    expected_posthog_api_host = str(tracking.get("posthogApiHost") or "").strip()
    expected_posthog_ui_host = str(tracking.get("posthogUiHost") or "").strip()
    expected_posthog_defaults = str(tracking.get("posthogDefaults") or "").strip()
    expected_posthog_person_profiles = str(tracking.get("posthogPersonProfiles") or "").strip()

    with httpx.Client(timeout=30.0, follow_redirects=True) as client:
        for page in validation_plan.get("pages_to_validate", []):
            if not isinstance(page, dict):
                continue
            page_url = str(page.get("url") or "").strip()
            if not page_url:
                continue
            response = client.get(page_url)
            response.raise_for_status()
            html_document = response.text
            if expected_meta_pixel_id:
                if expected_meta_pixel_id not in html_document or "connect.facebook.net/en_US/fbevents.js" not in html_document:
                    raise DeployError(
                        f"Post-deploy tracking validation failed for '{page_url}': Meta Pixel bootstrap was not embedded."
                    )
            if expected_posthog_api_key:
                required_fragments = [
                    "window.posthog.init(",
                    expected_posthog_api_key,
                    expected_posthog_api_host,
                ]
                if expected_posthog_ui_host:
                    required_fragments.append(expected_posthog_ui_host)
                if expected_posthog_defaults:
                    required_fragments.append(expected_posthog_defaults)
                if expected_posthog_person_profiles:
                    required_fragments.append(expected_posthog_person_profiles)
                missing_fragment = next((fragment for fragment in required_fragments if fragment not in html_document), None)
                if missing_fragment is not None:
                    raise DeployError(
                        f"Post-deploy tracking validation failed for '{page_url}': expected deployed HTML to include "
                        f"'{missing_fragment}' for PostHog bootstrap."
                    )


def _validate_observed_tracking_events(*, validation_plan: dict[str, Any], observed_state: dict[str, Any]) -> None:
    internal_events = [
        str(entry.get("eventType") or "").strip()
        for entry in (observed_state.get("internal") if isinstance(observed_state, dict) else [])
        if isinstance(entry, dict) and str(entry.get("eventType") or "").strip()
    ]
    _assert_event_subsequence(
        observed=internal_events,
        expected=list(validation_plan.get("expected_internal_events") or []),
        label="internal funnel events",
    )

    tracking = validation_plan.get("tracking") or {}
    expected_meta_pixel_id = str(tracking.get("metaPixelId") or "").strip()
    if expected_meta_pixel_id:
        meta_calls = observed_state.get("meta") if isinstance(observed_state, dict) else None
        meta_init_ids = [
            str(entry[1] or "").strip()
            for entry in meta_calls or []
            if isinstance(entry, list) and len(entry) >= 2 and str(entry[0] or "").strip() == "init"
        ]
        if expected_meta_pixel_id not in meta_init_ids:
            raise DeployError(
                f"Post-deploy tracking validation failed for Meta Pixel: expected init for pixel '{expected_meta_pixel_id}', "
                f"observed {meta_init_ids!r}."
            )
        meta_event_names = _extract_recorded_event_names(observed_events=meta_calls or [])
        _assert_event_subsequence(
            observed=meta_event_names,
            expected=list(validation_plan.get("expected_meta_events") or []),
            label="Meta Pixel events",
        )

    expected_posthog_api_key = str(tracking.get("posthogProjectApiKey") or "").strip()
    expected_posthog_api_host = str(tracking.get("posthogApiHost") or "").strip()
    if expected_posthog_api_key and expected_posthog_api_host:
        posthog_state = observed_state.get("posthog") if isinstance(observed_state, dict) else None
        posthog_inits = posthog_state.get("inits") if isinstance(posthog_state, dict) else []
        found_matching_init = False
        for entry in posthog_inits or []:
            if not isinstance(entry, list) or len(entry) < 2:
                continue
            api_key = str(entry[0] or "").strip()
            config = entry[1] if isinstance(entry[1], dict) else {}
            api_host = str(config.get("api_host") or "").strip()
            ui_host = str(config.get("ui_host") or "").strip()
            if api_key != expected_posthog_api_key or api_host != expected_posthog_api_host:
                continue
            expected_ui_host = str(tracking.get("posthogUiHost") or "").strip()
            if expected_ui_host and ui_host != expected_ui_host:
                continue
            found_matching_init = True
            break
        if not found_matching_init:
            raise DeployError(
                "Post-deploy tracking validation failed for PostHog: expected an init call matching the deployed tracking config."
            )
        posthog_event_names = _extract_recorded_posthog_event_names(
            observed_events=(posthog_state.get("captures") if isinstance(posthog_state, dict) else []) or []
        )
        _assert_event_subsequence(
            observed=posthog_event_names,
            expected=list(validation_plan.get("expected_posthog_events") or []),
            label="PostHog events",
        )


def _run_funnel_tracking_post_deploy_validation_sync(*, validation_plan: dict[str, Any]) -> None:
    from playwright.sync_api import sync_playwright

    _validate_deployed_tracking_html(validation_plan=validation_plan)

    origin = str(validation_plan.get("origin") or "").rstrip("/")
    start_page = validation_plan.get("start_page") or {}
    sales_page = validation_plan.get("sales_page") or {}
    start_url = str(start_page.get("url") or "").strip()
    sales_url = str(sales_page.get("url") or "").strip()
    if not start_url or not sales_url:
        raise DeployError("Post-deploy tracking validation requires start and sales page URLs.")

    query_separator = "&" if "?" in start_url else "?"
    paid_entry_url = (
        f"{start_url}{query_separator}"
        "utm_source=deploy-validation&utm_medium=deploy-validation&fbclid=deploy-validation"
    )
    mock_checkout_url = f"{origin}/__mos_mock_checkout__/"

    with sync_playwright() as playwright:
        browser = playwright.chromium.launch()
        try:
            context = browser.new_context(ignore_https_errors=True)
            context.route(
                "**/static/array.js*",
                lambda route: route.fulfill(
                    status=200,
                    content_type="application/javascript",
                    body="window.__mosPosthogArrayLoaded = true;",
                ),
            )
            context.route(
                "**/fbevents.js*",
                lambda route: route.fulfill(
                    status=200,
                    content_type="application/javascript",
                    body="window.__mosMetaPixelLibraryLoaded = true;",
                ),
            )
            context.route(
                "**/__mos_mock_checkout__*",
                lambda route: route.fulfill(
                    status=200,
                    content_type="text/html; charset=utf-8",
                    body="<html><body>mock checkout</body></html>",
                ),
            )
            context.route(
                "**/api/public/checkout*",
                lambda route: route.fulfill(
                    status=200,
                    content_type="application/json",
                    body=json.dumps(
                        {
                            "checkoutUrl": mock_checkout_url,
                            "sessionId": "deploy-validation-session",
                        }
                    ),
                ),
            )
            for external_url in validation_plan.get("external_checkout_urls", []):
                if not external_url:
                    continue
                context.route(
                    external_url,
                    lambda route: route.fulfill(
                        status=200,
                        content_type="text/html; charset=utf-8",
                        body="<html><body>mock external checkout</body></html>",
                    ),
                )
            context.add_init_script(_DEPLOY_TRACKING_VALIDATION_INIT_SCRIPT)
            page = context.new_page()
            page.goto(
                paid_entry_url,
                wait_until="domcontentloaded",
                timeout=_DEPLOY_TRACKING_VALIDATION_PAGE_TIMEOUT_MS,
            )
            page.wait_for_timeout(_DEPLOY_TRACKING_VALIDATION_STEP_WAIT_MS)

            pre_sales_selector = str(validation_plan.get("pre_sales_click_selector") or "").strip()
            if pre_sales_selector:
                page.locator(pre_sales_selector).first.click(
                    force=True,
                    timeout=_DEPLOY_TRACKING_VALIDATION_PAGE_TIMEOUT_MS,
                )
                page.wait_for_url(
                    re.compile(re.escape(urlsplit(sales_url).path)),
                    timeout=_DEPLOY_TRACKING_VALIDATION_PAGE_TIMEOUT_MS,
                )
                page.wait_for_timeout(_DEPLOY_TRACKING_VALIDATION_STEP_WAIT_MS)

            checkout_selector = str(validation_plan.get("checkout_selector") or "").strip()
            page.locator(checkout_selector).first.click(
                force=True,
                timeout=_DEPLOY_TRACKING_VALIDATION_PAGE_TIMEOUT_MS,
            )
            checkout_mode = str(validation_plan.get("checkout_mode") or "").strip()
            if checkout_mode == "external_checkout_url":
                external_checkout_urls = [
                    str(url or "").strip()
                    for url in validation_plan.get("external_checkout_urls", [])
                    if str(url or "").strip()
                ]
                if not external_checkout_urls:
                    raise DeployError(
                        "Post-deploy tracking validation could not determine an external checkout URL to observe."
                    )
                page.wait_for_url(
                    re.compile("|".join(re.escape(url) for url in external_checkout_urls)),
                    timeout=_DEPLOY_TRACKING_VALIDATION_PAGE_TIMEOUT_MS,
                )
                page.goto(
                    mock_checkout_url,
                    wait_until="domcontentloaded",
                    timeout=_DEPLOY_TRACKING_VALIDATION_PAGE_TIMEOUT_MS,
                )
            else:
                page.wait_for_url(
                    re.compile(re.escape(urlsplit(mock_checkout_url).path)),
                    timeout=_DEPLOY_TRACKING_VALIDATION_PAGE_TIMEOUT_MS,
                )
            page.wait_for_timeout(_DEPLOY_TRACKING_VALIDATION_STEP_WAIT_MS)
            observed_state = page.evaluate(
                f"""
() => {{
  try {{
    return JSON.parse(window.sessionStorage.getItem({json.dumps(_DEPLOY_TRACKING_VALIDATION_STORAGE_KEY)}) || "{{}}");
  }} catch (_error) {{
    return {{}};
  }}
}}
"""
            )
            if not isinstance(observed_state, dict):
                raise DeployError("Post-deploy tracking validation did not capture any tracking state.")
            _validate_observed_tracking_events(
                validation_plan=validation_plan,
                observed_state=observed_state,
            )
        finally:
            browser.close()


async def _run_funnel_tracking_post_deploy_validation(
    *,
    artifact_payload: dict[str, Any],
    funnel_id: str,
    publication_id: str,
    access_urls: list[str],
    render_mode: str,
) -> dict[str, Any]:
    validation_plan = _build_funnel_tracking_validation_plan(
        artifact_payload=artifact_payload,
        funnel_id=funnel_id,
        publication_id=publication_id,
        access_urls=access_urls,
        render_mode=render_mode,
    )
    await asyncio.to_thread(
        _run_funnel_tracking_post_deploy_validation_sync,
        validation_plan=validation_plan,
    )
    return {
        "startUrl": validation_plan["start_page"]["url"],
        "salesUrl": validation_plan["sales_page"]["url"],
        "expectedInternalEvents": validation_plan["expected_internal_events"],
        "expectedMetaEvents": validation_plan["expected_meta_events"],
        "expectedPosthogEvents": validation_plan["expected_posthog_events"],
    }


def hydrate_funnel_artifact_workload_patch(
    *,
    session: Any,
    org_id: str,
    funnel_id: str,
    publication_id: str,
    workload_patch: dict[str, Any],
    created_by_user_id: str | None = None,
) -> dict[str, Any]:
    source_type = str(workload_patch.get("source_type") or "").strip().lower()
    if source_type != "funnel_artifact":
        return workload_patch

    source_ref = workload_patch.get("source_ref")
    if not isinstance(source_ref, dict):
        raise DeployError("funnel_artifact workload patch is missing source_ref.")

    artifact_ref = persist_client_funnel_runtime_artifact(
        session=session,
        org_id=org_id,
        funnel_id=funnel_id,
        publication_id=publication_id,
        created_by_user_id=created_by_user_id,
    )
    from app.db.repositories.artifacts import ArtifactsRepository

    artifact_record = ArtifactsRepository(session).get(org_id=org_id, artifact_id=str(artifact_ref["artifact_id"]))
    if artifact_record is None:
        raise DeployError(
            f"Persisted funnel runtime artifact '{artifact_ref['artifact_id']}' could not be reloaded for deploy hydration."
        )
    artifact_payload = artifact_record.data
    if not isinstance(artifact_payload, dict):
        raise DeployError(
            f"Persisted funnel runtime artifact '{artifact_ref['artifact_id']}' has an invalid payload."
        )

    source_ref["client_id"] = str(artifact_ref["client_id"])
    source_ref["artifact_id"] = str(artifact_ref["artifact_id"])
    source_ref["artifact_version"] = int(artifact_ref["artifact_version"])
    source_ref["artifact"] = copy.deepcopy(artifact_payload)
    workload_patch["source_ref"] = source_ref
    return workload_patch


def build_site_runtime_bundle_artifact_payload(
    *,
    session: Any,
    org_id: str,
    site_id: str,
    publication_id: str,
) -> dict[str, Any]:
    """Build the site_runtime_bundle artifact payload from a publication snapshot.

    This payload captures the full publishable state of a site including:
    - Site metadata
    - All pages with their published versions
    - All site links
    - All site funnels with steps
    - All product bindings
    """
    from sqlalchemy import select

    from app.db.models import (
        Site,
        SitePublication,
        SitePublicationPage,
        SitePublicationLink,
        SitePublicationFunnel,
        SitePublicationFunnelStep,
        SitePublicationProductBinding,
        SitePageVersion,
    )
    from app.services.site_publications import (
        list_site_publication_pages,
        list_site_publication_links,
        list_site_publication_funnels,
        list_site_publication_funnel_steps,
        list_site_publication_product_bindings,
    )

    # Get the site
    site = session.scalars(select(Site).where(Site.id == site_id, Site.org_id == org_id)).first()
    if not site:
        raise DeployError(f"Site '{site_id}' not found for artifact payload build.")

    # Get the publication
    publication = session.scalars(
        select(SitePublication).where(SitePublication.id == publication_id)
    ).first()
    if not publication:
        raise DeployError(
            f"Site publication '{publication_id}' not found for artifact payload build."
        )

    if str(publication.site_id) != str(site_id):
        raise DeployError(
            f"Site publication '{publication_id}' does not belong to site '{site_id}'."
        )

    # Build pages payload
    pub_pages = list_site_publication_pages(session, publication_id=publication_id)
    pages_payload: dict[str, dict[str, Any]] = {}
    page_id_to_slug: dict[str, str] = {}

    for pub_page in pub_pages:
        # Get the page version
        version = session.scalars(
            select(SitePageVersion).where(SitePageVersion.id == pub_page.page_version_id)
        ).first()

        if not version:
            raise DeployError(
                f"Publication page '{pub_page.id}' references missing version "
                f"'{pub_page.page_version_id}'."
            )

        slug = pub_page.slug_at_publish
        pages_payload[slug] = {
            "pageId": str(pub_page.page_id),
            "versionId": str(pub_page.page_version_id),
            "pageType": pub_page.page_type_at_publish,
            "pageRole": pub_page.page_role_at_publish,
            "title": pub_page.title_at_publish,
            "description": pub_page.description_at_publish,
            "ordering": pub_page.ordering_at_publish,
            "puckData": version.puck_data,
        }
        page_id_to_slug[str(pub_page.page_id)] = slug

    # Build links payload
    pub_links = list_site_publication_links(session, publication_id=publication_id)
    links_payload: list[dict[str, Any]] = []

    for pub_link in pub_links:
        from_slug = (
            page_id_to_slug.get(str(pub_link.from_page_id_at_publish))
            if pub_link.from_page_id_at_publish
            else None
        )
        to_slug = (
            page_id_to_slug.get(str(pub_link.to_page_id_at_publish))
            if pub_link.to_page_id_at_publish
            else None
        )
        links_payload.append(
            {
                "fromPageSlug": from_slug,
                "toPageSlug": to_slug,
                "label": pub_link.label_at_publish,
                "kind": pub_link.link_kind_at_publish,
                "meta": pub_link.meta_at_publish,
            }
        )

    # Build funnels payload
    pub_funnels = list_site_publication_funnels(session, publication_id=publication_id)
    funnels_payload: dict[str, dict[str, Any]] = {}

    for pub_funnel in pub_funnels:
        pub_steps = list_site_publication_funnel_steps(session, publication_funnel_id=pub_funnel.id)

        steps_payload: list[dict[str, Any]] = []
        for pub_step in pub_steps:
            steps_payload.append(
                {
                    "pageSlug": pub_step.slug_at_publish,
                    "ordering": pub_step.ordering_at_publish,
                    "stepRole": pub_step.step_role_at_publish,
                    "ctaLabel": pub_step.cta_label_at_publish,
                }
            )

        funnels_payload[str(pub_funnel.site_funnel_id)] = {
            "name": pub_funnel.name_at_publish,
            "funnelType": pub_funnel.funnel_type_at_publish,
            "entryPageSlug": (
                page_id_to_slug.get(str(pub_funnel.entry_page_id_at_publish))
                if pub_funnel.entry_page_id_at_publish
                else None
            ),
            "steps": steps_payload,
        }

    # Build product bindings payload
    pub_bindings = list_site_publication_product_bindings(session, publication_id=publication_id)
    bindings_payload: list[dict[str, Any]] = []

    for pub_binding in pub_bindings:
        page_slug = (
            page_id_to_slug.get(str(pub_binding.page_id_at_publish))
            if pub_binding.page_id_at_publish
            else None
        )
        bindings_payload.append(
            {
                "productId": str(pub_binding.product_id_at_publish),
                "pageSlug": page_slug,
                "pageRole": pub_binding.page_role_at_publish,
                "variantIds": pub_binding.variant_ids_at_publish,
                "bindingContext": pub_binding.binding_context_at_publish,
                "priority": pub_binding.priority_at_publish,
                "active": pub_binding.active_at_publish,
            }
        )

    return {
        "meta": {
            "siteId": str(site.id),
            "siteName": site.name,
            "routeSlug": site.route_slug or "",
            "siteType": site.site_type or "",
            "siteFamily": site.site_family or "",
            "publicationId": str(publication.id),
            "publishedAt": publication.created_at.isoformat() if publication.created_at else "",
        },
        "pages": pages_payload,
        "links": links_payload,
        "funnels": funnels_payload,
        "productBindings": bindings_payload,
    }


def persist_site_runtime_bundle_artifact(
    *,
    session: Any,
    org_id: str,
    site_id: str,
    publication_id: str,
    created_by_user_id: str | None = None,
) -> dict[str, Any]:
    """Persist a site_runtime_bundle artifact from a publication snapshot.

    Returns artifact metadata including id and version.
    """
    from app.db.enums import ArtifactTypeEnum
    from app.db.models import Site
    from app.db.repositories.artifacts import ArtifactsRepository

    site = session.scalars(select(Site).where(Site.id == site_id, Site.org_id == org_id)).first()
    if not site:
        raise DeployError("Site not found while creating site runtime artifact.")

    client_id = str(site.client_id)

    payload = build_site_runtime_bundle_artifact_payload(
        session=session,
        org_id=org_id,
        site_id=site_id,
        publication_id=publication_id,
    )

    artifacts_repo = ArtifactsRepository(session)
    latest = artifacts_repo.get_latest_by_type(
        org_id=org_id,
        client_id=client_id,
        artifact_type=ArtifactTypeEnum.site_runtime_bundle,
    )
    next_version = int(latest.version) + 1 if latest and latest.version else 1

    artifact = artifacts_repo.insert(
        org_id=org_id,
        client_id=client_id,
        artifact_type=ArtifactTypeEnum.site_runtime_bundle,
        data=payload,
        created_by_user=created_by_user_id,
        version=next_version,
    )

    return {
        "artifact_id": str(artifact.id),
        "artifact_version": int(artifact.version),
        "site_id": site_id,
        "client_id": client_id,
    }


def patch_workload_in_plan(
    *,
    org_id: str,
    workload_patch: dict[str, Any],
    plan_path: str | None = None,
    instance_name: str | None = None,
    create_if_missing: bool = False,
    in_place: bool = False,
) -> dict[str, Any]:
    from cloudhand.models import ApplicationSpec

    name = (workload_patch.get("name") or "").strip()
    if not name:
        raise DeployError("Workload patch must include a non-empty 'name' field.")
    resolved_org_id = (org_id or "").strip()
    if not resolved_org_id:
        raise DeployError("org_id is required when patching a workload.")

    ch_dir = _cloudhand_dir()
    ch_dir.mkdir(parents=True, exist_ok=True)

    base_plan_path = _assert_under_cloudhand(Path(plan_path)) if plan_path else _find_latest_plan()
    if not base_plan_path or not base_plan_path.exists():
        raise DeployError("No plan found.")

    try:
        plan = json.loads(base_plan_path.read_text(encoding="utf-8"))
    except Exception as exc:
        raise DeployError(f"Failed to read plan JSON: {exc}") from exc

    new_spec = plan.get("new_spec") or {}
    instances = new_spec.get("instances") or []
    if not isinstance(instances, list):
        raise DeployError("Plan new_spec.instances must be a list.")

    updated = 0
    for inst in instances:
        if instance_name and inst.get("name") != instance_name:
            continue
        workloads = inst.get("workloads") or []
        if not isinstance(workloads, list):
            continue
        for i, existing in enumerate(workloads):
            if (existing.get("name") or "").strip() != name:
                continue
            merged = _deep_merge(existing, workload_patch)
            merged = _ensure_org_scoped_workload_port(
                workload=merged,
                existing_workload=existing if isinstance(existing, dict) else None,
                org_id=resolved_org_id,
                plan=plan,
                instance_name=str(inst.get("name") or "").strip() or None,
            )
            try:
                validated = ApplicationSpec.model_validate(merged)
            except Exception as exc:
                raise DeployError(f"Updated workload is invalid: {exc}") from exc
            workloads[i] = json.loads(validated.model_dump_json())
            inst["workloads"] = workloads
            updated += 1

    if updated == 0:
        if not create_if_missing:
            raise DeployError(f"No workload named '{name}' found in plan.")

        # Choose where to insert the new workload
        if instance_name:
            target_inst = next((i for i in instances if i.get("name") == instance_name), None)
            if not target_inst:
                raise DeployError(f"Instance '{instance_name}' not found in plan.")
        else:
            if len(instances) != 1:
                raise DeployError(
                    "instance_name is required when plan contains multiple instances."
                )
            target_inst = instances[0]

        workload_for_create = _ensure_org_scoped_workload_port(
            workload=dict(workload_patch),
            existing_workload=None,
            org_id=resolved_org_id,
            plan=plan,
            instance_name=str(target_inst.get("name") or "").strip() or None,
        )

        try:
            validated = ApplicationSpec.model_validate(workload_for_create)
        except Exception as exc:
            raise DeployError(f"Workload is invalid: {exc}") from exc

        target_inst.setdefault("workloads", [])
        if not isinstance(target_inst["workloads"], list):
            target_inst["workloads"] = []
        target_inst["workloads"].append(json.loads(validated.model_dump_json()))
        updated = 1

    plan["new_spec"] = new_spec

    out_path = (
        base_plan_path
        if in_place
        else (ch_dir / f"plan-{datetime.utcnow().strftime('%Y-%m-%dT%H-%M-%SZ')}.json")
    )
    try:
        out_path.write_text(json.dumps(plan, indent=2), encoding="utf-8")
    except Exception as exc:  # pragma: no cover
        raise DeployError(f"Failed to write updated plan: {exc}") from exc

    return {
        "status": "ok",
        "base_plan_path": str(base_plan_path),
        "updated_plan_path": str(out_path),
        "workload_name": name,
        "updated_count": updated,
    }


def _bootstrap_deploy_plan_payload(
    *, workload_patch: dict[str, Any], instance_name: str | None
) -> dict[str, Any]:
    from cloudhand.models import ApplicationSpec

    resolved_instance_name = (instance_name or "").strip() or "ubuntu-4gb-nbg1-2"

    try:
        validated_workload = ApplicationSpec.model_validate(workload_patch)
    except Exception as exc:
        raise DeployError(f"Workload is invalid for bootstrap plan: {exc}") from exc

    workload_payload = json.loads(validated_workload.model_dump_json())
    return {
        "operations": [],
        "new_spec": {
            "provider": "hetzner",
            "region": "fsn1",
            "networks": [
                {
                    "name": "default",
                    "cidr": "10.0.0.0/16",
                }
            ],
            "instances": [
                {
                    "name": resolved_instance_name,
                    "size": "cx23",
                    "network": "default",
                    "region": "nbg1",
                    "labels": {},
                    "workloads": [workload_payload],
                    "maintenance": None,
                }
            ],
            "load_balancers": [],
            "firewalls": [],
            "dns_records": [],
            "containers": [],
        },
    }


def ensure_plan_for_funnel_publish_workload(
    *,
    workload_patch: dict[str, Any],
    plan_path: str | None,
    instance_name: str | None,
) -> dict[str, Any]:
    requested_plan_path = (plan_path or "").strip()
    if requested_plan_path:
        candidate = _assert_under_cloudhand(Path(requested_plan_path))
        if candidate.exists():
            return {"plan_path": str(candidate), "bootstrapped": False}
        bootstrap_payload = _bootstrap_deploy_plan_payload(
            workload_patch=workload_patch,
            instance_name=instance_name,
        )
        saved = save_plan(content=json.dumps(bootstrap_payload, indent=2), path=str(candidate))
        return {"plan_path": saved["path"], "bootstrapped": True}

    latest = _find_latest_plan()
    if latest and latest.exists():
        return {"plan_path": str(latest), "bootstrapped": False}

    bootstrap_payload = _bootstrap_deploy_plan_payload(
        workload_patch=workload_patch,
        instance_name=instance_name,
    )
    saved = save_plan(content=json.dumps(bootstrap_payload, indent=2))
    return {"plan_path": saved["path"], "bootstrapped": True}


def _load_funnel_runtime_artifact_payload_for_apply(*, artifact_id: str) -> dict[str, Any]:
    from sqlalchemy import select

    from app.db.base import SessionLocal
    from app.db.enums import ArtifactTypeEnum
    from app.db.models import Artifact

    session = SessionLocal()
    try:
        artifact = session.scalars(select(Artifact).where(Artifact.id == artifact_id)).first()
    finally:
        session.close()

    if not artifact:
        raise DeployError(f"Funnel runtime artifact '{artifact_id}' was not found.")
    if artifact.type != ArtifactTypeEnum.funnel_runtime_bundle:
        raise DeployError(
            f"Artifact '{artifact_id}' has type '{artifact.type.value}' but expected '{ArtifactTypeEnum.funnel_runtime_bundle.value}'."
        )
    data = artifact.data
    if not isinstance(data, dict):
        raise DeployError(f"Artifact '{artifact_id}' payload is invalid.")
    if not isinstance(data.get("meta"), dict):
        raise DeployError(f"Artifact '{artifact_id}' payload is missing meta.")
    if not isinstance(data.get("products"), dict):
        raise DeployError(f"Artifact '{artifact_id}' payload is missing products.")
    return data


def _load_product_route_context_for_apply(*, product_id: str) -> tuple[str, str]:
    from sqlalchemy import select

    from app.db.base import SessionLocal
    from app.db.models import Product
    from app.services.public_routing import require_product_route_slug

    try:
        normalized_product_id = str(UUID(str(product_id).strip()))
    except ValueError as exc:
        raise DeployError(
            f"Invalid product_id '{product_id}' in funnel artifact source_ref."
        ) from exc

    session = SessionLocal()
    try:
        product = session.scalars(
            select(Product).where(Product.id == normalized_product_id)
        ).first()
    finally:
        session.close()

    if not product:
        raise DeployError(
            f"Product '{normalized_product_id}' referenced by funnel artifact workload was not found."
        )
    return str(product.client_id), require_product_route_slug(product=product)


def _normalize_legacy_publication_source_ref_for_apply(*, workload: dict[str, Any]) -> bool:
    name = str(workload.get("name") or "").strip() or "<unnamed>"
    source_ref = workload.get("source_ref")
    if not isinstance(source_ref, dict):
        raise DeployError(
            f"Workload '{name}' source_ref must be an object for source_type='funnel_publication'."
        )

    changed = False
    public_id = str(source_ref.get("public_id") or "").strip()
    if not public_id:
        raise DeployError(
            f"Workload '{name}' uses source_type='funnel_publication' but source_ref.public_id is missing."
        )

    upstream_base_url = str(source_ref.get("upstream_base_url") or "").strip().rstrip("/")
    if not upstream_base_url:
        upstream_base_url = str(settings.DEPLOY_PUBLIC_BASE_URL or "").strip().rstrip("/")
        if not upstream_base_url:
            legacy_api = str(source_ref.get("upstream_api_base_url") or "").strip().rstrip("/")
            if legacy_api:
                parsed = urlsplit(legacy_api)
                if parsed.scheme and parsed.netloc:
                    upstream_base_url = f"{parsed.scheme}://{parsed.netloc}"
        if not upstream_base_url:
            raise DeployError(
                f"Workload '{name}' is missing source_ref.upstream_base_url. "
                "Set DEPLOY_PUBLIC_BASE_URL or update the plan workload."
            )
        source_ref["upstream_base_url"] = upstream_base_url
        changed = True

    upstream_api_base_url = str(source_ref.get("upstream_api_base_url") or "").strip().rstrip("/")
    if not upstream_api_base_url:
        upstream_api_base_url = str(settings.DEPLOY_PUBLIC_API_BASE_URL or "").strip().rstrip("/")
        if not upstream_api_base_url:
            upstream_api_base_url = f"{upstream_base_url}/api"
        source_ref["upstream_api_base_url"] = upstream_api_base_url
        changed = True

    if not upstream_base_url.startswith(("http://", "https://")):
        raise DeployError(
            f"Workload '{name}' has invalid source_ref.upstream_base_url '{upstream_base_url}'."
        )
    if not upstream_api_base_url.startswith(("http://", "https://")):
        raise DeployError(
            f"Workload '{name}' has invalid source_ref.upstream_api_base_url '{upstream_api_base_url}'."
        )

    if changed:
        workload["source_ref"] = source_ref
    return changed


def _normalize_legacy_artifact_source_ref_for_apply(*, workload: dict[str, Any]) -> bool:
    name = str(workload.get("name") or "").strip() or "<unnamed>"
    source_ref = workload.get("source_ref")
    if not isinstance(source_ref, dict):
        raise DeployError(
            f"Workload '{name}' source_ref must be an object for source_type='funnel_artifact'."
        )

    changed = False
    client_id = str(source_ref.get("client_id") or "").strip()
    product_id = str(source_ref.get("product_id") or "").strip()

    # Legacy fallback path: source_type was historically set to funnel_artifact while carrying
    # publication proxy payload (`public_id`) without artifact references.
    if not client_id and not product_id and str(source_ref.get("public_id") or "").strip():
        workload["source_type"] = "funnel_publication"
        changed |= _normalize_legacy_publication_source_ref_for_apply(workload=workload)
        return True

    if not client_id:
        if product_id:
            resolved_client_id, _ = _load_product_route_context_for_apply(product_id=product_id)
            source_ref["client_id"] = resolved_client_id
            client_id = resolved_client_id
            changed = True
        else:
            artifact = source_ref.get("artifact")
            if isinstance(artifact, dict):
                meta = artifact.get("meta")
                if isinstance(meta, dict):
                    meta_client_id = str(
                        meta.get("clientId") or meta.get("client_id") or ""
                    ).strip()
                    if meta_client_id:
                        source_ref["client_id"] = meta_client_id
                        client_id = meta_client_id
                        changed = True

    if not client_id:
        raise DeployError(
            f"Workload '{name}' uses source_type='funnel_artifact' but source_ref.client_id is missing."
        )

    upstream_api_base_root = str(source_ref.get("upstream_api_base_root") or "").strip().rstrip("/")
    if not upstream_api_base_root:
        legacy_api = (
            str(
                source_ref.get("upstream_api_base_url") or settings.DEPLOY_PUBLIC_API_BASE_URL or ""
            )
            .strip()
            .rstrip("/")
        )
        if not legacy_api:
            raise DeployError(
                f"Workload '{name}' is missing source_ref.upstream_api_base_root. "
                "Set DEPLOY_PUBLIC_API_BASE_URL or update the plan workload."
            )
        source_ref["upstream_api_base_root"] = legacy_api
        upstream_api_base_root = legacy_api
        changed = True

    if not upstream_api_base_root.startswith(("http://", "https://")):
        raise DeployError(
            f"Workload '{name}' has invalid source_ref.upstream_api_base_root '{upstream_api_base_root}'."
        )

    explicit_render_mode = source_ref.get("artifact_render_mode")
    raw_render_mode = str(
        explicit_render_mode or _FUNNEL_ARTIFACT_RENDER_MODE_RUNTIME_BUNDLE
    ).strip().lower()
    if raw_render_mode not in {
        _FUNNEL_ARTIFACT_RENDER_MODE_RUNTIME_BUNDLE,
        _FUNNEL_ARTIFACT_RENDER_MODE_STANDALONE_IMPORTED_HTML,
    }:
        raise DeployError(
            f"Workload '{name}' has invalid source_ref.artifact_render_mode '{raw_render_mode}'."
        )
    if explicit_render_mode is not None and explicit_render_mode != raw_render_mode:
        source_ref["artifact_render_mode"] = raw_render_mode
        changed = True

    if raw_render_mode == _FUNNEL_ARTIFACT_RENDER_MODE_STANDALONE_IMPORTED_HTML:
        normalized_api_origin = _require_standalone_upstream_api_origin(
            upstream_api_base_url=upstream_api_base_root
        )
        if normalized_api_origin != upstream_api_base_root:
            source_ref["upstream_api_base_root"] = normalized_api_origin
            upstream_api_base_root = normalized_api_origin
            changed = True

    runtime_dist_path = str(source_ref.get("runtime_dist_path") or "").strip()
    if raw_render_mode == _FUNNEL_ARTIFACT_RENDER_MODE_RUNTIME_BUNDLE:
        if not runtime_dist_path:
            source_ref["runtime_dist_path"] = settings.DEPLOY_ARTIFACT_RUNTIME_DIST_PATH
            changed = True
    elif "runtime_dist_path" in source_ref:
        source_ref.pop("runtime_dist_path", None)
        changed = True

    artifact = source_ref.get("artifact")
    if not isinstance(artifact, dict):
        raise DeployError(
            f"Workload '{name}' source_ref.artifact must be an object for source_type='funnel_artifact'."
        )

    if not isinstance(artifact.get("meta"), dict):
        artifact["meta"] = {}
        changed = True

    if not isinstance(artifact.get("products"), dict):
        legacy_funnels = artifact.get("funnels")
        if isinstance(legacy_funnels, dict):
            if not product_id:
                meta = artifact.get("meta")
                if isinstance(meta, dict):
                    product_id = str(meta.get("productId") or meta.get("product_id") or "").strip()
            if not product_id:
                raise DeployError(
                    f"Workload '{name}' has legacy source_ref.artifact.funnels but source_ref.product_id is missing."
                )
            _resolved_client_id, product_slug = _load_product_route_context_for_apply(
                product_id=product_id
            )
            artifact["products"] = {
                product_slug: {
                    "meta": {
                        "productId": product_id,
                        "productSlug": product_slug,
                    },
                    "funnels": legacy_funnels,
                }
            }
            changed = True
        else:
            artifact["products"] = {}
            changed = True

    source_ref["artifact"] = artifact
    workload["source_ref"] = source_ref
    return changed


def _materialize_funnel_artifacts_for_apply(
    *, plan_file: Path, workload_names: set[str] | None = None
) -> Path:
    try:
        plan = json.loads(plan_file.read_text(encoding="utf-8"))
    except Exception as exc:
        raise DeployError(f"Failed to read plan JSON: {exc}") from exc

    new_spec = plan.get("new_spec")
    if not isinstance(new_spec, dict):
        raise DeployError("Plan new_spec must be an object.")
    instances = new_spec.get("instances")
    if not isinstance(instances, list):
        raise DeployError("Plan new_spec.instances must be a list.")

    has_changes = False
    for inst in instances:
        if not isinstance(inst, dict):
            continue
        workloads = inst.get("workloads")
        if not isinstance(workloads, list):
            continue
        for workload in workloads:
            if not isinstance(workload, dict):
                continue
            workload_name = str(workload.get("name") or "").strip()
            if workload_names and workload_name not in workload_names:
                continue
            source_type = str(workload.get("source_type") or "").strip().lower()
            if source_type == "funnel_publication":
                if _normalize_legacy_publication_source_ref_for_apply(workload=workload):
                    has_changes = True
                continue
            if source_type != "funnel_artifact":
                continue
            if _normalize_legacy_artifact_source_ref_for_apply(workload=workload):
                has_changes = True
            source_ref = workload.get("source_ref")
            if not isinstance(source_ref, dict):
                raise DeployError(
                    f"Workload '{workload.get('name')}' source_ref must be an object for source_type='funnel_artifact'."
                )
            artifact_id = str(source_ref.get("artifact_id") or "").strip()
            if not artifact_id:
                # Some existing plans may carry placeholder inline artifacts with no DB artifact
                # reference yet. Leave those unchanged here.
                continue
            artifact_payload = _load_funnel_runtime_artifact_payload_for_apply(
                artifact_id=artifact_id
            )
            raw_render_mode = str(source_ref.get("artifact_render_mode") or "").strip().lower()
            if not raw_render_mode:
                inferred_render_mode = (
                    _FUNNEL_ARTIFACT_RENDER_MODE_STANDALONE_IMPORTED_HTML
                    if _artifact_payload_supports_standalone_imported_html(
                        artifact_payload=artifact_payload
                    )
                    else _FUNNEL_ARTIFACT_RENDER_MODE_RUNTIME_BUNDLE
                )
                source_ref["artifact_render_mode"] = inferred_render_mode
                raw_render_mode = inferred_render_mode
                has_changes = True

            if raw_render_mode == _FUNNEL_ARTIFACT_RENDER_MODE_STANDALONE_IMPORTED_HTML:
                if "runtime_dist_path" in source_ref:
                    source_ref.pop("runtime_dist_path", None)
                    has_changes = True
            elif not str(source_ref.get("runtime_dist_path") or "").strip():
                source_ref["runtime_dist_path"] = settings.DEPLOY_ARTIFACT_RUNTIME_DIST_PATH
                has_changes = True

            if source_ref.get("artifact") != artifact_payload:
                source_ref["artifact"] = artifact_payload
                workload["source_ref"] = source_ref
                has_changes = True

    if not has_changes:
        return plan_file

    materialized_path = (
        _cloudhand_dir()
        / f"apply-materialized-{datetime.utcnow().strftime('%Y-%m-%dT%H-%M-%SZ')}-{uuid4().hex[:8]}.json"
    )
    try:
        materialized_path.write_text(json.dumps(plan, indent=2), encoding="utf-8")
    except Exception as exc:
        raise DeployError(f"Failed to write materialized apply plan: {exc}") from exc
    return materialized_path


async def apply_plan(
    *, plan_path: str | None = None, workload_names: list[str] | None = None
) -> dict[str, Any]:
    """
    Apply a plan using the embedded Cloudhand engine (Terraform + SSH deploy).

    Mirrors the control-plane behavior: writes state under DEPLOY_ROOT_DIR and returns
    consolidated logs + server IPs (when available).
    """

    # Token is required for Terraform provider auth. We keep it simple for now:
    # require a process env var so it never needs to traverse the UI.
    if not os.getenv("HCLOUD_TOKEN") and not os.getenv("TF_VAR_hcloud_token"):
        raise DeployError("HCLOUD_TOKEN is not set. Terraform apply cannot run.")

    ch_dir = _cloudhand_dir()
    tf_dir = _terraform_dir()
    ch_dir.mkdir(parents=True, exist_ok=True)

    # Pick plan file
    if plan_path:
        plan_file = _assert_under_cloudhand(Path(plan_path))
    else:
        plan_file = _find_latest_plan()

    if not plan_file or not plan_file.exists():
        raise DeployError("No plan found.")

    requested_plan_file = plan_file
    normalized_workload_names: list[str] = []
    selected_workload_names: set[str] = set()
    for raw_name in workload_names or []:
        workload_name = str(raw_name or "").strip()
        if not workload_name or workload_name in selected_workload_names:
            continue
        selected_workload_names.add(workload_name)
        normalized_workload_names.append(workload_name)
    plan_file = _materialize_funnel_artifacts_for_apply(
        plan_file=plan_file,
        workload_names=(selected_workload_names or None),
    )

    # Run Cloudhand apply in a subprocess so we can stream/capture Terraform output.
    env = os.environ.copy()
    project_id = settings.DEPLOY_PROJECT_ID
    terraform_bin = _resolve_terraform_bin()

    cmd = [
        sys.executable,
        "-u",
        "-m",
        "cloudhand.cli",
        "--project",
        project_id,
        "apply",
        str(plan_file),
        "--auto-approve",
        "--terraform-bin",
        terraform_bin,
    ]
    for workload_name in normalized_workload_names:
        cmd.extend(["--workload-name", workload_name])

    proc = await asyncio.create_subprocess_exec(
        *cmd,
        # Cloudhand assumes the project root is cwd and uses ./cloudhand/ for artifacts/state.
        cwd=str(_cloudhand_dir().parent),
        env=env,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.STDOUT,
        start_new_session=True,
    )

    logs: list[str] = []
    reader_task = asyncio.create_task(_collect_subprocess_output(proc.stdout, logs=logs))
    timeout_seconds = _deploy_apply_timeout_seconds()
    try:
        if timeout_seconds is None:
            rc = await proc.wait()
        else:
            rc = await asyncio.wait_for(proc.wait(), timeout=timeout_seconds)
    except asyncio.TimeoutError as exc:
        logs.append(
            f"Error: Cloudhand apply timed out after {int(timeout_seconds)} seconds "
            f"for plan '{requested_plan_file}'.\n"
        )
        await _terminate_subprocess(proc)
        raise DeployError(
            f"Cloudhand apply timed out after {int(timeout_seconds)} seconds."
        ) from exc
    finally:
        await reader_task

    # Try to read terraform outputs for convenience
    server_ips: dict[str, str] = {}
    live_url: Optional[str] = None
    tf_out: dict[str, Any] = {}

    if tf_dir.exists():
        try:
            proc2 = await asyncio.create_subprocess_exec(
                terraform_bin,
                "output",
                "-json",
                cwd=str(tf_dir),
                env=env,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            out, err = await proc2.communicate()
            if proc2.returncode == 0:
                tf_out = json.loads(out.decode() or "{}")
            else:
                logs.append(f"Warning: terraform output failed: {err.decode(errors='ignore')}\n")
        except Exception as exc:  # pragma: no cover
            logs.append(f"Warning: failed to read terraform outputs: {exc}\n")

    if isinstance(tf_out.get("server_ips"), dict):
        val = tf_out["server_ips"].get("value")
        if isinstance(val, dict):
            # best-effort type narrowing
            server_ips = {str(k): str(v) for k, v in val.items()}
            if server_ips:
                live_url = f"http://{next(iter(server_ips.values()))}"

    return {
        "returncode": rc,
        "plan_path": str(requested_plan_file),
        "materialized_plan_path": str(plan_file),
        "server_ips": server_ips,
        "live_url": live_url,
        "logs": "".join(logs),
    }


def _normalize_access_urls(urls: list[str] | None) -> list[str]:
    out: list[str] = []
    seen: set[str] = set()
    for raw in urls or []:
        if not isinstance(raw, str):
            continue
        url = raw.strip()
        if not url:
            continue
        if url in seen:
            continue
        seen.add(url)
        out.append(url)
    return out


def _normalize_bunny_pull_zone_name_component(*, value: str, label: str) -> str:
    normalized = re.sub(r"[^a-z0-9-]+", "-", (value or "").strip().lower())
    normalized = re.sub(r"-{2,}", "-", normalized).strip("-")
    if not normalized:
        raise DeployError(
            f"Bunny pull zone name component '{label}' is empty after normalization. "
            f"Received value='{value}'."
        )
    return normalized


def _build_bunny_pull_zone_name(*, client_id: str, workload_name: str) -> str:
    _ = _normalize_bunny_pull_zone_name_component(
        value=client_id,
        label="client_id",
    )
    workload_component = _normalize_bunny_pull_zone_name_component(
        value=workload_name,
        label="workload_name",
    )
    return workload_component


def _resolve_bunny_pull_zone_client_id(*, client_id: str) -> str:
    resolved_client_id = str(client_id or "").strip()
    if not resolved_client_id:
        raise DeployError("client_id is required for Bunny pull zone provisioning.")
    return resolved_client_id


def _bunny_api_request(*, method: str, path: str, payload: dict[str, Any] | None = None) -> Any:
    api_key = str(settings.BUNNY_API_KEY or "").strip()
    if not api_key:
        raise DeployError("Bunny pull zone provisioning requires BUNNY_API_KEY.")

    base_url = str(settings.BUNNY_API_BASE_URL or "").strip().rstrip("/")
    if not base_url:
        raise DeployError("BUNNY_API_BASE_URL must be configured for Bunny pull zone provisioning.")

    normalized_method = (method or "").strip().upper()
    if not normalized_method:
        raise DeployError("Bunny API request method is required.")

    endpoint = f"{base_url}/{path.lstrip('/')}"
    try:
        with httpx.Client(timeout=30.0) as client:
            response = client.request(
                normalized_method,
                endpoint,
                headers={"AccessKey": api_key, "Content-Type": "application/json"},
                json=payload,
            )
    except httpx.HTTPError as exc:
        raise DeployError(f"Bunny API request failed ({normalized_method} {path}): {exc}") from exc

    if response.status_code >= 400:
        detail = response.text.strip()
        try:
            body = response.json()
        except ValueError:
            body = None
        if isinstance(body, dict):
            message = (
                body.get("Message")
                or body.get("Error")
                or body.get("detail")
                or body.get("message")
            )
            if isinstance(message, str) and message.strip():
                detail = message.strip()
            elif not detail:
                detail = json.dumps(body, ensure_ascii=True)
        elif not detail:
            detail = "<empty response body>"
        raise DeployError(
            f"Bunny API request failed ({normalized_method} {path}) "
            f"with status {response.status_code}: {detail}"
        )

    if not response.content:
        return None
    try:
        return response.json()
    except ValueError as exc:
        raise DeployError(
            f"Bunny API request returned non-JSON response ({normalized_method} {path})."
        ) from exc


def _list_bunny_pull_zones() -> list[dict[str, Any]]:
    payload = _bunny_api_request(method="GET", path="/pullzone")
    items: Any
    if isinstance(payload, dict):
        items = payload.get("Items")
    elif isinstance(payload, list):
        # Some Bunny accounts/environments return the collection directly.
        items = payload
    else:
        raise DeployError(
            "Bunny list pull zones response must be an object with Items or an array."
        )
    if not isinstance(items, list):
        raise DeployError("Bunny list pull zones response must contain an array of pull zones.")
    zones: list[dict[str, Any]] = []
    for idx, item in enumerate(items):
        if not isinstance(item, dict):
            raise DeployError(f"Bunny list pull zones response item at index {idx} is invalid.")
        zones.append(item)
    return zones


def _find_bunny_pull_zone_by_name(*, zone_name: str) -> dict[str, Any] | None:
    normalized_target = zone_name.strip().lower()
    matches: list[dict[str, Any]] = []
    for zone in _list_bunny_pull_zones():
        candidate = str(zone.get("Name") or "").strip().lower()
        if candidate == normalized_target:
            matches.append(zone)
    if len(matches) > 1:
        raise DeployError(f"Multiple Bunny pull zones found for name '{zone_name}'.")
    return matches[0] if matches else None


def _find_bunny_pull_zone_by_hostname(*, hostname: str) -> dict[str, Any] | None:
    normalized_target = _normalize_hostname(value=hostname, context="Bunny custom domain")
    matches: list[dict[str, Any]] = []
    for zone in _list_bunny_pull_zones():
        hostnames = _extract_bunny_pull_zone_hostname_values(zone)
        if normalized_target in hostnames:
            matches.append(zone)
    if len(matches) > 1:
        raise DeployError(f"Multiple Bunny pull zones found for hostname '{normalized_target}'.")
    return matches[0] if matches else None


def _resolve_existing_bunny_pull_zone_for_hostnames(
    *,
    server_names: list[str] | None,
) -> dict[str, Any] | None:
    normalized_server_names = _normalize_workload_server_names(server_names=server_names or [])
    if not normalized_server_names:
        return None

    matched_zones: dict[int, dict[str, Any]] = {}
    matched_hostnames_by_zone: dict[int, list[str]] = {}
    for hostname in normalized_server_names:
        zone = _find_bunny_pull_zone_by_hostname(hostname=hostname)
        if zone is None:
            continue
        zone_id = _coerce_bunny_pull_zone_id(zone=zone)
        matched_zones[zone_id] = zone
        matched_hostnames_by_zone.setdefault(zone_id, []).append(hostname)

    if not matched_zones:
        return None
    if len(matched_zones) > 1:
        zone_descriptions: list[str] = []
        for zone_id, zone in sorted(matched_zones.items()):
            zone_name = str(zone.get("Name") or "").strip() or str(zone_id)
            hostnames = ", ".join(sorted(matched_hostnames_by_zone.get(zone_id, [])))
            zone_descriptions.append(f"{zone_name} (id={zone_id}; hostnames={hostnames})")
        raise DeployError(
            "Bunny custom domains for this workload already exist on multiple pull zones: "
            + "; ".join(zone_descriptions)
            + ". Consolidate the domains onto a single pull zone before retrying."
        )
    return next(iter(matched_zones.values()))


def _coerce_bunny_pull_zone_id(*, zone: dict[str, Any]) -> int:
    raw_id = zone.get("Id")
    try:
        zone_id = int(raw_id)
    except Exception as exc:
        raise DeployError("Bunny pull zone payload is missing a valid Id.") from exc
    if zone_id <= 0:
        raise DeployError("Bunny pull zone Id must be greater than zero.")
    return zone_id


def _normalize_hostname(*, value: str, context: str) -> str:
    normalized = (value or "").strip().lower().rstrip(".")
    if not normalized:
        raise DeployError(f"{context} hostname is required.")
    if "://" in normalized or "/" in normalized or "?" in normalized or "#" in normalized:
        raise DeployError(
            f"{context} hostname '{value}' is invalid. Use a bare hostname (for example: shop.example.com)."
        )
    if not _HOSTNAME_RE.match(normalized):
        raise DeployError(f"{context} hostname '{value}' is invalid.")
    return normalized


def _normalize_workload_server_names(*, server_names: list[str]) -> list[str]:
    out: list[str] = []
    seen: set[str] = set()
    for raw in server_names:
        hostname = _normalize_hostname(value=raw, context="Workload")
        if hostname in seen:
            continue
        seen.add(hostname)
        out.append(hostname)
    return out


def _resolve_publish_job_workspace_server_names(
    *,
    session: Any,
    org_id: str,
    workload_client_id: str,
    workload_patch: dict[str, Any],
) -> list[str]:
    from app.db.repositories.org_deploy_domains import OrgDeployDomainsRepository

    raw_workspace_server_names = workload_patch.get("workspace_server_names")
    if raw_workspace_server_names is not None:
        if not isinstance(raw_workspace_server_names, list):
            raise DeployError("Publish deploy workload workspace_server_names must be a list.")
        normalized = _normalize_workload_server_names(server_names=raw_workspace_server_names)
        if normalized:
            return normalized

    return OrgDeployDomainsRepository(session).list_hostnames(
        org_id=org_id,
        client_id=workload_client_id,
    )


def _extract_bunny_pull_zone_hostname_values(zone: dict[str, Any]) -> list[str]:
    hostnames = zone.get("Hostnames")
    if hostnames is None:
        return []
    if not isinstance(hostnames, list):
        raise DeployError(
            "Bunny pull zone response field Hostnames must be an array when provided."
        )

    values: list[str] = []
    seen: set[str] = set()
    for idx, hostname in enumerate(hostnames):
        if not isinstance(hostname, dict):
            raise DeployError(f"Bunny pull zone hostname at index {idx} is invalid.")
        value = str(hostname.get("Value") or "").strip().lower()
        if not value:
            continue
        if value in seen:
            continue
        seen.add(value)
        values.append(value)
    return values


def _extract_bunny_pull_zone_dns_target_hostname(zone: dict[str, Any]) -> str:
    hostname_values = _extract_bunny_pull_zone_hostname_values(zone)
    for value in hostname_values:
        if value.endswith(".b-cdn.net"):
            return value
    raise DeployError(
        "Bunny pull zone response does not include a default '*.b-cdn.net' hostname for CNAME target."
    )


def _get_bunny_pull_zone(*, zone_id: int) -> dict[str, Any]:
    payload = _bunny_api_request(method="GET", path=f"/pullzone/{zone_id}")
    if not isinstance(payload, dict):
        raise DeployError("Bunny get pull zone response must be an object.")
    return payload


def _ensure_bunny_pull_zone_hostname(*, zone_id: int, hostname: str) -> dict[str, Any]:
    normalized_hostname = _normalize_hostname(value=hostname, context="Bunny custom domain")
    zone = _get_bunny_pull_zone(zone_id=zone_id)
    existing = _extract_bunny_pull_zone_hostname_values(zone)
    if normalized_hostname in existing:
        return {"hostname": normalized_hostname, "status": "existing"}

    registered_zone = _find_bunny_pull_zone_by_hostname(hostname=normalized_hostname)
    if registered_zone is not None:
        registered_zone_id = _coerce_bunny_pull_zone_id(zone=registered_zone)
        if registered_zone_id == zone_id:
            return {"hostname": normalized_hostname, "status": "existing"}
        registered_zone_name = str(registered_zone.get("Name") or "").strip() or str(
            registered_zone_id
        )
        raise DeployError(
            f"Bunny custom domain '{normalized_hostname}' is already registered to pull zone "
            f"'{registered_zone_name}' (id={registered_zone_id}), not target zone id={zone_id}."
        )

    try:
        response = _bunny_api_request(
            method="POST",
            path=f"/pullzone/{zone_id}/addHostname",
            payload={"Hostname": normalized_hostname},
        )
    except DeployError as exc:
        if "already registered" not in str(exc).lower():
            raise
        reconciled_zone = _get_bunny_pull_zone(zone_id=zone_id)
        reconciled_hostnames = _extract_bunny_pull_zone_hostname_values(reconciled_zone)
        if normalized_hostname in reconciled_hostnames:
            return {"hostname": normalized_hostname, "status": "existing"}
        registered_zone = _find_bunny_pull_zone_by_hostname(hostname=normalized_hostname)
        if registered_zone is not None:
            registered_zone_id = _coerce_bunny_pull_zone_id(zone=registered_zone)
            if registered_zone_id == zone_id:
                return {"hostname": normalized_hostname, "status": "existing"}
            registered_zone_name = str(registered_zone.get("Name") or "").strip() or str(
                registered_zone_id
            )
            raise DeployError(
                f"Bunny custom domain '{normalized_hostname}' is already registered to pull zone "
                f"'{registered_zone_name}' (id={registered_zone_id}), not target zone id={zone_id}."
            ) from exc
        raise DeployError(
            f"Bunny reported hostname '{normalized_hostname}' is already registered, but it was not "
            "present on the target pull zone or any listed pull zone. Retry after Bunny propagates "
            "or inspect the Bunny dashboard."
        ) from exc
    if response is not None and not isinstance(response, (dict, bool, str)):
        raise DeployError(
            "Bunny add hostname response must be an object, bool, or string when present."
        )
    return {"hostname": normalized_hostname, "status": "created"}


def _ensure_bunny_pull_zone_auto_ssl_enabled(*, zone_id: int) -> None:
    response = _bunny_api_request(
        method="POST",
        path=f"/pullzone/{zone_id}",
        payload={"EnableAutoSSL": True, "DisableLetsEncrypt": False},
    )
    if response is not None and not isinstance(response, (dict, bool, str)):
        raise DeployError(
            "Bunny pull zone SSL update response must be an object, bool, or string when present."
        )


def _request_bunny_pull_zone_certificate(*, zone_id: int, hostname: str) -> dict[str, Any] | None:
    _ = zone_id
    normalized_hostname = _normalize_hostname(value=hostname, context="Bunny certificate")
    response = _bunny_api_request(
        method="GET",
        path=f"/pullzone/loadFreeCertificate?hostname={quote(normalized_hostname, safe='')}",
    )
    if response is None:
        return None
    if isinstance(response, dict):
        return response
    if isinstance(response, bool):
        return {"ok": response}
    if isinstance(response, str):
        return {"message": response}
    raise DeployError(
        "Bunny free certificate response must be an object, bool, or string when present."
    )


def _provision_bunny_custom_domains(
    *,
    bunny_zone: dict[str, Any],
    server_names: list[str],
    request_ssl: bool = True,
) -> dict[str, Any]:
    normalized_server_names = _normalize_workload_server_names(server_names=server_names)
    if not normalized_server_names:
        return {
            "dnsTargetHostname": None,
            "domains": [],
            "pullZoneHostnames": _extract_bunny_pull_zone_hostname_values(bunny_zone),
        }

    zone_id = _coerce_bunny_pull_zone_id(zone=bunny_zone)
    dns_target_hostname = _extract_bunny_pull_zone_dns_target_hostname(bunny_zone)
    if request_ssl:
        _ensure_bunny_pull_zone_auto_ssl_enabled(zone_id=zone_id)

    domain_results: list[dict[str, Any]] = []
    for hostname in normalized_server_names:
        try:
            dns_record = namecheap_dns_service.upsert_cname_record(
                hostname=hostname,
                target_hostname=dns_target_hostname,
            )
        except namecheap_dns_service.NamecheapDnsError as exc:
            raise DeployError(str(exc)) from exc

        hostname_result = _ensure_bunny_pull_zone_hostname(zone_id=zone_id, hostname=hostname)
        certificate_result: dict[str, Any] | None = None
        ssl_status = "pending_publish"
        if request_ssl:
            certificate_result = _request_bunny_pull_zone_certificate(
                zone_id=zone_id, hostname=hostname
            )
            ssl_status = "requested"
        domain_results.append(
            {
                "hostname": hostname,
                "dns": dns_record,
                "bunnyHostname": hostname_result,
                "ssl": {
                    "provider": "bunny",
                    "status": ssl_status,
                    "certificateRequest": certificate_result,
                },
            }
        )

    refreshed_zone = _get_bunny_pull_zone(zone_id=zone_id)
    return {
        "dnsTargetHostname": dns_target_hostname,
        "domains": domain_results,
        "pullZoneHostnames": _extract_bunny_pull_zone_hostname_values(refreshed_zone),
    }


def _resolve_bunny_pull_zone_origin_url(
    *,
    requested_origin_ip: Any,
    workload_port: int | None = None,
) -> str:
    requested = str(requested_origin_ip or "").strip()
    configured_default = str(settings.BUNNY_PULLZONE_ORIGIN_IP or "").strip()
    origin_input = requested or configured_default
    resolved_port: int | None = None
    if workload_port is not None:
        resolved_port = _coerce_service_port(raw_port=workload_port, context="Workload")

    if not origin_input:
        raise DeployError(
            "Bunny pull zone origin IP is required. "
            "Set deploy.bunnyPullZoneOriginIp or BUNNY_PULLZONE_ORIGIN_IP."
        )

    if origin_input.startswith(("http://", "https://")):
        parsed = urlsplit(origin_input)
        if not parsed.scheme or not parsed.netloc:
            raise DeployError("Bunny pull zone origin URL is invalid. Expected http(s)://<host>.")
        return origin_input.rstrip("/")

    if " " in origin_input or "/" in origin_input:
        raise DeployError("Bunny pull zone origin must be a bare host/IP or a full http(s) URL.")
    if resolved_port is not None and ":" not in origin_input:
        return f"http://{origin_input}:{resolved_port}"
    return f"http://{origin_input}"


def _extract_bunny_pull_zone_access_urls(zone: dict[str, Any]) -> list[str]:
    urls: list[str] = []
    for value in _extract_bunny_pull_zone_hostname_values(zone):
        urls.append(f"https://{value}/")
    return _normalize_access_urls(urls)


def _resolve_bunny_origin_context_for_workload(
    *,
    workload: dict[str, Any],
    workload_name: str,
    instance_name: str | None,
    resolve_port_from_latest_spec: bool,
    require_port_when_no_domains: bool,
) -> tuple[list[str], int | None, str | None]:
    server_names = _extract_workload_server_names(
        workload=workload,
        context=f"Workload '{workload_name}'",
    )
    workload_port = _extract_primary_service_port(
        workload=workload,
        context=f"Workload '{workload_name}'",
    )
    workload_port_source: str | None = "plan" if workload_port is not None else None

    if workload_port is None and not server_names and resolve_port_from_latest_spec:
        try:
            workload_port = _workload_port_from_latest_spec(
                workload_name=workload_name,
                instance_name=instance_name,
            )
            workload_port_source = "spec"
        except DeployError as exc:
            if require_port_when_no_domains:
                raise DeployError(
                    f"Workload '{workload_name}' has no server_names and no assigned service port "
                    "after apply; cannot build Bunny pull zone origin URL."
                ) from exc

    if workload_port is None and not server_names and require_port_when_no_domains:
        raise DeployError(
            f"Workload '{workload_name}' has no server_names and no assigned service port; "
            "cannot build Bunny pull zone origin URL."
        )

    return server_names, workload_port, workload_port_source


def _ensure_bunny_pull_zone(
    *,
    client_id: str,
    workload_name: str,
    origin_url: str,
    server_names: list[str] | None = None,
) -> dict[str, Any]:
    zone_name = _build_bunny_pull_zone_name(client_id=client_id, workload_name=workload_name)
    existing_zone_by_name = _find_bunny_pull_zone_by_name(zone_name=zone_name)
    existing_zone_by_hostname = _resolve_existing_bunny_pull_zone_for_hostnames(
        server_names=server_names,
    )
    existing_zone = existing_zone_by_hostname or existing_zone_by_name

    zone: dict[str, Any]
    if existing_zone is None:
        created = _bunny_api_request(
            method="POST",
            path="/pullzone",
            payload={"Name": zone_name, "OriginUrl": origin_url},
        )
        if not isinstance(created, dict):
            raise DeployError("Bunny create pull zone response must be an object.")
        zone = created
    else:
        existing_zone_id = _coerce_bunny_pull_zone_id(zone=existing_zone)
        current_origin = str(existing_zone.get("OriginUrl") or "").strip()
        if current_origin != origin_url:
            updated = _bunny_api_request(
                method="POST",
                path=f"/pullzone/{existing_zone_id}",
                payload={"OriginUrl": origin_url},
            )
            if not isinstance(updated, dict):
                raise DeployError("Bunny update pull zone response must be an object.")
            zone = updated
        else:
            zone = existing_zone

    if not isinstance(zone.get("Hostnames"), list):
        zone_id = _coerce_bunny_pull_zone_id(zone=zone)
        return _get_bunny_pull_zone(zone_id=zone_id)
    return zone


def _purge_bunny_pull_zone_cache(*, zone_id: int, cache_tag: str | None = None) -> dict[str, Any]:
    if zone_id <= 0:
        raise DeployError("Bunny pull zone Id must be greater than zero.")

    payload: dict[str, Any] | None = None
    normalized_cache_tag = str(cache_tag or "").strip()
    if normalized_cache_tag:
        payload = {"CacheTag": normalized_cache_tag}

    response = _bunny_api_request(
        method="POST",
        path=f"/pullzone/{zone_id}/purgeCache",
        payload=payload,
    )
    if response is not None and not isinstance(response, (dict, bool, str)):
        raise DeployError(
            "Bunny purge cache response must be an object, bool, or string when present."
        )

    result: dict[str, Any] = {"zoneId": zone_id, "status": "purged"}
    if normalized_cache_tag:
        result["cacheTag"] = normalized_cache_tag
    if isinstance(response, dict) and response:
        result["response"] = response
    elif isinstance(response, bool):
        result["ok"] = response
    elif isinstance(response, str) and response.strip():
        result["message"] = response.strip()
    return result


def _load_workload_from_plan(
    *,
    workload_name: str,
    plan_path: str | None,
    instance_name: str | None,
) -> tuple[dict[str, Any], str]:
    name = (workload_name or "").strip()
    if not name:
        raise DeployError("workload_name is required.")

    base_plan_path = _assert_under_cloudhand(Path(plan_path)) if plan_path else _find_latest_plan()
    if not base_plan_path or not base_plan_path.exists():
        raise DeployError("No plan found.")

    try:
        plan = json.loads(base_plan_path.read_text(encoding="utf-8"))
    except Exception as exc:
        raise DeployError(f"Failed to read plan JSON: {exc}") from exc

    new_spec = plan.get("new_spec") or {}
    instances = new_spec.get("instances") or []
    if not isinstance(instances, list):
        raise DeployError("Plan new_spec.instances must be a list.")

    matches: list[dict[str, Any]] = []
    for inst in instances:
        if instance_name and inst.get("name") != instance_name:
            continue
        workloads = inst.get("workloads") or []
        if not isinstance(workloads, list):
            continue
        for workload in workloads:
            if not isinstance(workload, dict):
                continue
            if (workload.get("name") or "").strip() != name:
                continue
            matches.append(workload)

    if not matches:
        raise DeployError(f"No workload named '{name}' found in plan.")
    if len(matches) > 1 and not (instance_name or "").strip():
        raise DeployError(
            f"Multiple workloads named '{name}' found in plan. Specify instance_name."
        )
    return matches[0], str(base_plan_path)


def _resolve_workload_client_id(*, workload: dict[str, Any], workload_name: str) -> str:
    source_ref = workload.get("source_ref")
    if not isinstance(source_ref, dict):
        raise DeployError(
            f"Workload '{workload_name}' source_ref must be an object to resolve the workspace-scoped deploy domain."
        )

    client_id = str(source_ref.get("client_id") or "").strip()
    if client_id:
        return client_id

    artifact = source_ref.get("artifact")
    if isinstance(artifact, dict):
        meta = artifact.get("meta")
        if isinstance(meta, dict):
            meta_client_id = str(meta.get("clientId") or meta.get("client_id") or "").strip()
            if meta_client_id:
                return meta_client_id

    raise DeployError(
        f"Workload '{workload_name}' is missing source_ref.client_id and cannot resolve its workspace scope."
    )


def get_workload_workspace_id_from_plan(
    *,
    workload_name: str,
    plan_path: str | None = None,
    instance_name: str | None = None,
) -> str:
    workload, _resolved_plan_path = _load_workload_from_plan(
        workload_name=workload_name,
        plan_path=plan_path,
        instance_name=instance_name,
    )
    return _resolve_workload_client_id(workload=workload, workload_name=workload_name)


def configure_bunny_pull_zone_for_workload(
    *,
    client_id: str,
    workload_name: str,
    plan_path: str | None,
    instance_name: str | None,
    requested_origin_ip: str | None = None,
    server_names: list[str] | None = None,
) -> dict[str, Any]:
    workload, resolved_plan_path = _load_workload_from_plan(
        workload_name=workload_name,
        plan_path=plan_path,
        instance_name=instance_name,
    )

    source_type = str(workload.get("source_type") or "").strip().lower()
    if source_type != "funnel_artifact":
        raise DeployError(
            "Bunny pull zone provisioning from deploy domain save requires source_type 'funnel_artifact'."
        )
    workload_client_id = _resolve_workload_client_id(workload=workload, workload_name=workload_name)
    resolved_client_id = _resolve_bunny_pull_zone_client_id(client_id=client_id)
    if workload_client_id != resolved_client_id:
        raise DeployError(
            f"Workload '{workload_name}' belongs to workspace '{workload_client_id}', not '{resolved_client_id}'."
        )

    workload_server_names, workload_port, workload_port_source = (
        _resolve_bunny_origin_context_for_workload(
            workload=workload,
            workload_name=workload_name,
            instance_name=instance_name,
            resolve_port_from_latest_spec=False,
            require_port_when_no_domains=False,
        )
    )
    if server_names is not None:
        workload_server_names = _normalize_workload_server_names(server_names=server_names)
    port_pending = bool(not workload_server_names and workload_port is None)
    if port_pending:
        workload_port_source = "pending"

    origin_url = _resolve_bunny_pull_zone_origin_url(
        requested_origin_ip=requested_origin_ip,
        workload_port=workload_port,
    )
    bunny_zone = _ensure_bunny_pull_zone(
        client_id=resolved_client_id,
        workload_name=workload_name,
        origin_url=origin_url,
        server_names=workload_server_names,
    )
    domain_provisioning = _provision_bunny_custom_domains(
        bunny_zone=bunny_zone,
        server_names=workload_server_names,
        request_ssl=False,
    )

    zone_for_access_urls = dict(bunny_zone)
    provisioned_hostnames = domain_provisioning.get("pullZoneHostnames")
    if isinstance(provisioned_hostnames, list):
        zone_for_access_urls["Hostnames"] = [
            {"Value": value} for value in provisioned_hostnames if isinstance(value, str)
        ]
    bunny_access_urls = _extract_bunny_pull_zone_access_urls(zone_for_access_urls)
    return {
        "provider": "bunny",
        "plan_path": resolved_plan_path,
        "pull_zone": {
            "id": bunny_zone.get("Id"),
            "name": bunny_zone.get("Name"),
            "originUrl": bunny_zone.get("OriginUrl"),
            "accessUrls": bunny_access_urls,
            "workloadPort": workload_port,
            "workloadPortSource": workload_port_source,
            "workloadPortPending": port_pending,
            "dnsTargetHostname": domain_provisioning.get("dnsTargetHostname"),
            "domainProvisioning": domain_provisioning.get("domains"),
        },
    }


def _reconcile_bunny_pull_zone_for_published_workload(
    *,
    client_id: str,
    workload_name: str,
    plan_path: str | None,
    instance_name: str | None,
    requested_origin_ip: str | None,
    require_port_when_no_domains: bool,
    server_names: list[str] | None = None,
) -> dict[str, Any]:
    workload, resolved_plan_path = _load_workload_from_plan(
        workload_name=workload_name,
        plan_path=plan_path,
        instance_name=instance_name,
    )

    source_type = str(workload.get("source_type") or "").strip().lower()
    if source_type != "funnel_artifact":
        raise DeployError(
            "Bunny pull zone provisioning from publish requires source_type 'funnel_artifact'."
        )
    workload_client_id = _resolve_workload_client_id(workload=workload, workload_name=workload_name)
    resolved_client_id = _resolve_bunny_pull_zone_client_id(client_id=client_id)
    if workload_client_id != resolved_client_id:
        raise DeployError(
            f"Workload '{workload_name}' belongs to workspace '{workload_client_id}', not '{resolved_client_id}'."
        )

    workload_server_names, workload_port, workload_port_source = (
        _resolve_bunny_origin_context_for_workload(
            workload=workload,
            workload_name=workload_name,
            instance_name=instance_name,
            resolve_port_from_latest_spec=True,
            require_port_when_no_domains=require_port_when_no_domains,
        )
    )
    if server_names is not None:
        workload_server_names = _normalize_workload_server_names(server_names=server_names)

    origin_url = _resolve_bunny_pull_zone_origin_url(
        requested_origin_ip=requested_origin_ip,
        workload_port=workload_port,
    )
    bunny_zone = _ensure_bunny_pull_zone(
        client_id=resolved_client_id,
        workload_name=workload_name,
        origin_url=origin_url,
        server_names=workload_server_names,
    )
    domain_provisioning = _provision_bunny_custom_domains(
        bunny_zone=bunny_zone,
        server_names=workload_server_names,
        request_ssl=True,
    )

    zone_for_access_urls = dict(bunny_zone)
    provisioned_hostnames = domain_provisioning.get("pullZoneHostnames")
    if isinstance(provisioned_hostnames, list):
        zone_for_access_urls["Hostnames"] = [
            {"Value": value} for value in provisioned_hostnames if isinstance(value, str)
        ]
    bunny_access_urls = _extract_bunny_pull_zone_access_urls(zone_for_access_urls)
    return {
        "provider": "bunny",
        "plan_path": resolved_plan_path,
        "pull_zone": {
            "id": bunny_zone.get("Id"),
            "name": bunny_zone.get("Name"),
            "originUrl": bunny_zone.get("OriginUrl"),
            "accessUrls": bunny_access_urls,
            "workloadPort": workload_port,
            "workloadPortSource": workload_port_source,
            "workloadPortPending": bool(not workload_server_names and workload_port is None),
            "dnsTargetHostname": domain_provisioning.get("dnsTargetHostname"),
            "domainProvisioning": domain_provisioning.get("domains"),
        },
    }


def _latest_spec_path() -> Path:
    return _cloudhand_dir() / "spec.json"


def _workload_port_from_latest_spec(*, workload_name: str, instance_name: str | None) -> int:
    spec_path = _latest_spec_path()
    if not spec_path.exists():
        raise DeployError(
            "Cloudhand spec.json was not found after apply; cannot determine deployed workload port."
        )

    try:
        payload = json.loads(spec_path.read_text(encoding="utf-8"))
    except Exception as exc:
        raise DeployError(f"Failed to read Cloudhand spec.json: {exc}") from exc

    if isinstance(payload.get("new_spec"), dict):
        new_spec = payload["new_spec"]
    elif isinstance(payload, dict):
        new_spec = payload
    else:
        raise DeployError("Cloudhand spec.json is invalid (expected JSON object).")

    instances = new_spec.get("instances")
    if not isinstance(instances, list):
        raise DeployError("Cloudhand spec.json is invalid (instances must be a list).")

    target_instance_name = (instance_name or "").strip()
    candidate_instances: list[dict[str, Any]] = []
    if target_instance_name:
        for inst in instances:
            if (
                isinstance(inst, dict)
                and str(inst.get("name") or "").strip() == target_instance_name
            ):
                candidate_instances.append(inst)
        if not candidate_instances:
            raise DeployError(
                f"Instance '{target_instance_name}' was not found in Cloudhand spec.json."
            )
    else:
        candidate_instances = [inst for inst in instances if isinstance(inst, dict)]

    matches: list[int] = []
    for inst in candidate_instances:
        workloads = inst.get("workloads")
        if not isinstance(workloads, list):
            continue
        for workload in workloads:
            if not isinstance(workload, dict):
                continue
            if str(workload.get("name") or "").strip() != workload_name:
                continue
            service_cfg = workload.get("service_config")
            if not isinstance(service_cfg, dict):
                raise DeployError(
                    f"Workload '{workload_name}' has no valid service_config in Cloudhand spec.json."
                )
            ports = service_cfg.get("ports")
            if not isinstance(ports, list) or not ports:
                raise DeployError(
                    f"Workload '{workload_name}' has no assigned ports in Cloudhand spec.json."
                )
            try:
                first_port = int(ports[0])
            except Exception as exc:
                raise DeployError(
                    f"Workload '{workload_name}' has an invalid port in Cloudhand spec.json."
                ) from exc
            matches.append(first_port)

    if not matches:
        raise DeployError(f"Workload '{workload_name}' was not found in Cloudhand spec.json.")
    if len(matches) > 1 and not target_instance_name:
        raise DeployError(
            f"Workload '{workload_name}' appears in multiple instances; provide instance_name."
        )
    return matches[0]


def _infer_external_access_urls(
    *,
    server_ips: dict[str, Any],
    workload_name: str,
    instance_name: str | None,
) -> list[str]:
    if not isinstance(server_ips, dict) or not server_ips:
        raise DeployError(
            "Terraform outputs did not include server IPs for external access URL generation."
        )

    port = _workload_port_from_latest_spec(workload_name=workload_name, instance_name=instance_name)
    urls: list[str] = []
    for value in server_ips.values():
        ip = str(value or "").strip()
        if not ip:
            continue
        if port == 80:
            urls.append(f"http://{ip}/")
        else:
            urls.append(f"http://{ip}:{port}/")

    resolved = _normalize_access_urls(urls)
    if not resolved:
        raise DeployError(
            "External access URL generation failed because no valid server IPs were available."
        )
    return resolved


def _validate_standalone_funnel_artifact_preflight(*, workload_patch: dict[str, Any]) -> None:
    from cloudhand.adapters.deployer import ServerDeployer
    from cloudhand.models import ApplicationSourceType, ApplicationSpec, FunnelArtifactRenderMode
    from cloudhand.secrets import get_or_create_project_ssh_key

    try:
        app = ApplicationSpec.model_validate(workload_patch)
    except Exception as exc:  # pragma: no cover
        raise DeployError(f"Standalone preflight could not parse the workload patch: {exc}") from exc

    if app.source_type != ApplicationSourceType.FUNNEL_ARTIFACT:
        return
    source = app.source_ref
    if source is None:
        raise DeployError("Standalone preflight requires source_ref on the artifact workload.")
    if source.artifact_render_mode != FunnelArtifactRenderMode.STANDALONE_IMPORTED_HTML:
        return

    private_key, _public_key = get_or_create_project_ssh_key(settings.DEPLOY_PROJECT_ID)
    deployer = ServerDeployer(
        ip="127.0.0.1",
        private_key_str=private_key,
        local_root=_cloudhand_dir().parent,
    )
    deployer.upload_bytes = lambda payload, target_path: None  # type: ignore[method-assign]
    deployer.upload_file = lambda local_path, target_path: None  # type: ignore[method-assign]
    deployer.run = lambda cmd, cwd=None, mask=None: ""  # type: ignore[method-assign]

    standalone_uploaded_target_paths: set[str] = set()
    standalone_served_assets: dict[str, Any] = {}
    standalone_image_sources: dict[str, Any] = {}
    site_dir = "/tmp/mos-standalone-preflight"

    try:
        deployer._write_funnel_artifact_assets(
            site_dir=site_dir,
            source=source,
            uploaded_target_paths=standalone_uploaded_target_paths,
            standalone_served_assets=standalone_served_assets,
            standalone_image_sources=standalone_image_sources,
        )
        deployer._write_funnel_artifact_standalone_html_routes(
            site_dir=site_dir,
            source=source,
            public_server_names=(
                deployer._normalize_server_names(app.workspace_server_names)
                or deployer._normalize_server_names(app.service_config.server_names)
            ),
            mirrored_target_paths=standalone_uploaded_target_paths,
            standalone_served_assets=standalone_served_assets,
            standalone_image_sources=standalone_image_sources,
        )
    except Exception as exc:
        raise DeployError(f"Standalone artifact preflight failed: {exc}") from exc


def _summarize_apply_result(result: dict[str, Any]) -> tuple[int, dict[str, Any]]:
    rc = int(result.get("returncode", 1))
    summary: dict[str, Any] = {
        "returncode": rc,
        "plan_path": result.get("plan_path"),
        "materialized_plan_path": result.get("materialized_plan_path"),
        "server_ips": result.get("server_ips"),
        "live_url": result.get("live_url"),
    }
    logs = result.get("logs")
    if isinstance(logs, str) and logs:
        summary["logs_tail"] = logs[-_DEPLOY_JOB_LOG_TAIL_CHARS:]
    return rc, summary


async def _run_apply_plan_job(job_id: str) -> None:
    job = _read_job(job_id)
    path = _job_path(job_id)
    plan_path = str(job.get("plan_path") or "").strip()
    workload_names_raw = job.get("workload_names")
    workload_names: list[str] | None
    if isinstance(workload_names_raw, list):
        workload_names = [
            str(name).strip()
            for name in workload_names_raw
            if isinstance(name, str) and str(name).strip()
        ]
    else:
        workload_names = None
    if not plan_path:
        job["status"] = "failed"
        job["error"] = "Job is missing plan_path."
        job["finished_at"] = _utc_now_iso()
        _write_json_atomic(path, job)
        return

    job["status"] = "running"
    job["started_at"] = _utc_now_iso()
    _write_json_atomic(path, job)

    try:
        result = await apply_plan(plan_path=plan_path, workload_names=workload_names)
        rc, summary = _summarize_apply_result(result)

        access_urls = _normalize_access_urls(job.get("access_urls"))
        job["result"] = summary
        job["access_urls"] = access_urls
        if rc == 0:
            job["status"] = "succeeded"
            job["error"] = None
        else:
            job["status"] = "failed"
            job["error"] = f"Apply failed with return code {rc}."
    except DeployError as exc:
        job["status"] = "failed"
        job["error"] = str(exc)
    except Exception as exc:  # pragma: no cover - defensive
        job["status"] = "failed"
        job["error"] = f"Unexpected deploy failure: {exc}"

    job["finished_at"] = _utc_now_iso()
    _write_json_atomic(path, job)


async def _run_funnel_publish_job(job_id: str) -> None:
    from app.db.base import SessionLocal
    from app.services.funnels import publish_funnel

    job = _read_publish_job(job_id)
    path = _publish_job_path(job_id)
    job["status"] = "running"
    job["started_at"] = _utc_now_iso()
    job["phase"] = "publishing_funnel"
    _write_json_atomic(path, job)

    org_id = str(job.get("org_id") or "").strip()
    user_id = str(job.get("user_id") or "").strip()
    funnel_id = str(job.get("funnel_id") or "").strip()
    deploy_request = job.get("deploy_request")
    result_payload: dict[str, Any] = {}
    access_urls = _normalize_access_urls(job.get("access_urls"))
    hydrated_artifact_payload: dict[str, Any] | None = None
    hydrated_artifact_render_mode = ""
    publication_id = ""

    if not org_id or not user_id or not funnel_id:
        job["status"] = "failed"
        job["error"] = "Publish job is missing org_id, user_id, or funnel_id."
        job["finished_at"] = _utc_now_iso()
        _write_json_atomic(path, job)
        return

    try:
        session = SessionLocal()
        try:
            publication = publish_funnel(
                session=session, org_id=org_id, user_id=user_id, funnel_id=funnel_id
            )
            publication_id = str(publication.id)
            result_payload["publicationId"] = publication_id
            job["result"] = result_payload
            job["phase"] = "publication_created"
            _write_json_atomic(path, job)

            if deploy_request is not None:
                if not isinstance(deploy_request, dict):
                    raise DeployError("Invalid publish deploy request payload.")

                workload_patch = deploy_request.get("workload_patch")
                if not isinstance(workload_patch, dict):
                    raise DeployError("Publish deploy request is missing workload_patch.")

                workload_patch = hydrate_funnel_artifact_workload_patch(
                    session=session,
                    org_id=org_id,
                    funnel_id=funnel_id,
                    publication_id=str(publication.id),
                    workload_patch=workload_patch,
                    created_by_user_id=user_id,
                )

                hydrated_source_ref = workload_patch.get("source_ref")
                if isinstance(hydrated_source_ref, dict):
                    artifact_id = str(hydrated_source_ref.get("artifact_id") or "").strip()
                    artifact_version = hydrated_source_ref.get("artifact_version")
                    client_id = str(hydrated_source_ref.get("client_id") or "").strip()
                    if not artifact_id:
                        raise DeployError(
                            "Hydrated funnel deploy workload is missing source_ref.artifact_id."
                        )
                    artifact_payload = _load_funnel_runtime_artifact_payload_for_apply(
                        artifact_id=artifact_id
                    )
                    hydrated_artifact_payload = artifact_payload
                    workload_patch = _apply_publish_job_artifact_render_mode(
                        workload_patch=workload_patch,
                        artifact_payload=artifact_payload,
                        requested_render_mode=deploy_request.get("artifact_render_mode_requested"),
                        render_mode_was_explicit=bool(
                            deploy_request.get("artifact_render_mode_explicit", False)
                        ),
                    )
                    hydrated_source_ref = workload_patch.get("source_ref")
                    if not isinstance(hydrated_source_ref, dict):
                        raise DeployError(
                            "Hydrated funnel deploy workload lost source_ref after render mode resolution."
                        )
                    resolved_render_mode = str(
                        hydrated_source_ref.get("artifact_render_mode") or ""
                    ).strip()
                    hydrated_artifact_render_mode = resolved_render_mode
                    runtime_artifact_payload: dict[str, Any] = {
                        "id": artifact_id,
                        "clientId": client_id,
                        "renderMode": resolved_render_mode,
                    }
                    if isinstance(artifact_version, int):
                        runtime_artifact_payload["version"] = artifact_version
                    result_payload["runtimeArtifact"] = runtime_artifact_payload
                    job["result"] = result_payload
                    job["phase"] = "artifact_hydrated"
                    _write_json_atomic(path, job)
                    if resolved_render_mode == _FUNNEL_ARTIFACT_RENDER_MODE_STANDALONE_IMPORTED_HTML:
                        job["phase"] = "preflighting_standalone"
                        _write_json_atomic(path, job)
                        _validate_standalone_funnel_artifact_preflight(
                            workload_patch=workload_patch,
                        )
                        job["phase"] = "standalone_preflight_validated"
                        _write_json_atomic(path, job)

                plan_resolution = ensure_plan_for_funnel_publish_workload(
                    workload_patch=workload_patch,
                    plan_path=deploy_request.get("plan_path"),
                    instance_name=deploy_request.get("instance_name"),
                )

                patch_result = patch_workload_in_plan(
                    org_id=org_id,
                    workload_patch=workload_patch,
                    plan_path=plan_resolution["plan_path"],
                    instance_name=deploy_request.get("instance_name"),
                    create_if_missing=bool(deploy_request.get("create_if_missing", True)),
                    in_place=bool(deploy_request.get("in_place", False)),
                )
                deploy_response: dict[str, Any] = {"patch": patch_result}
                job["phase"] = "plan_patched"
                job["result"] = result_payload
                _write_json_atomic(path, job)
                if plan_resolution.get("bootstrapped"):
                    deploy_response["bootstrap"] = {
                        "created": True,
                        "plan_path": plan_resolution["plan_path"],
                    }
                access_urls = _normalize_access_urls(deploy_request.get("access_urls"))

                apply_plan_enabled = bool(deploy_request.get("apply_plan", True))
                requested_access_urls = _normalize_access_urls(deploy_request.get("access_urls"))
                if apply_plan_enabled:
                    workload_name = str(workload_patch.get("name") or "").strip()
                    if not workload_name:
                        raise DeployError(
                            "Publish deploy workload patch is missing workload name."
                        )
                    job["phase"] = "applying_plan"
                    _write_json_atomic(path, job)
                    apply_result = await apply_plan(
                        plan_path=patch_result["updated_plan_path"],
                        workload_names=[workload_name],
                    )
                    return_code, summary = _summarize_apply_result(apply_result)
                    deploy_response["apply"] = summary
                    if return_code != 0:
                        result_payload["deploy"] = deploy_response
                        job["result"] = result_payload
                        job["access_urls"] = access_urls
                        job["status"] = "failed"
                        job["error"] = (
                            f"Funnel published but deploy apply failed with return code {return_code}."
                        )
                        job["finished_at"] = _utc_now_iso()
                        _write_json_atomic(path, job)
                        return
                    if not access_urls:
                        access_urls = _infer_external_access_urls(
                            server_ips=summary.get("server_ips") or {},
                            workload_name=workload_name,
                            instance_name=deploy_request.get("instance_name"),
                        )
                    summary["access_urls"] = access_urls
                    deploy_response["apply"] = summary

                if bool(deploy_request.get("bunny_pull_zone", False)):
                    job["phase"] = "reconciling_bunny"
                    job["result"] = result_payload
                    _write_json_atomic(path, job)
                    workload_name = str(workload_patch.get("name") or "").strip()
                    if not workload_name:
                        raise DeployError("Publish deploy workload patch is missing workload name.")
                    workload_client_id = _resolve_workload_client_id(
                        workload=workload_patch,
                        workload_name=workload_name,
                    )
                    workspace_server_names = _resolve_publish_job_workspace_server_names(
                        session=session,
                        org_id=org_id,
                        workload_client_id=workload_client_id,
                        workload_patch=workload_patch,
                    )
                    bunny_config = _reconcile_bunny_pull_zone_for_published_workload(
                        client_id=workload_client_id,
                        workload_name=workload_name,
                        plan_path=patch_result.get("updated_plan_path"),
                        instance_name=deploy_request.get("instance_name"),
                        requested_origin_ip=deploy_request.get("bunny_pull_zone_origin_ip"),
                        require_port_when_no_domains=apply_plan_enabled,
                        server_names=workspace_server_names,
                    )
                    bunny_pull_zone_payload = bunny_config.get("pull_zone")
                    if isinstance(bunny_pull_zone_payload, dict) and isinstance(
                        bunny_pull_zone_payload.get("accessUrls"), list
                    ):
                        bunny_access_urls = bunny_pull_zone_payload.get("accessUrls")
                    else:
                        bunny_access_urls = []
                    if not isinstance(bunny_pull_zone_payload, dict):
                        raise DeployError("Publish deploy Bunny pull zone payload must be an object.")
                    try:
                        bunny_zone_id = int(bunny_pull_zone_payload.get("id"))
                    except (TypeError, ValueError) as exc:
                        raise DeployError(
                            "Publish deploy Bunny pull zone payload is missing a valid id."
                        ) from exc
                    if bunny_zone_id <= 0:
                        raise DeployError(
                            "Publish deploy Bunny pull zone payload id must be greater than zero."
                        )
                    job["phase"] = "purging_bunny_cache"
                    job["result"] = result_payload
                    _write_json_atomic(path, job)
                    bunny_config["cachePurge"] = _purge_bunny_pull_zone_cache(zone_id=bunny_zone_id)
                    access_urls = _normalize_access_urls(access_urls + bunny_access_urls)
                    deploy_response["cdn"] = bunny_config

                should_validate_tracking = bool(
                    deploy_request.get("validate_tracking_post_deploy", True)
                )
                validation_target_requested = bool(
                    apply_plan_enabled
                    or deploy_request.get("bunny_pull_zone", False)
                    or requested_access_urls
                )
                if should_validate_tracking and validation_target_requested:
                    if not access_urls:
                        raise DeployError(
                            "Post-deploy tracking validation requires at least one public access URL after deploy."
                        )
                    if hydrated_artifact_payload is None:
                        raise DeployError(
                            "Post-deploy tracking validation requires a hydrated funnel runtime artifact payload."
                        )
                    if not publication_id:
                        raise DeployError(
                            "Post-deploy tracking validation requires a published funnel publication id."
                        )
                    job["phase"] = "validating_tracking"
                    job["result"] = result_payload
                    _write_json_atomic(path, job)
                    deploy_response["trackingValidation"] = (
                        await _run_funnel_tracking_post_deploy_validation(
                            artifact_payload=hydrated_artifact_payload,
                            funnel_id=funnel_id,
                            publication_id=publication_id,
                            access_urls=access_urls,
                            render_mode=hydrated_artifact_render_mode,
                        )
                    )

                result_payload["deploy"] = deploy_response
        finally:
            session.close()

        job["result"] = result_payload
        job["access_urls"] = access_urls
        job["status"] = "succeeded"
        job["phase"] = "completed"
        job["error"] = None
    except ValueError as exc:
        job["status"] = "failed"
        job["error"] = str(exc)
        if result_payload:
            job["result"] = result_payload
        job["access_urls"] = access_urls
    except DeployError as exc:
        job["status"] = "failed"
        job["error"] = str(exc)
        if result_payload:
            job["result"] = result_payload
        job["access_urls"] = access_urls
    except Exception as exc:  # pragma: no cover - defensive
        job["status"] = "failed"
        job["error"] = f"Unexpected publish/deploy failure: {exc}"
        if result_payload:
            job["result"] = result_payload
        job["access_urls"] = access_urls

    job["finished_at"] = _utc_now_iso()
    _write_json_atomic(path, job)


def start_apply_plan_job(
    *,
    plan_path: str | None = None,
    workload_names: list[str] | None = None,
    access_urls: list[str] | None = None,
) -> dict[str, Any]:
    if plan_path:
        plan_file = _assert_under_cloudhand(Path(plan_path))
    else:
        plan_file = _find_latest_plan()
    if not plan_file or not plan_file.exists():
        raise DeployError("No plan found.")

    normalized_workload_names: list[str] = []
    seen_workload_names: set[str] = set()
    for raw_name in workload_names or []:
        workload_name = str(raw_name or "").strip()
        if not workload_name or workload_name in seen_workload_names:
            continue
        seen_workload_names.add(workload_name)
        normalized_workload_names.append(workload_name)

    job_id = str(uuid4())
    job = {
        "id": job_id,
        "status": "queued",
        "created_at": _utc_now_iso(),
        "started_at": None,
        "finished_at": None,
        "plan_path": str(plan_file),
        "workload_names": normalized_workload_names,
        "access_urls": _normalize_access_urls(access_urls),
        "result": None,
        "error": None,
    }
    _write_json_atomic(_job_path(job_id), job)

    try:
        loop = asyncio.get_running_loop()
    except RuntimeError as exc:
        raise DeployError("No running event loop available to start async deploy job.") from exc

    loop.create_task(_run_apply_plan_job(job_id))
    return job


def get_apply_plan_job(*, job_id: str) -> dict[str, Any]:
    return _read_job(job_id)


def start_funnel_publish_job(
    *,
    org_id: str,
    user_id: str,
    funnel_id: str,
    deploy_request: dict[str, Any] | None,
    access_urls: list[str] | None = None,
) -> dict[str, Any]:
    safe_org_id = (org_id or "").strip()
    safe_user_id = (user_id or "").strip()
    safe_funnel_id = (funnel_id or "").strip()
    if not safe_org_id:
        raise DeployError("org_id is required.")
    if not safe_user_id:
        raise DeployError("user_id is required.")
    if not safe_funnel_id:
        raise DeployError("funnel_id is required.")

    if deploy_request is not None and not isinstance(deploy_request, dict):
        raise DeployError("deploy_request must be an object when provided.")

    job_id = str(uuid4())
    job = {
        "id": job_id,
        "status": "queued",
        "created_at": _utc_now_iso(),
        "started_at": None,
        "finished_at": None,
        "org_id": safe_org_id,
        "user_id": safe_user_id,
        "funnel_id": safe_funnel_id,
        "deploy_request": deploy_request,
        "access_urls": _normalize_access_urls(access_urls),
        "result": None,
        "error": None,
    }
    _write_json_atomic(_publish_job_path(job_id), job)

    try:
        loop = asyncio.get_running_loop()
    except RuntimeError as exc:
        raise DeployError("No running event loop available to start async publish job.") from exc

    loop.create_task(_run_funnel_publish_job(job_id))
    return job


def get_funnel_publish_job(*, job_id: str, org_id: str, funnel_id: str) -> dict[str, Any]:
    job = _read_publish_job(job_id)
    if str(job.get("org_id") or "") != (org_id or "").strip():
        raise DeployError(f"Publish job '{job_id}' not found.")
    if str(job.get("funnel_id") or "") != (funnel_id or "").strip():
        raise DeployError(f"Publish job '{job_id}' not found.")
    return job
