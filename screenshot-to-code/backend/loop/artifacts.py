import json
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from uuid import uuid4

from loop.contracts import (
    DesignSystemPreflight,
    LoopResumeState,
    ReferenceBundle,
    RequirementsSpec,
    ValidationReport,
)


def _utc_timestamp() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")


@dataclass(frozen=True)
class ArtifactPaths:
    current_file_path: str
    current_metadata_path: str
    best_file_path: str
    best_metadata_path: str
    run_dir: str


class ValidatedLoopArtifactStore:
    def __init__(self, repo_root: Path | None = None) -> None:
        self._repo_root = repo_root or Path(__file__).resolve().parents[2]
        self._base_dir = self._repo_root / "assets" / "validated-loop"
        self._current_dir = self._base_dir / "current"
        self._best_dir = self._base_dir / "best"
        self._run_dir = self._base_dir / "history" / f"{_utc_timestamp()}-{uuid4().hex[:8]}"
        self._iterations_dir = self._run_dir / "iterations"
        self._run_best_dir = self._run_dir / "best"
        self._current_dir.mkdir(parents=True, exist_ok=True)
        self._best_dir.mkdir(parents=True, exist_ok=True)
        self._iterations_dir.mkdir(parents=True, exist_ok=True)
        self._run_best_dir.mkdir(parents=True, exist_ok=True)

    @property
    def paths(self) -> ArtifactPaths:
        return ArtifactPaths(
            current_file_path=str(self._current_dir / "index.html"),
            current_metadata_path=str(self._current_dir / "metadata.json"),
            best_file_path=str(self._best_dir / "index.html"),
            best_metadata_path=str(self._best_dir / "metadata.json"),
            run_dir=str(self._run_dir),
        )

    def persist_reference_bundle(self, reference_bundle: ReferenceBundle) -> None:
        payload = reference_bundle.model_dump(mode="json")
        current_reference = self._current_dir / "reference_bundle.json"
        current_reference.write_text(json.dumps(payload, indent=2), encoding="utf-8")
        run_reference = Path(self.paths.run_dir) / "reference_bundle.json"
        run_reference.write_text(json.dumps(payload, indent=2), encoding="utf-8")

    def persist_design_system_artifacts(
        self, *, design_system_json: str, design_system_html: str
    ) -> tuple[str, str]:
        current_dir = self._current_dir / "design-system"
        run_dir = Path(self.paths.run_dir) / "design-system"
        current_dir.mkdir(parents=True, exist_ok=True)
        run_dir.mkdir(parents=True, exist_ok=True)

        current_json_path = current_dir / "design-system.json"
        current_html_path = current_dir / "design-system.html"
        run_json_path = run_dir / "design-system.json"
        run_html_path = run_dir / "design-system.html"

        current_json_path.write_text(design_system_json, encoding="utf-8")
        current_html_path.write_text(design_system_html, encoding="utf-8")
        run_json_path.write_text(design_system_json, encoding="utf-8")
        run_html_path.write_text(design_system_html, encoding="utf-8")

        return str(run_json_path), str(run_html_path)

    @staticmethod
    def load_reference_bundle(run_dir: str) -> ReferenceBundle:
        reference_path = Path(run_dir) / "reference_bundle.json"
        payload = json.loads(reference_path.read_text(encoding="utf-8"))
        return ReferenceBundle.model_validate(payload)

    def persist_iteration_code(self, *, html: str, iteration: int) -> None:
        current_file = Path(self.paths.current_file_path)
        current_file.write_text(html, encoding="utf-8")
        iteration_file = self._iterations_dir / f"iteration-{iteration:02d}.html"
        iteration_file.write_text(html, encoding="utf-8")

    def persist_best_checkpoint(
        self,
        *,
        html: str,
        iteration: int,
        requirements: RequirementsSpec,
        validation_report: ValidationReport,
    ) -> None:
        best_file = Path(self.paths.best_file_path)
        best_file.write_text(html, encoding="utf-8")
        run_best_file = self._run_best_dir / "index.html"
        run_best_file.write_text(html, encoding="utf-8")

        payload: dict[str, Any] = {
            "updatedAt": datetime.now(timezone.utc).isoformat(),
            "iteration": iteration,
            "bestIteration": iteration,
            "bestFilePath": self.paths.best_file_path,
            "runDir": self.paths.run_dir,
            "stopReason": None,
            "requirements": requirements.model_dump(mode="json"),
            "validation": validation_report.model_dump(mode="json"),
        }
        best_metadata = Path(self.paths.best_metadata_path)
        best_metadata.write_text(json.dumps(payload, indent=2), encoding="utf-8")
        run_best_metadata = self._run_best_dir / "metadata.json"
        run_best_metadata.write_text(json.dumps(payload, indent=2), encoding="utf-8")

    def persist_metadata(
        self,
        *,
        iteration: int,
        stop_reason: str | None,
        requirements: RequirementsSpec | None,
        validation_report: ValidationReport | None,
    ) -> None:
        payload: dict[str, Any] = {
            "updatedAt": datetime.now(timezone.utc).isoformat(),
            "currentFilePath": self.paths.current_file_path,
            "runDir": self.paths.run_dir,
            "iteration": iteration,
            "stopReason": stop_reason,
            "requirements": (
                requirements.model_dump(mode="json")
                if requirements is not None
                else None
            ),
            "validation": (
                validation_report.model_dump(mode="json")
                if validation_report is not None
                else None
            ),
        }
        current_metadata = Path(self.paths.current_metadata_path)
        current_metadata.write_text(json.dumps(payload, indent=2), encoding="utf-8")
        run_metadata = Path(self.paths.run_dir) / "metadata.json"
        run_metadata.write_text(json.dumps(payload, indent=2), encoding="utf-8")

    @staticmethod
    def load_resume_state(run_dir: str) -> LoopResumeState:
        best_metadata_path = Path(run_dir) / "best" / "metadata.json"
        metadata_path = (
            best_metadata_path
            if best_metadata_path.exists()
            else Path(run_dir) / "metadata.json"
        )
        payload = json.loads(metadata_path.read_text(encoding="utf-8"))
        best_file_path = Path(run_dir) / "best" / "index.html"
        best_file_state = None
        if best_file_path.exists():
            best_file_state = {
                "path": "index.html",
                "content": best_file_path.read_text(encoding="utf-8"),
            }
        return LoopResumeState.model_validate(
            {
                "requirements": payload.get("requirements"),
                "latest_validation": payload.get("validation"),
                "best_file_state": best_file_state,
                "completed_iterations": payload.get("bestIteration")
                or payload.get("iteration", 0)
                or 0,
                "stop_reason": payload.get("stopReason"),
            }
        )


def load_design_system_preflight_from_run_dir(run_dir: str) -> DesignSystemPreflight:
    """Load design system preflight JSON from a run directory.

    Raises:
        FileNotFoundError: If the design-system.json does not exist in the run dir.
        ValueError: If the JSON content is invalid or fails validation.
    """
    design_system_path = Path(run_dir) / "design-system" / "design-system.json"
    if not design_system_path.exists():
        raise FileNotFoundError(
            f"Design system preflight not found at {design_system_path}. "
            "Ensure the run directory contains a completed design-system preflight."
        )
    try:
        payload = json.loads(design_system_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise ValueError(
            f"Design system preflight at {design_system_path} contains invalid JSON."
        ) from exc
    try:
        return DesignSystemPreflight.model_validate(payload)
    except Exception as exc:
        raise ValueError(
            f"Design system preflight at {design_system_path} failed validation."
        ) from exc


def load_design_system_preflight_from_current_cache(
    repo_root: Path | None = None,
) -> DesignSystemPreflight | None:
    """Load design system preflight from the current cache if available.

    Returns None if no current design system preflight exists.
    """
    root = repo_root or Path(__file__).resolve().parents[2]
    current_ds_path = root / "assets" / "validated-loop" / "current" / "design-system" / "design-system.json"
    if not current_ds_path.exists():
        return None
    try:
        payload = json.loads(current_ds_path.read_text(encoding="utf-8"))
        return DesignSystemPreflight.model_validate(payload)
    except Exception:
        return None


def load_reference_bundle_from_current_cache(
    repo_root: Path | None = None,
) -> ReferenceBundle | None:
    root = repo_root or Path(__file__).resolve().parents[2]
    reference_path = root / "assets" / "validated-loop" / "current" / "reference_bundle.json"
    if not reference_path.exists():
        return None
    try:
        payload = json.loads(reference_path.read_text(encoding="utf-8"))
        return ReferenceBundle.model_validate(payload)
    except Exception:
        return None
