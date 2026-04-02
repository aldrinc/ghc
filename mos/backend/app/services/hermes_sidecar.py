from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
from dataclasses import dataclass
from hashlib import sha256
from pathlib import Path
from typing import Any, Callable, Generator


class HermesSidecarError(RuntimeError):
    """Raised when the Hermes local sidecar cannot complete a prototype action."""


@dataclass(frozen=True)
class HermesRuntimeProjection:
    bundle_manifest: dict[str, Any]
    runtime_home: Path
    projection_hash: str
    toolsets: list[str]


@dataclass(frozen=True)
class HermesRunResult:
    response_text: str
    hermes_session_id: str
    raw_output: str
    usage: dict[str, int]


@dataclass(frozen=True)
class HermesRuntimeSettings:
    runtime_schema_version: str
    toolsets: list[str]
    model: str
    provider: str
    base_url: str
    openai_api_key: str
    anthropic_api_key: str
    compression_enabled: bool
    compression_threshold: float
    compression_summary_provider: str
    compression_summary_model: str | None
    api_key_hash: str


@dataclass(frozen=True)
class HermesRuntimeConfig:
    runtime_schema_version: str
    toolsets: list[str]
    model: str
    provider: str
    base_url: str
    compression_enabled: bool
    compression_threshold: float
    compression_summary_provider: str
    compression_summary_model: str | None
    required_run_agent_markers: tuple[str, ...]
    forbidden_run_agent_markers: tuple[str, ...]


class HermesSidecarService:
    EMBER_BUNDLE_KEY = "ember_v1"
    HONEST_HERBALIST_BUNDLE_KEY = "honest_herbalist_v1"
    RUNTIME_SKILL_NAME = "marketi-v3-sidecar-runtime"
    PAGE_EDITOR_MCP_SERVER_NAME = "marketi_page_editor"

    def __init__(self) -> None:
        self.repo_root = Path(__file__).resolve().parents[4]
        self.backend_root = self.repo_root / "mos" / "backend"
        self.programming_root = self.repo_root.parent
        self.strategy_root = self.programming_root / "mos_strategy_v3"
        self.hh_copy_root = self.repo_root / "V2 Fixes" / "Copywriting Agent — Final"
        self.local_root = self.repo_root / ".local" / "hermes"
        self.sidecar_env_path = self.local_root / "sidecar.env"
        self.runtime_config_path = Path(__file__).resolve().parents[1] / "data" / "hermes_runtime_config.json"
        self.hermes_source_root = Path(
            os.getenv("MARKETI_HERMES_SOURCE_ROOT", str(Path.home() / ".hermes" / "hermes-agent"))
        )
        self.hermes_run_agent_path = self.hermes_source_root / "run_agent.py"

    def runtime_summary(self) -> dict[str, Any]:
        settings = self._load_runtime_settings()
        return {
            "model": settings.model,
            "provider": settings.provider,
            "baseUrl": settings.base_url,
            "toolsets": settings.toolsets,
            "compressionEnabled": settings.compression_enabled,
            "compressionThreshold": settings.compression_threshold,
            "compressionSummaryProvider": settings.compression_summary_provider,
            "compressionSummaryModel": settings.compression_summary_model or None,
            "runtimeSchemaVersion": settings.runtime_schema_version,
        }

    @classmethod
    def page_editor_toolset_name(cls) -> str:
        return f"mcp-{cls.PAGE_EDITOR_MCP_SERVER_NAME}"

    def build_runtime_projection(
        self,
        *,
        bundle_key: str,
        org_id: str,
        client_id: str,
        product_id: str,
        thread_id: str,
        agent_profile: str,
        page_context: dict[str, Any] | None = None,
    ) -> HermesRuntimeProjection:
        supported_bundle_keys = {
            self.EMBER_BUNDLE_KEY,
            self.HONEST_HERBALIST_BUNDLE_KEY,
        }
        if bundle_key not in supported_bundle_keys:
            raise HermesSidecarError(
                "Unsupported bundleKey "
                f"'{bundle_key}'. Supported local prototype bundles: {', '.join(sorted(supported_bundle_keys))}."
            )
        if agent_profile != "copy":
            raise HermesSidecarError(
                f"Unsupported agentProfile '{agent_profile}'. Only 'copy' is supported in the local prototype."
            )

        manifest = self._build_bundle_manifest(bundle_key=bundle_key, agent_profile=agent_profile)
        return self.build_runtime_projection_from_manifest(
            bundle_manifest=manifest,
            org_id=org_id,
            client_id=client_id,
            product_id=product_id,
            thread_id=thread_id,
            agent_profile=agent_profile,
            page_context=page_context,
        )

    def build_runtime_projection_from_manifest(
        self,
        *,
        bundle_manifest: dict[str, Any],
        org_id: str,
        client_id: str,
        product_id: str,
        thread_id: str,
        agent_profile: str,
        page_context: dict[str, Any] | None = None,
    ) -> HermesRuntimeProjection:
        manifest = bundle_manifest
        settings = self._load_runtime_settings()
        projection_hash = self._projection_hash(
            manifest=manifest,
            page_context=page_context,
            settings=settings,
        )
        runtime_home = (
            self.local_root
            / f"org_{org_id}"
            / f"client_{client_id}"
            / f"product_{product_id}"
            / agent_profile
            / f"thread_{thread_id}"
        )

        hash_marker = runtime_home / "projection_hash.txt"
        if hash_marker.exists() and hash_marker.read_text(encoding="utf-8").strip() == projection_hash:
            return HermesRuntimeProjection(
                bundle_manifest=manifest,
                runtime_home=runtime_home,
                projection_hash=projection_hash,
                toolsets=list(settings.toolsets),
            )

        if runtime_home.exists():
            shutil.rmtree(runtime_home)
        runtime_home.mkdir(parents=True, exist_ok=True)
        self._seed_hermes_base_files(
            runtime_home=runtime_home,
            settings=settings,
            page_editor_thread_id=thread_id if page_context is not None else None,
        )
        self._project_skills(runtime_home=runtime_home, manifest=manifest)
        projected_files, projected_supporting_docs = self._project_bundle_sources(
            runtime_home=runtime_home,
            manifest=manifest,
        )
        self._write_runtime_guides(
            runtime_home=runtime_home,
            manifest=manifest,
            page_context=page_context,
            settings=settings,
            projected_files=projected_files,
            projected_supporting_docs=projected_supporting_docs,
        )
        hash_marker.write_text(projection_hash, encoding="utf-8")

        return HermesRuntimeProjection(
            bundle_manifest=manifest,
            runtime_home=runtime_home,
            projection_hash=projection_hash,
            toolsets=list(settings.toolsets),
        )

    def run_turn(
        self,
        *,
        runtime_home: Path,
        query: str,
        hermes_session_id: str | None,
        toolsets: list[str] | None = None,
        progress_callback: Callable[[dict[str, Any]], None] | None = None,
    ) -> HermesRunResult:
        if not query.strip():
            raise HermesSidecarError("Hermes query is empty.")

        prior_session_ids = self._list_session_ids(runtime_home)
        settings = self._load_runtime_settings()
        resolved_toolsets = toolsets or settings.toolsets
        command = ["hermes", "chat", "-Q", "-t", ",".join(resolved_toolsets), "-q", query]
        if hermes_session_id:
            command.extend(["--resume", hermes_session_id])
        env = os.environ.copy()
        env["HERMES_HOME"] = str(runtime_home)
        env.setdefault("CODEX_HOME", str(runtime_home / ".codex"))
        env.setdefault("PYTHONIOENCODING", "utf-8")
        env["HERMES_INFERENCE_PROVIDER"] = settings.provider
        env["OPENAI_BASE_URL"] = settings.base_url
        env["OPENAI_API_KEY"] = settings.openai_api_key
        env["ANTHROPIC_API_KEY"] = settings.anthropic_api_key
        env["LLM_MODEL"] = settings.model
        env["CONTEXT_COMPRESSION_ENABLED"] = "true" if settings.compression_enabled else "false"
        env["CONTEXT_COMPRESSION_THRESHOLD"] = str(settings.compression_threshold)
        env["CONTEXT_COMPRESSION_PROVIDER"] = settings.compression_summary_provider
        if settings.compression_summary_model:
            env["CONTEXT_COMPRESSION_MODEL"] = settings.compression_summary_model
        elif "CONTEXT_COMPRESSION_MODEL" in env:
            env.pop("CONTEXT_COMPRESSION_MODEL")

        if progress_callback is None:
            try:
                completed = subprocess.run(
                    command,
                    cwd=self.repo_root,
                    env=env,
                    capture_output=True,
                    text=True,
                    timeout=900,
                    check=False,
                )
            except subprocess.TimeoutExpired as exc:
                raise HermesSidecarError("Hermes sidecar timed out after 900 seconds.") from exc

            raw_stdout = self._strip_ansi(completed.stdout or "")
            raw_stderr = self._strip_ansi(completed.stderr or "")
            raw_output = raw_stdout.strip()
            if raw_stderr.strip():
                raw_output = f"{raw_output}\n{raw_stderr.strip()}".strip()

            if completed.returncode != 0:
                detail = raw_output or "Hermes exited without output."
                raise HermesSidecarError(f"Hermes sidecar failed: {detail}")
        else:
            raw_output = self._run_turn_with_progress(
                command=command,
                env=env,
                progress_callback=progress_callback,
            )

        provider_error = self._provider_error(raw_output)
        if provider_error:
            raise HermesSidecarError(f"Hermes sidecar provider error: {provider_error}")

        session_error = self._session_error(raw_output)
        if session_error:
            raise HermesSidecarError(f"Hermes sidecar session error: {session_error}")

        session_id = (
            self._extract_session_id(raw_output)
            or hermes_session_id
            or self._discover_session_id(runtime_home=runtime_home, prior_session_ids=prior_session_ids)
        )
        if not session_id:
            raise HermesSidecarError(
                "Hermes sidecar did not return a session_id. The run cannot be resumed safely."
            )

        response_text = self._load_response_from_session(runtime_home=runtime_home, session_id=session_id)
        if not response_text:
            response_text = self._strip_session_trailer(raw_output).strip()
        if not response_text:
            raise HermesSidecarError("Hermes sidecar returned an empty response.")

        return HermesRunResult(
            response_text=response_text,
            hermes_session_id=session_id,
            raw_output=raw_output,
            usage=self._load_usage_from_session(runtime_home=runtime_home, session_id=session_id),
        )

    def stream_turn(
        self,
        *,
        runtime_home: Path,
        query: str,
        hermes_session_id: str | None,
        toolsets: list[str] | None = None,
    ) -> Generator[dict[str, Any], None, HermesRunResult]:
        if not query.strip():
            raise HermesSidecarError("Hermes query is empty.")

        prior_session_ids = self._list_session_ids(runtime_home)
        settings = self._load_runtime_settings()
        resolved_toolsets = toolsets or settings.toolsets
        command = ["hermes", "chat", "-Q", "-t", ",".join(resolved_toolsets), "-q", query]
        if hermes_session_id:
            command.extend(["--resume", hermes_session_id])
        env = os.environ.copy()
        env["HERMES_HOME"] = str(runtime_home)
        env.setdefault("CODEX_HOME", str(runtime_home / ".codex"))
        env.setdefault("PYTHONIOENCODING", "utf-8")
        env["HERMES_INFERENCE_PROVIDER"] = settings.provider
        env["OPENAI_BASE_URL"] = settings.base_url
        env["OPENAI_API_KEY"] = settings.openai_api_key
        env["ANTHROPIC_API_KEY"] = settings.anthropic_api_key
        env["LLM_MODEL"] = settings.model
        env["CONTEXT_COMPRESSION_ENABLED"] = "true" if settings.compression_enabled else "false"
        env["CONTEXT_COMPRESSION_THRESHOLD"] = str(settings.compression_threshold)
        env["CONTEXT_COMPRESSION_PROVIDER"] = settings.compression_summary_provider
        if settings.compression_summary_model:
            env["CONTEXT_COMPRESSION_MODEL"] = settings.compression_summary_model
        elif "CONTEXT_COMPRESSION_MODEL" in env:
            env.pop("CONTEXT_COMPRESSION_MODEL")

        raw_output = yield from self._stream_command_output(command=command, env=env)

        provider_error = self._provider_error(raw_output)
        if provider_error:
            raise HermesSidecarError(f"Hermes sidecar provider error: {provider_error}")

        session_error = self._session_error(raw_output)
        if session_error:
            raise HermesSidecarError(f"Hermes sidecar session error: {session_error}")

        session_id = (
            self._extract_session_id(raw_output)
            or hermes_session_id
            or self._discover_session_id(runtime_home=runtime_home, prior_session_ids=prior_session_ids)
        )
        if not session_id:
            raise HermesSidecarError(
                "Hermes sidecar did not return a session_id. The run cannot be resumed safely."
            )

        response_text = self._load_response_from_session(runtime_home=runtime_home, session_id=session_id)
        if not response_text:
            response_text = self._strip_session_trailer(raw_output).strip()
        if not response_text:
            raise HermesSidecarError("Hermes sidecar returned an empty response.")

        return HermesRunResult(
            response_text=response_text,
            hermes_session_id=session_id,
            raw_output=raw_output,
            usage=self._load_usage_from_session(runtime_home=runtime_home, session_id=session_id),
        )

    def _stream_command_output(
        self,
        *,
        command: list[str],
        env: dict[str, str],
    ) -> Generator[dict[str, Any], None, str]:
        try:
            process = subprocess.Popen(
                command,
                cwd=self.repo_root,
                env=env,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                bufsize=1,
            )
        except OSError as exc:
            raise HermesSidecarError(f"Hermes sidecar failed to start: {exc}") from exc

        raw_chars: list[str] = []
        line_chars: list[str] = []
        last_event_key: tuple[str, str] | None = None

        def _flush_line() -> Generator[dict[str, Any], None, None]:
            nonlocal last_event_key
            if not line_chars:
                return
            raw_line = "".join(line_chars)
            line_chars.clear()
            event = self._parse_progress_event_line(raw_line)
            if event is None:
                return
            event_key = (str(event.get("type") or ""), str(event.get("message") or ""))
            if event_key == last_event_key:
                return
            last_event_key = event_key
            yield event

        try:
            stdout = process.stdout
            if stdout is None:
                raise HermesSidecarError("Hermes sidecar did not expose stdout for streaming.")
            while True:
                chunk = stdout.read(1)
                if chunk == "":
                    break
                raw_chars.append(chunk)
                if chunk in {"\r", "\n"}:
                    yield from _flush_line()
                    continue
                line_chars.append(chunk)
            yield from _flush_line()
            try:
                return_code = process.wait(timeout=5)
            except subprocess.TimeoutExpired as exc:
                process.kill()
                raise HermesSidecarError("Hermes sidecar did not exit cleanly after streaming.") from exc
        except Exception:
            process.kill()
            raise

        raw_output = self._strip_ansi("".join(raw_chars)).strip()
        if return_code != 0:
            detail = raw_output or "Hermes exited without output."
            raise HermesSidecarError(f"Hermes sidecar failed: {detail}")
        return raw_output

    def _run_turn_with_progress(
        self,
        *,
        command: list[str],
        env: dict[str, str],
        progress_callback: Callable[[dict[str, Any]], None],
    ) -> str:
        try:
            process = subprocess.Popen(
                command,
                cwd=self.repo_root,
                env=env,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                bufsize=1,
            )
        except OSError as exc:
            raise HermesSidecarError(f"Hermes sidecar failed to start: {exc}") from exc

        raw_chars: list[str] = []
        line_chars: list[str] = []
        last_event_key: tuple[str, str] | None = None

        def _flush_line() -> None:
            nonlocal last_event_key
            if not line_chars:
                return
            raw_line = "".join(line_chars)
            line_chars.clear()
            event = self._parse_progress_event_line(raw_line)
            if event is None:
                return
            event_key = (str(event.get("type") or ""), str(event.get("message") or ""))
            if event_key == last_event_key:
                return
            last_event_key = event_key
            progress_callback(event)

        try:
            stdout = process.stdout
            if stdout is None:
                raise HermesSidecarError("Hermes sidecar did not expose stdout for streaming.")
            while True:
                chunk = stdout.read(1)
                if chunk == "":
                    break
                raw_chars.append(chunk)
                if chunk in {"\r", "\n"}:
                    _flush_line()
                    continue
                line_chars.append(chunk)
            _flush_line()
            try:
                return_code = process.wait(timeout=5)
            except subprocess.TimeoutExpired as exc:
                process.kill()
                raise HermesSidecarError("Hermes sidecar did not exit cleanly after streaming.") from exc
        except Exception:
            process.kill()
            raise

        raw_output = self._strip_ansi("".join(raw_chars)).strip()
        if return_code != 0:
            detail = raw_output or "Hermes exited without output."
            raise HermesSidecarError(f"Hermes sidecar failed: {detail}")
        return raw_output

    @classmethod
    def _parse_progress_event_line(cls, raw_line: str) -> dict[str, Any] | None:
        clean_line = cls._strip_ansi(raw_line).strip()
        if not clean_line:
            return None
        if re.match(r"^[⠁-⣿]", clean_line):
            return None

        if clean_line.startswith("session_id:"):
            session_id = clean_line.partition(":")[2].strip()
            return {
                "type": "session",
                "message": f"Session {session_id} active.",
                "sessionId": session_id,
                "resumed": False,
            }

        if clean_line.startswith("↻ Resumed session "):
            resumed_id = clean_line.split()[3] if len(clean_line.split()) >= 4 else None
            return {
                "type": "session",
                "message": clean_line,
                "sessionId": resumed_id,
                "resumed": True,
            }

        if clean_line.startswith("┊ "):
            body = clean_line[2:].strip()
            if body.startswith("💬"):
                message = body[1:].strip()
                return {"type": "thinking", "message": message}
            tool_match = re.match(
                r"^(?P<icon>\S+)\s+(?P<tool>[a-zA-Z_]+)\s+(?P<target>.+?)\s+(?P<duration>\d+(?:\.\d+)?s)(?:\s+\[(?P<status>[^\]]+)\])?$",
                body,
            )
            if tool_match:
                status = tool_match.group("status") or "completed"
                return {
                    "type": "tool",
                    "message": body,
                    "icon": tool_match.group("icon"),
                    "toolName": tool_match.group("tool"),
                    "target": tool_match.group("target").strip(),
                    "duration": tool_match.group("duration"),
                    "status": status,
                }
            return {"type": "status", "message": body}

        if clean_line.startswith("💬"):
            return {"type": "thinking", "message": clean_line[1:].strip()}
        if clean_line.startswith("⚠️"):
            return {"type": "warning", "message": clean_line[2:].strip() or clean_line}
        if clean_line.startswith("❌"):
            return {"type": "error", "message": clean_line[1:].strip() or clean_line}

        return {"type": "status", "message": clean_line}

    def _build_bundle_manifest(self, *, bundle_key: str, agent_profile: str) -> dict[str, Any]:
        if bundle_key == self.EMBER_BUNDLE_KEY:
            return self._build_ember_bundle_manifest(bundle_key=bundle_key, agent_profile=agent_profile)
        if bundle_key == self.HONEST_HERBALIST_BUNDLE_KEY:
            return self._build_honest_herbalist_bundle_manifest(
                bundle_key=bundle_key,
                agent_profile=agent_profile,
            )
        raise HermesSidecarError(f"Unsupported bundleKey '{bundle_key}'.")

    def _build_ember_bundle_manifest(self, *, bundle_key: str, agent_profile: str) -> dict[str, Any]:
        if not self.strategy_root.exists():
            raise HermesSidecarError(f"Strategy source root does not exist: {self.strategy_root}")

        bundle_root = self.strategy_root / "FutrGroup-Hookd-Project" / "EMBER"
        skill_catalog = self._available_skill_catalog()

        required_files = {
            "knowledge_base": bundle_root / "EMBER-KNOWLEDGE-BASE.md",
            "workflow": bundle_root / "claude-projects" / "WORKFLOW.md",
            "cso": bundle_root / "cso" / "EMBER-CSO.md",
            "offer_document": bundle_root / "offer" / "EMBER-OFFER-DOCUMENT.json",
            "approved_headlines": bundle_root / "headlines" / "HEADLINE-POOL-EMBER-v3-synthesis.md",
            "signal_hunter_report": bundle_root / "signal-hunter" / "SIGNAL-HUNTER-REPORT-EMBER.md",
            "presell_page_example": bundle_root / "pages" / "EMBER-PRESALE-ADVERTORIAL.md",
            "sales_page_example": bundle_root / "pages" / "EMBER-SALES-PAGE.md",
        }

        supporting_docs = self._build_v3_supporting_docs()
        skill_chain = self._build_skill_chain(
            skill_catalog=skill_catalog,
            skill_roles=[
                ("FutrGroup_signal-hunter", "VOC and language map source"),
                ("FutrGroup_opportunity-engine", "CSO strategy layer"),
                ("FutrGroup_offer-architect", "Offer document and bundle framing"),
                ("FutrGroup_halbert-headlines", "Headline pool and human gate"),
                ("FutrGroup_copy-forge", "Copy strategy to draft asset execution"),
                ("FutrGroup_frankie-pages", "Full presell or sales page assembly"),
                ("FutrGroup_brand-forge", "Optional brand voice enrichment"),
                ("FutrGroup_founder-forge", "Optional founder narrative enrichment"),
                ("FutrGroup_pipeline-orchestrator", "Workflow source-of-truth for chat sequencing"),
            ],
        )
        available_skills = [
            {
                "name": name,
                "role": "Projected V3 skill",
                "path": str(path),
            }
            for name, path in sorted(skill_catalog.items())
        ]

        missing_roles = [f"{role}: {path}" for role, path in required_files.items() if not path.exists()]
        missing_supporting_docs = [
            f"{role}: {path}"
            for role, path in supporting_docs.items()
            if not path.exists()
        ]
        if missing_roles or missing_supporting_docs:
            parts: list[str] = []
            if missing_roles:
                parts.append("Missing bundle files: " + "; ".join(missing_roles))
            if missing_supporting_docs:
                parts.append("Missing V3 support files: " + "; ".join(missing_supporting_docs))
            raise HermesSidecarError(" ".join(parts))

        return {
            "bundleKey": bundle_key,
            "bundleFamily": "ember",
            "agentProfile": agent_profile,
            "bundleRoot": str(bundle_root),
            "files": {role: str(path) for role, path in required_files.items()},
            "skills": skill_chain,
            "availableSkills": available_skills,
            "supportingDocs": {role: str(path) for role, path in supporting_docs.items()},
        }

    def _build_honest_herbalist_bundle_manifest(
        self,
        *,
        bundle_key: str,
        agent_profile: str,
    ) -> dict[str, Any]:
        if not self.hh_copy_root.exists():
            raise HermesSidecarError(
                f"Honest Herbalist source root does not exist: {self.hh_copy_root}"
            )

        bundle_root = self.hh_copy_root
        skill_catalog = self._available_skill_catalog()
        required_files = {
            "system_readme": bundle_root / "SYSTEM_README.md",
            "architecture_map": bundle_root / "ARCHITECTURE_MAP.md",
            "audience_product": bundle_root
            / "06_examples"
            / "honest_herbalist"
            / "brand_context"
            / "audience-product.md",
            "brand_voice": bundle_root
            / "06_examples"
            / "honest_herbalist"
            / "brand_context"
            / "brand-voice.md",
            "compliance": bundle_root / "01_governance" / "shared_context" / "compliance.md",
            "mental_models": bundle_root
            / "01_governance"
            / "shared_context"
            / "mental-models.md",
            "competitor_research": bundle_root
            / "01_governance"
            / "research_artifacts"
            / "Competitor research - workflow-9959e7b9-ee05-4d23-8042-9dc03cff2b14 - step-01.txt",
            "avatar_brief": bundle_root
            / "01_governance"
            / "research_artifacts"
            / "Avatar brief - workflow-9959e7b9-ee05-4d23-8042-9dc03cff2b14 - step-06.txt",
            "offer_brief": bundle_root
            / "01_governance"
            / "research_artifacts"
            / "Offer brief - workflow-9959e7b9-ee05-4d23-8042-9dc03cff2b14 - step-07.txt",
            "necessary_beliefs": bundle_root
            / "01_governance"
            / "research_artifacts"
            / "_I believe_ statements - workflow-9959e7b9-ee05-4d23-8042-9dc03cff2b14 - step-09.txt",
            "approved_headlines": bundle_root
            / "06_examples"
            / "honest_herbalist"
            / "headlines"
            / "v4_50_headlines.txt",
            "presell_page_example": bundle_root
            / "06_examples"
            / "honest_herbalist"
            / "advertorials"
            / "advertorial_dosage_dangerous_detail.md",
            "sales_page_example": bundle_root
            / "06_examples"
            / "honest_herbalist"
            / "sales_pages"
            / "OutputC_Merged_SalesPage.md",
            "presell_promise_contract": bundle_root
            / "06_examples"
            / "honest_herbalist"
            / "promise_contracts"
            / "dangerous_detail_promise_contract.json",
            "sales_page_promise_contract": bundle_root
            / "06_examples"
            / "honest_herbalist"
            / "promise_contracts"
            / "sales_page_promise_contract.json",
        }
        supporting_docs = self._build_v3_supporting_docs()
        skill_chain = self._build_skill_chain(
            skill_catalog=skill_catalog,
            skill_roles=[
                ("FutrGroup_pipeline-orchestrator", "Conversation and handoff discipline"),
                ("foundational-docs-generator", "Foundational doc packaging reference"),
                ("angles", "Positioning and mechanism framing"),
                ("FutrGroup_offer-architect", "Offer structure and stack framing"),
                ("FutrGroup_halbert-headlines", "Headline discipline and selection"),
                ("FutrGroup_copy-forge", "Direct-response drafting"),
                ("FutrGroup_frankie-pages", "Long-form page assembly"),
                ("copywriting-skill", "Schema and QA reference layer"),
            ],
        )
        available_skills = [
            {
                "name": name,
                "role": "Projected V3 skill",
                "path": str(path),
            }
            for name, path in sorted(skill_catalog.items())
        ]

        missing_roles = [f"{role}: {path}" for role, path in required_files.items() if not path.exists()]
        missing_supporting_docs = [
            f"{role}: {path}"
            for role, path in supporting_docs.items()
            if not path.exists()
        ]
        if missing_roles or missing_supporting_docs:
            parts: list[str] = []
            if missing_roles:
                parts.append("Missing Honest Herbalist bundle files: " + "; ".join(missing_roles))
            if missing_supporting_docs:
                parts.append("Missing V3 support files: " + "; ".join(missing_supporting_docs))
            raise HermesSidecarError(" ".join(parts))

        return {
            "bundleKey": bundle_key,
            "bundleFamily": "honest_herbalist",
            "agentProfile": agent_profile,
            "bundleRoot": str(bundle_root),
            "files": {role: str(path) for role, path in required_files.items()},
            "skills": skill_chain,
            "availableSkills": available_skills,
            "supportingDocs": {role: str(path) for role, path in supporting_docs.items()},
        }

    def _available_skill_catalog(self) -> dict[str, Path]:
        skills_root = self.strategy_root / "skills"
        if not skills_root.exists():
            raise HermesSidecarError(f"Strategy skills root does not exist: {skills_root}")

        catalog: dict[str, Path] = {}
        for path in sorted(skills_root.iterdir()):
            if path.is_dir() and (path / "SKILL.md").exists():
                catalog[path.name] = path

        extra_skill_dirs = [
            self.strategy_root / "FutrGroup-Hookd-Project" / "02-skills" / "FutrGroup_pipeline-orchestrator",
        ]
        for path in extra_skill_dirs:
            if (path / "SKILL.md").exists():
                catalog[path.name] = path
        return catalog

    @staticmethod
    def _build_skill_chain(
        *,
        skill_catalog: dict[str, Path],
        skill_roles: list[tuple[str, str]],
    ) -> list[dict[str, Any]]:
        missing_skills = [name for name, _ in skill_roles if name not in skill_catalog]
        if missing_skills:
            raise HermesSidecarError(
                "Missing required skill directories: " + ", ".join(sorted(missing_skills))
            )
        return [
            {
                "name": name,
                "role": role,
                "path": str(skill_catalog[name]),
            }
            for name, role in skill_roles
        ]

    def _build_v3_supporting_docs(self) -> dict[str, Path]:
        supporting_docs = {
            "v3_claude": self.strategy_root / "CLAUDE.md",
            "v3_onboarding": self.strategy_root / "ONBOARDING.md",
            "v3_agents": self.strategy_root / "AGENTS.md",
            "v3_settings": self.strategy_root / "settings.json",
            "v3_offer_engine_command": self.strategy_root / "commands" / "offer-engine" / "SKILL.md",
            "v3_memory": self.strategy_root / "memory",
            "v3_hookd_memory": self.strategy_root / "FutrGroup-Hookd-Project" / "06-memory",
        }
        return {role: path for role, path in supporting_docs.items() if path.exists()}

    def _projection_hash(
        self,
        *,
        manifest: dict[str, Any],
        page_context: dict[str, Any] | None,
        settings: HermesRuntimeSettings,
    ) -> str:
        payload: dict[str, Any] = {
            "manifest": manifest,
            "pageContext": page_context or {},
            "toolsets": list(settings.toolsets),
            "runtimeSchemaVersion": settings.runtime_schema_version,
            "runtimeSettings": {
                "model": settings.model,
                "provider": settings.provider,
                "baseUrl": settings.base_url,
                "apiKeyHash": settings.api_key_hash,
                "compressionEnabled": settings.compression_enabled,
                "compressionThreshold": settings.compression_threshold,
                "compressionSummaryProvider": settings.compression_summary_provider,
                "compressionSummaryModel": settings.compression_summary_model,
            },
            "files": {},
            "skillTrees": {},
        }
        source_items: dict[str, str] = dict(manifest["files"])
        source_items.update(manifest.get("supportingDocs") or {})
        for role, raw_path in source_items.items():
            path = Path(raw_path)
            if path.is_dir():
                payload["files"][role] = {
                    "path": str(path),
                    "kind": "dir",
                    "tree": self._tree_fingerprint(path),
                }
                continue
            payload["files"][role] = {
                "path": str(path),
                "kind": "file",
                "mtime": path.stat().st_mtime_ns,
                "size": path.stat().st_size,
            }
        for skill in manifest.get("availableSkills") or manifest["skills"]:
            path = Path(skill["path"])
            payload["skillTrees"][skill["name"]] = self._tree_fingerprint(path)
        return sha256(json.dumps(payload, sort_keys=True).encode("utf-8")).hexdigest()

    @staticmethod
    def _tree_fingerprint(path: Path) -> list[dict[str, Any]]:
        entries: list[dict[str, Any]] = []
        for file_path in sorted(p for p in path.rglob("*") if p.is_file()):
            stat = file_path.stat()
            entries.append(
                {
                    "path": str(file_path.relative_to(path)),
                    "mtime": stat.st_mtime_ns,
                    "size": stat.st_size,
                }
            )
        return entries

    def _seed_hermes_base_files(
        self,
        *,
        runtime_home: Path,
        settings: HermesRuntimeSettings,
        page_editor_thread_id: str | None,
    ) -> None:
        for dirname in ("skills", "memories", "sessions", "logs", "runtime"):
            (runtime_home / dirname).mkdir(parents=True, exist_ok=True)

        mcp_text = (
            self._page_editor_mcp_config(thread_id=page_editor_thread_id)
            if page_editor_thread_id
            else ""
        )
        config_text = (
            "model:\n"
            f"  default: {settings.model}\n"
            f"  provider: {settings.provider}\n"
            f"  base_url: {settings.base_url}\n"
            "toolsets:\n"
            "- all\n"
            "agent:\n"
            "  max_turns: 60\n"
            "  verbose: false\n"
            "  reasoning_effort: medium\n"
            "terminal:\n"
            "  backend: local\n"
            "  cwd: .\n"
            "  timeout: 180\n"
            "browser:\n"
            "  inactivity_timeout: 120\n"
            "  record_sessions: false\n"
            "compression:\n"
            f"  enabled: {'true' if settings.compression_enabled else 'false'}\n"
            f"  threshold: {settings.compression_threshold}\n"
            f"  summary_provider: {settings.compression_summary_provider}\n"
            f"  summary_model: {settings.compression_summary_model!r}\n"
            "memory:\n"
            "  memory_enabled: false\n"
            "  user_profile_enabled: false\n"
            "display:\n"
            "  compact: true\n"
            "  tool_progress: all\n"
            "  resume_display: minimal\n"
            "  show_reasoning: false\n"
            "  background_process_notifications: error\n"
            f"{mcp_text}"
            "_config_version: 6\n"
        )
        (runtime_home / "config.yaml").write_text(config_text, encoding="utf-8")

        env_lines = [
            f"OPENAI_BASE_URL={settings.base_url}",
            f"OPENAI_API_KEY={settings.openai_api_key}",
            f"ANTHROPIC_API_KEY={settings.anthropic_api_key}",
            f"CONTEXT_COMPRESSION_ENABLED={'true' if settings.compression_enabled else 'false'}",
            f"CONTEXT_COMPRESSION_THRESHOLD={settings.compression_threshold}",
            f"CONTEXT_COMPRESSION_PROVIDER={settings.compression_summary_provider}",
        ]
        if settings.compression_summary_model:
            env_lines.append(f"CONTEXT_COMPRESSION_MODEL={settings.compression_summary_model}")
        (runtime_home / ".env").write_text("\n".join(env_lines) + "\n", encoding="utf-8")

    def _project_skills(self, *, runtime_home: Path, manifest: dict[str, Any]) -> None:
        skills_root = runtime_home / "skills"
        for skill in manifest.get("availableSkills") or manifest["skills"]:
            source = Path(skill["path"])
            target = skills_root / source.name
            shutil.copytree(source, target, dirs_exist_ok=True)

        runtime_skill_dir = skills_root / self.RUNTIME_SKILL_NAME
        runtime_skill_dir.mkdir(parents=True, exist_ok=True)
        start_here_path = runtime_home / "runtime" / "START-HERE.md"
        manifest_path = runtime_home / "runtime" / "active_bundle" / "manifest.json"
        active_chain = " -> ".join(skill["name"] for skill in manifest["skills"])
        runtime_skill = (
            "---\n"
            f"name: {self.RUNTIME_SKILL_NAME}\n"
            'description: "Runtime glue skill for the local mOS V3 Hermes sidecar. Enforces the active bundle chain and source-fidelity rules."\n'
            "---\n\n"
            "# Marketi V3 Sidecar Runtime\n\n"
            "## When to Use\n"
            "Use inside the local mOS Hermes prototype when the active bundle is mounted and the objective is a reviewable copy draft.\n\n"
            "## Procedure\n"
            f"1. Read `{start_here_path}` before drafting.\n"
            f"2. Treat `{manifest_path}` as the canonical active bundle.\n"
            f"3. Use the active chain in this order: {active_chain}.\n"
            "4. Treat any selected or approved headline artifact in the active bundle as already human-approved. Do not regenerate headlines unless the user explicitly asks.\n"
            "5. When the bundle includes worked examples or promise contracts, match their document shape and delivery obligations without copying verbatim.\n"
            "6. When inputs are missing or contradictory, stop and explain the exact missing role instead of repairing silently.\n"
            "7. Return only the exact user-facing payload requested by the task contract. If the task says JSON-only, return JSON-only. Otherwise return markdown only.\n"
            "8. Do not include tool commentary, status notes, implementation notes, or code fences unless the task contract explicitly requires them.\n"
        )
        (runtime_skill_dir / "SKILL.md").write_text(runtime_skill, encoding="utf-8")

    def _project_bundle_sources(
        self,
        *,
        runtime_home: Path,
        manifest: dict[str, Any],
    ) -> tuple[dict[str, str], dict[str, str]]:
        active_bundle_root = runtime_home / "runtime" / "active_bundle" / "files"
        projected_files: dict[str, str] = {}
        for role, raw_path in manifest["files"].items():
            source = Path(raw_path)
            target = self._projection_target(active_bundle_root, role, source)
            self._copy_source_item(source=source, target=target)
            projected_files[role] = str(target)

        supporting_root = runtime_home / "runtime" / "supporting_docs"
        projected_supporting_docs: dict[str, str] = {}
        for role, raw_path in (manifest.get("supportingDocs") or {}).items():
            source = Path(raw_path)
            target = self._projection_target(supporting_root, role, source)
            self._copy_source_item(source=source, target=target)
            projected_supporting_docs[role] = str(target)
        return projected_files, projected_supporting_docs

    @staticmethod
    def _projection_target(root: Path, role: str, source: Path) -> Path:
        if source.is_dir():
            return root / role
        suffix = "".join(source.suffixes)
        return root / f"{role}{suffix}"

    @staticmethod
    def _copy_source_item(*, source: Path, target: Path) -> None:
        target.parent.mkdir(parents=True, exist_ok=True)
        if source.is_dir():
            shutil.copytree(source, target, dirs_exist_ok=True)
            return
        shutil.copy2(source, target)

    def _write_runtime_guides(
        self,
        *,
        runtime_home: Path,
        manifest: dict[str, Any],
        page_context: dict[str, Any] | None,
        settings: HermesRuntimeSettings,
        projected_files: dict[str, str],
        projected_supporting_docs: dict[str, str],
    ) -> None:
        runtime_root = runtime_home / "runtime"
        active_bundle_root = runtime_root / "active_bundle"
        active_bundle_root.mkdir(parents=True, exist_ok=True)
        runtime_manifest = {
            **manifest,
            "projectedFiles": projected_files,
            "projectedSupportingDocs": projected_supporting_docs,
        }
        (active_bundle_root / "manifest.json").write_text(
            json.dumps(runtime_manifest, indent=2, sort_keys=True),
            encoding="utf-8",
        )

        start_here = [
            "# START HERE",
            "",
            "This Hermes home was generated by the local mOS V3 prototype.",
            "",
            "Non-negotiable runtime rules:",
            "- Use the projected skill chain, not generic copywriting behavior.",
            "- Do not invent missing claims, pricing, testimonials, or proof.",
            "- Treat selected or approved headline artifacts in the active bundle as human-approved.",
            "- When required inputs are missing, stop with a clear error.",
            "- Output only the exact payload requested by the current task contract.",
            f"- Runtime model is pinned to `{settings.model}` via `{settings.base_url}`.",
            "- This direct Anthropic runtime uses stable session reuse and context compression for spend control.",
            "- Hermes' built-in Claude prompt-cache markers are only available on its OpenRouter path.",
            "",
            "Active primary skill chain:",
        ]
        for skill in manifest["skills"]:
            start_here.append(f"- {skill['name']}: {skill['role']}")
        start_here.extend(
            [
                "",
                "Projected bundle files:",
            ]
        )
        for role, path in projected_files.items():
            start_here.append(f"- {role}: {path}")

        if projected_supporting_docs:
            start_here.extend(
                [
                    "",
                    "Projected V3 support docs and assets:",
                ]
            )
            for role, path in projected_supporting_docs.items():
                start_here.append(f"- {role}: {path}")

        start_here.extend(
            [
                "",
                "Bundle-specific rules:",
            ]
        )
        runtime_rules = manifest.get("runtimeRules")
        rules = runtime_rules if isinstance(runtime_rules, list) and runtime_rules else self._bundle_runtime_rules(bundle_key=manifest["bundleKey"])
        for rule in rules:
            start_here.append(f"- {rule}")

        if page_context:
            page_context_path = runtime_root / "page_context.json"
            page_context_path.write_text(
                json.dumps(page_context, indent=2, sort_keys=True),
                encoding="utf-8",
            )
            start_here.extend(
                [
                    "",
                    f"Page context file: {page_context_path}",
                    "- The page context file is read-only reference material.",
                    (
                        f"- For canonical page edits, use `{self.page_editor_toolset_name()}` "
                        "MCP tools instead of mutating any runtime or bundle file."
                    ),
                ]
            )

        (runtime_root / "START-HERE.md").write_text("\n".join(start_here) + "\n", encoding="utf-8")
        soul = (
            "# Hermes V3 Prototype Persona\n\n"
            "You are operating inside a local mOS V3 prototype.\n"
            "Be direct, professional, and strict about source fidelity.\n"
            "Use the projected FutrGroup skills and active bundle files instead of generic assumptions.\n"
            "If an input is missing, contradictory, or unapproved, error clearly.\n"
            "For successful runs, return only the user-facing markdown draft.\n"
        )
        (runtime_home / "SOUL.md").write_text(soul, encoding="utf-8")

    def _bundle_runtime_rules(self, *, bundle_key: str) -> list[str]:
        if bundle_key == self.EMBER_BUNDLE_KEY:
            return [
                "Use the EMBER source files as the canonical offer and page examples.",
                "Respect the approved headline file as a human-approved upstream gate.",
                "Stay inside the presell/sales-page document shapes already present in the EMBER examples.",
            ]
        if bundle_key == self.HONEST_HERBALIST_BUNDLE_KEY:
            return [
                "Use the Honest Herbalist foundational docs and shared-context files as the canonical source of truth.",
                "Use the worked-example advertorial and sales page to match document shape and review expectations without copying lines verbatim.",
                "When a promise contract exists for the requested document type, make the body satisfy that promise.",
                "Produce full page-ready markdown documents that match the same deliverable category we expect from EMBER: presell advertorials and sales pages.",
            ]
        return ["Use the active bundle files and projected skills as the only trusted source of truth."]

    def _load_runtime_settings(self) -> HermesRuntimeSettings:
        runtime_config = self._load_runtime_config()
        self._validate_runtime_installation(runtime_config=runtime_config)
        file_env = self._read_env_file(self.sidecar_env_path)

        def _env(name: str) -> str:
            file_value = file_env.get(name, "").strip()
            if file_value:
                return file_value
            value = os.getenv(name)
            if value is not None and value.strip():
                return value.strip()
            return ""

        openai_api_key = (
            _env("MARKETI_HERMES_OPENAI_API_KEY")
            or _env("OPENAI_API_KEY")
            or _env("MARKETI_HERMES_ANTHROPIC_API_KEY")
            or _env("ANTHROPIC_API_KEY")
        )
        anthropic_api_key = (
            _env("MARKETI_HERMES_ANTHROPIC_API_KEY")
            or _env("ANTHROPIC_API_KEY")
            or openai_api_key
        )
        if not openai_api_key:
            raise HermesSidecarError(
                "Hermes sidecar is missing an API key. Configure "
                f"{self.sidecar_env_path} with ANTHROPIC_API_KEY or OPENAI_API_KEY."
            )

        return HermesRuntimeSettings(
            runtime_schema_version=runtime_config.runtime_schema_version,
            toolsets=list(runtime_config.toolsets),
            model=runtime_config.model,
            provider=runtime_config.provider,
            base_url=runtime_config.base_url.rstrip("/"),
            openai_api_key=openai_api_key,
            anthropic_api_key=anthropic_api_key,
            compression_enabled=runtime_config.compression_enabled,
            compression_threshold=runtime_config.compression_threshold,
            compression_summary_provider=runtime_config.compression_summary_provider,
            compression_summary_model=runtime_config.compression_summary_model,
            api_key_hash=sha256(openai_api_key.encode("utf-8")).hexdigest(),
        )

    def _page_editor_mcp_config(self, *, thread_id: str) -> str:
        backend_python = self.backend_root / ".venv" / "bin" / "python"
        if not backend_python.exists():
            raise HermesSidecarError(
                f"Hermes page editor MCP runtime is missing backend Python: {backend_python}"
            )
        return (
            "mcp_servers:\n"
            f"  {self.PAGE_EDITOR_MCP_SERVER_NAME}:\n"
            f"    command: \"{backend_python}\"\n"
            "    args:\n"
            "      - \"-m\"\n"
            "      - \"app.agent_platform.page_edit_mcp_server\"\n"
            "      - \"--thread-id\"\n"
            f"      - \"{thread_id}\"\n"
            "    env:\n"
            f"      PYTHONPATH: \"{self.backend_root}\"\n"
            "    timeout: 120\n"
            "    connect_timeout: 30\n"
        )

    def _load_runtime_config(self) -> HermesRuntimeConfig:
        if not self.runtime_config_path.exists():
            raise HermesSidecarError(
                f"Hermes runtime config is missing: {self.runtime_config_path}"
            )
        try:
            payload = json.loads(self.runtime_config_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise HermesSidecarError(
                f"Hermes runtime config is unreadable: {self.runtime_config_path}"
            ) from exc

        defaults = payload.get("defaults")
        adapter_spec = payload.get("adapterSpec")
        if not isinstance(defaults, dict) or not isinstance(adapter_spec, dict):
            raise HermesSidecarError(
                f"Hermes runtime config is invalid: {self.runtime_config_path}"
            )

        runtime_schema_version = payload.get("runtimeSchemaVersion")
        toolsets = payload.get("toolsets")
        if not isinstance(runtime_schema_version, str) or not runtime_schema_version.strip():
            raise HermesSidecarError(
                f"Hermes runtime config is missing runtimeSchemaVersion: {self.runtime_config_path}"
            )
        if not isinstance(toolsets, list) or not toolsets or not all(
            isinstance(item, str) and item.strip() for item in toolsets
        ):
            raise HermesSidecarError(
                f"Hermes runtime config is missing valid toolsets: {self.runtime_config_path}"
            )

        required_markers = adapter_spec.get("requiredRunAgentMarkers")
        forbidden_markers = adapter_spec.get("forbiddenRunAgentMarkers")
        if not isinstance(required_markers, list) or not all(
            isinstance(item, str) and item for item in required_markers
        ):
            raise HermesSidecarError(
                f"Hermes runtime config is missing adapterSpec.requiredRunAgentMarkers: {self.runtime_config_path}"
            )
        if not isinstance(forbidden_markers, list) or not all(
            isinstance(item, str) and item for item in forbidden_markers
        ):
            raise HermesSidecarError(
                f"Hermes runtime config is missing adapterSpec.forbiddenRunAgentMarkers: {self.runtime_config_path}"
            )

        model = defaults.get("model")
        provider = defaults.get("provider")
        base_url = defaults.get("baseUrl")
        compression_summary_provider = defaults.get("compressionSummaryProvider")
        if not isinstance(model, str) or not model.strip():
            raise HermesSidecarError(
                f"Hermes runtime config is missing defaults.model: {self.runtime_config_path}"
            )
        if not isinstance(provider, str) or not provider.strip():
            raise HermesSidecarError(
                f"Hermes runtime config is missing defaults.provider: {self.runtime_config_path}"
            )
        if not isinstance(base_url, str) or not base_url.strip():
            raise HermesSidecarError(
                f"Hermes runtime config is missing defaults.baseUrl: {self.runtime_config_path}"
            )
        if not isinstance(compression_summary_provider, str) or not compression_summary_provider.strip():
            raise HermesSidecarError(
                "Hermes runtime config is missing defaults.compressionSummaryProvider: "
                f"{self.runtime_config_path}"
            )

        compression_enabled = defaults.get("compressionEnabled")
        if not isinstance(compression_enabled, bool):
            raise HermesSidecarError(
                "Hermes runtime config is missing defaults.compressionEnabled: "
                f"{self.runtime_config_path}"
            )
        compression_threshold = defaults.get("compressionThreshold")
        if not isinstance(compression_threshold, (int, float)) or isinstance(compression_threshold, bool):
            raise HermesSidecarError(
                "Hermes runtime config is missing defaults.compressionThreshold: "
                f"{self.runtime_config_path}"
            )
        compression_summary_model = defaults.get("compressionSummaryModel")
        if compression_summary_model is not None and not isinstance(compression_summary_model, str):
            raise HermesSidecarError(
                "Hermes runtime config has invalid defaults.compressionSummaryModel: "
                f"{self.runtime_config_path}"
            )

        return HermesRuntimeConfig(
            runtime_schema_version=runtime_schema_version.strip(),
            toolsets=[item.strip() for item in toolsets],
            model=model.strip(),
            provider=provider.strip(),
            base_url=base_url.strip(),
            compression_enabled=compression_enabled,
            compression_threshold=float(compression_threshold),
            compression_summary_provider=compression_summary_provider.strip(),
            compression_summary_model=compression_summary_model.strip()
            if isinstance(compression_summary_model, str) and compression_summary_model.strip()
            else None,
            required_run_agent_markers=tuple(required_markers),
            forbidden_run_agent_markers=tuple(forbidden_markers),
        )

    def _validate_runtime_installation(self, *, runtime_config: HermesRuntimeConfig) -> None:
        if not self.hermes_run_agent_path.exists():
            raise HermesSidecarError(
                "Hermes runtime source is missing. Expected run_agent.py at "
                f"{self.hermes_run_agent_path}. Set MARKETI_HERMES_SOURCE_ROOT if Hermes is installed elsewhere."
            )
        try:
            run_agent_text = self.hermes_run_agent_path.read_text(encoding="utf-8")
        except OSError as exc:
            raise HermesSidecarError(
                f"Hermes runtime source is unreadable: {self.hermes_run_agent_path}"
            ) from exc

        missing_markers = [
            marker for marker in runtime_config.required_run_agent_markers if marker not in run_agent_text
        ]
        forbidden_hits = [
            marker for marker in runtime_config.forbidden_run_agent_markers if marker in run_agent_text
        ]
        if missing_markers or forbidden_hits:
            problems: list[str] = []
            if missing_markers:
                problems.append("missing markers: " + "; ".join(missing_markers))
            if forbidden_hits:
                problems.append("forbidden markers present: " + "; ".join(forbidden_hits))
            raise HermesSidecarError(
                "Hermes runtime installation does not match the repo-owned runtime config at "
                f"{self.runtime_config_path}. "
                + " ".join(problems)
            )

    @staticmethod
    def _read_env_file(path: Path) -> dict[str, str]:
        if not path.exists():
            return {}
        values: dict[str, str] = {}
        for raw_line in path.read_text(encoding="utf-8").splitlines():
            line = raw_line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, value = line.split("=", 1)
            values[key.strip()] = value.strip().strip("'").strip('"')
        return values

    @staticmethod
    def _load_response_from_session(*, runtime_home: Path, session_id: str) -> str:
        session_path = runtime_home / "sessions" / f"session_{session_id}.json"
        if not session_path.exists():
            return ""
        try:
            payload = json.loads(session_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return ""

        messages = payload.get("messages")
        if not isinstance(messages, list):
            return ""

        for message in reversed(messages):
            if not isinstance(message, dict) or message.get("role") != "assistant":
                continue
            content = message.get("content")
            if isinstance(content, str) and content.strip():
                return content.strip()
        return ""

    @classmethod
    def _load_usage_from_session(cls, *, runtime_home: Path, session_id: str) -> dict[str, int]:
        session_path = runtime_home / "sessions" / f"session_{session_id}.json"
        if not session_path.exists():
            raise HermesSidecarError(
                f"Hermes sidecar session log is missing for exact usage telemetry: {session_path}"
            )
        try:
            payload = json.loads(session_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise HermesSidecarError(
                f"Hermes sidecar session log is unreadable for exact usage telemetry: {session_path}"
            ) from exc

        usage = payload.get("usage")
        if not isinstance(usage, dict):
            raise HermesSidecarError(
                f"Hermes sidecar did not persist exact usage telemetry for session {session_id}."
            )

        required_keys = ("prompt_tokens", "completion_tokens", "total_tokens")
        missing_keys = [key for key in required_keys if key not in usage]
        if missing_keys:
            raise HermesSidecarError(
                "Hermes sidecar usage telemetry is incomplete for session "
                f"{session_id}. Missing keys: {', '.join(sorted(missing_keys))}."
            )

        telemetry = {
            "promptTokens": cls._coerce_usage_int(usage["prompt_tokens"], field="prompt_tokens"),
            "completionTokens": cls._coerce_usage_int(
                usage["completion_tokens"],
                field="completion_tokens",
            ),
            "totalTokens": cls._coerce_usage_int(usage["total_tokens"], field="total_tokens"),
            "cacheReadTokens": cls._coerce_usage_int(
                usage.get("cache_read_tokens", 0),
                field="cache_read_tokens",
            ),
            "cacheWriteTokens": cls._coerce_usage_int(
                usage.get("cache_write_tokens", 0),
                field="cache_write_tokens",
            ),
            "apiCallCount": cls._coerce_usage_int(
                usage.get("api_call_count", 0),
                field="api_call_count",
            ),
        }
        return telemetry

    @staticmethod
    def _coerce_usage_int(value: Any, *, field: str) -> int:
        if isinstance(value, bool):
            raise HermesSidecarError(f"Hermes sidecar usage field '{field}' is invalid.")
        if isinstance(value, int):
            return value
        if isinstance(value, float) and value.is_integer():
            return int(value)
        raise HermesSidecarError(f"Hermes sidecar usage field '{field}' is invalid.")

    @staticmethod
    def _list_session_ids(runtime_home: Path) -> set[str]:
        sessions_root = runtime_home / "sessions"
        if not sessions_root.exists():
            return set()
        session_ids: set[str] = set()
        for path in sessions_root.glob("session_*.json"):
            stem = path.stem
            prefix = "session_"
            if stem.startswith(prefix):
                session_ids.add(stem[len(prefix) :])
        return session_ids

    @classmethod
    def _discover_session_id(cls, *, runtime_home: Path, prior_session_ids: set[str]) -> str | None:
        current_session_ids = cls._list_session_ids(runtime_home)
        new_session_ids = sorted(current_session_ids - prior_session_ids)
        if new_session_ids:
            return new_session_ids[-1]
        return None

    @staticmethod
    def _strip_ansi(text: str) -> str:
        ansi_escape = re.compile(r"\x1B(?:[@-Z\\-_]|\[[0-?]*[ -/]*[@-~])")
        return ansi_escape.sub("", text)

    @staticmethod
    def _provider_error(output: str) -> str | None:
        markers = (
            "API call failed",
            "Non-retryable client error detected",
            "RateLimitError",
            "usage_limit_reached",
            "Error code: 429",
        )
        if not any(marker in output for marker in markers):
            return None
        return output.strip()

    @staticmethod
    def _extract_session_id(output: str) -> str | None:
        match = re.search(r"session_id:\s*([A-Za-z0-9_\-]+)\s*$", output, re.MULTILINE)
        if not match:
            return None
        return match.group(1).strip()

    @staticmethod
    def _session_error(output: str) -> str | None:
        if "Session not found:" not in output:
            return None
        return output.strip()

    @classmethod
    def _strip_session_trailer(cls, output: str) -> str:
        session_id = cls._extract_session_id(output)
        if not session_id:
            return output
        return re.sub(
            r"\n?session_id:\s*" + re.escape(session_id) + r"\s*$",
            "",
            output,
            flags=re.MULTILINE,
        )
