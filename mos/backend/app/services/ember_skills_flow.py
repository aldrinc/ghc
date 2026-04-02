from __future__ import annotations

from copy import deepcopy
import json
from pathlib import Path
import re
from typing import Any

from sqlalchemy.orm import Session

from app.db.enums import ArtifactTypeEnum
from app.services.hermes_sidecar import HermesSidecarError, HermesSidecarService
from app.services.product_strategy_bundles import (
    FOUNDATIONAL_BUNDLE_TYPE,
    ProductStrategyBundlesError,
    ProductStrategyBundlesService,
    SKILLS_HANDOFF_BUNDLE_TYPE,
    SKILLS_WORKING_BUNDLE_TYPE,
)
from app.services.skills_runtime_registry import (
    DEFAULT_SKILL_BUNDLE_KEY,
    SkillsRuntimeRegistryError,
    SkillsRuntimeRegistryService,
)


class EmberSkillsFlowError(ValueError):
    """Raised when the EMBER skills flow cannot complete a stage cleanly."""


_STAGE_SPECS: dict[str, dict[str, Any]] = {
    "signal_report": {
        "artifact_type": ArtifactTypeEnum.skill_signal_report,
        "role": "signal_report",
        "runtime_profile_key": "strategy",
        "document_format": "markdown",
        "required_role_prefixes": ("foundational:",),
        "query": (
            "Read the active runtime START-HERE guide and active bundle manifest before drafting. "
            "Generate a product-scoped signal report for Ember: Brain Clarity Protocol using only the foundational docs currently mounted in the active bundle plus the installed methodology assets. "
            "Do not use historical EMBER outputs as source material. "
            "Return markdown only with a single H1, clear section headings, concrete language findings, and direct-response implications."
        ),
    },
    "angle_library": {
        "artifact_type": ArtifactTypeEnum.skill_angle_library,
        "role": "angle_library",
        "runtime_profile_key": "strategy",
        "document_format": "json",
        "required_roles": ("signal_report",),
        "query": (
            "Read the active runtime START-HERE guide and active bundle manifest before answering. "
            "Generate an EMBER angle library for Ember: Brain Clarity Protocol from the active foundational docs and signal report only. "
            "Do not use historical EMBER outputs as source material. "
            "Return JSON only with this exact shape: "
            '{ "angles": [{"angleId": string, "angleName": string, "description": string, "mechanism": string, "evidence": [string]}] }. '
            "Provide between 4 and 7 angles. Every evidence entry must be grounded in the active bundle."
        ),
    },
    "knowledge_base": {
        "artifact_type": ArtifactTypeEnum.skill_knowledge_base,
        "role": "knowledge_base",
        "runtime_profile_key": "strategy",
        "document_format": "markdown",
        "required_roles": ("signal_report", "angle_selection"),
        "query": (
            "Read the active runtime START-HERE guide and active bundle manifest before drafting. "
            "Generate a product-scoped EMBER knowledge base for Ember: Brain Clarity Protocol using the active foundational docs, signal report, and selected angle. "
            "Do not use historical EMBER outputs as source material. "
            "Return markdown only with a single H1 and sections covering audience state, mechanism, offer-relevant tensions, and page-writing implications."
        ),
    },
    "cso": {
        "artifact_type": ArtifactTypeEnum.skill_cso,
        "role": "cso",
        "runtime_profile_key": "strategy",
        "document_format": "markdown",
        "required_roles": ("signal_report", "knowledge_base", "angle_selection"),
        "query": (
            "Read the active runtime START-HERE guide and active bundle manifest before drafting. "
            "Generate a Customer Strategy Output (CSO) for Ember: Brain Clarity Protocol using the active foundational docs, signal report, knowledge base, and selected angle. "
            "Do not use historical EMBER outputs as source material. "
            "Return markdown only with a single H1 and explicit sections for target state, core problem framing, mechanism, proof strategy, objections, and copy constraints."
        ),
    },
    "offer_document": {
        "artifact_type": ArtifactTypeEnum.skill_offer_document,
        "role": "offer_document",
        "runtime_profile_key": "offer",
        "document_format": "json",
        "required_roles": ("angle_selection", "knowledge_base", "cso"),
        "query": (
            "Read the active runtime START-HERE guide and active bundle manifest before answering. "
            "Generate the EMBER offer document for Ember: Brain Clarity Protocol using the active foundational docs, selected angle, knowledge base, and CSO. "
            "Do not use historical EMBER outputs as source material. "
            "Return JSON only with this exact shape: "
            '{ "ump": string, "ums": string, "corePromise": string, "valueStackSummary": string, "guaranteeType": string | null, "pricingRationale": string, "selectedVariantId": string, "selectedVariantName": string, "offerDetailsMarkdown": string }.'
        ),
    },
    "headline_pool": {
        "artifact_type": ArtifactTypeEnum.skill_headline_pool,
        "role": "headline_pool",
        "runtime_profile_key": "offer",
        "document_format": "json",
        "required_roles": ("angle_selection", "cso", "offer_document"),
        "query": (
            "Read the active runtime START-HERE guide and active bundle manifest before answering. "
            "Generate a headline pool for Ember: Brain Clarity Protocol using the active selected angle, CSO, and offer document. "
            "Do not use historical EMBER outputs as source material. "
            "Return JSON only with this exact shape: "
            '{ "headlines": [{"headlineId": string, "headline": string, "rationale": string}] }. '
            "Provide between 12 and 20 headline candidates."
        ),
    },
    "presell_page": {
        "artifact_type": ArtifactTypeEnum.skill_presell_page,
        "role": "presell_page",
        "runtime_profile_key": "copy",
        "document_format": "markdown",
        "required_roles": ("angle_selection", "cso", "offer_document", "headline_selection"),
        "query": (
            "Read the active runtime START-HERE guide and active bundle manifest before drafting. "
            "Generate the presell page for Ember: Brain Clarity Protocol using the active selected angle, CSO, offer document, and selected headline. "
            "Do not use historical EMBER outputs as source material. "
            "Return markdown only with a single H1 and full long-form advertorial structure ready for human review."
        ),
    },
    "sales_page": {
        "artifact_type": ArtifactTypeEnum.skill_sales_page,
        "role": "sales_page",
        "runtime_profile_key": "copy",
        "document_format": "markdown",
        "required_roles": ("angle_selection", "cso", "offer_document", "headline_selection"),
        "query": (
            "Read the active runtime START-HERE guide and active bundle manifest before drafting. "
            "Generate the sales page for Ember: Brain Clarity Protocol using the active selected angle, CSO, offer document, and selected headline. "
            "Do not use historical EMBER outputs as source material. "
            "Return markdown only with a single H1 and full long-form sales-page structure ready for human review."
        ),
    },
}

_MANUAL_APPROVAL_STAGE_ROLES = {
    "signal_report",
    "knowledge_base",
    "cso",
    "offer_document",
    "presell_page",
    "sales_page",
}


class EmberSkillsFlowService:
    def __init__(
        self,
        *,
        session: Session,
        org_id: str,
        client_id: str,
        product_id: str,
        created_by_user: str | None,
    ) -> None:
        self.session = session
        self.org_id = org_id
        self.client_id = client_id
        self.product_id = product_id
        self.created_by_user = created_by_user
        self.bundle_service = ProductStrategyBundlesService(
            session=session,
            org_id=org_id,
            client_id=client_id,
            product_id=product_id,
            created_by_user=created_by_user,
        )
        self.runtime_registry = SkillsRuntimeRegistryService(
            session=session,
            org_id=org_id,
            client_id=client_id,
            product_id=product_id,
            created_by_user=created_by_user,
        )
        self.hermes = HermesSidecarService()

    def seed_working_bundle_from_foundation(self, *, allow_incomplete: bool = False) -> dict[str, Any]:
        foundational_bundle = self.bundle_service.get_active_bundle(bundle_type=FOUNDATIONAL_BUNDLE_TYPE)
        missing_foundational_doc_keys = list(
            (foundational_bundle.get("metadata") or {}).get("missingDocKeys") or []
        )
        if missing_foundational_doc_keys and not allow_incomplete:
            raise EmberSkillsFlowError(
                "Foundational bundle is incomplete and cannot seed strategy bundles yet. "
                "Missing source items: " + ", ".join(missing_foundational_doc_keys) + "."
            )
        artifact_roles = {
            item["role"]: item["artifactId"]
            for item in foundational_bundle["items"]
        }
        handoff_bundle = self.bundle_service.create_bundle(
            bundle_type=SKILLS_HANDOFF_BUNDLE_TYPE,
            title="EMBER Skills Approved Bundle",
            status="approved",
            is_active=True,
            artifact_roles=artifact_roles,
            metadata_json={
                "seededFromBundleId": foundational_bundle["id"],
                "foundationalBundleId": foundational_bundle["id"],
                "foundationalCompleteness": (foundational_bundle.get("metadata") or {}).get("isComplete"),
                "missingFoundationalDocKeys": list(
                    (foundational_bundle.get("metadata") or {}).get("missingDocKeys") or []
                ),
            },
            approved_by_user=self.created_by_user,
        )
        working_bundle = self.bundle_service.create_bundle(
            bundle_type=SKILLS_WORKING_BUNDLE_TYPE,
            title="EMBER Skills Working Bundle",
            status="draft",
            is_active=True,
            artifact_roles=artifact_roles,
            metadata_json={
                "seededFromBundleId": foundational_bundle["id"],
                "seededFromHandoffBundleId": handoff_bundle["id"],
            },
            approved_by_user=None,
        )
        self.session.commit()
        return {
            "workingBundle": working_bundle,
            "handoffBundle": handoff_bundle,
        }

    def run_stage(
        self,
        *,
        stage_key: str,
        bundle_key: str = DEFAULT_SKILL_BUNDLE_KEY,
        promote_to_active_bundle: bool = False,
    ) -> dict[str, Any]:
        spec = _STAGE_SPECS.get(stage_key)
        if spec is None:
            raise EmberSkillsFlowError(f"Unsupported EMBER stage '{stage_key}'.")
        if promote_to_active_bundle:
            raise EmberSkillsFlowError(
                "Automatic promotion is disabled for EMBER skills stages. "
                "Run the stage, review the draft in the active skills_working bundle, "
                "then approve it explicitly."
            )

        approved_bundle = self.bundle_service.get_active_bundle(bundle_type=SKILLS_HANDOFF_BUNDLE_TYPE)
        self._validate_stage_requirements(bundle_payload=approved_bundle, spec=spec, stage_key=stage_key)
        exported_bundle = self.runtime_registry.export_runtime_bundle(
            bundle_key=bundle_key,
            runtime_profile_key=spec["runtime_profile_key"],
            project_doc_bundle_id=approved_bundle["id"],
        )
        projection = self.hermes.build_runtime_projection_from_manifest(
            bundle_manifest=exported_bundle["manifest"],
            org_id=self.org_id,
            client_id=self.client_id,
            product_id=self.product_id,
            thread_id=self._stage_thread_id(
                stage_key=stage_key,
                runtime_profile_key=spec["runtime_profile_key"],
                exported_bundle=exported_bundle,
            ),
            agent_profile=spec["runtime_profile_key"],
            page_context=None,
        )
        query = self._build_stage_query(
            spec=spec,
            runtime_home=projection.runtime_home,
        )
        try:
            run_result = self.hermes.run_turn(
                runtime_home=projection.runtime_home,
                query=query,
                hermes_session_id=None,
            )
        except HermesSidecarError as exc:
            raise EmberSkillsFlowError(str(exc)) from exc

        artifact = self._persist_stage_output(
            stage_key=stage_key,
            spec=spec,
            raw_output=run_result.response_text,
            runtime_bundle_export=exported_bundle,
            hermes_session_id=run_result.hermes_session_id,
        )
        bundle_snapshot = self._upsert_artifact_to_working_bundle(
            role=spec["role"],
            artifact_id=str(artifact.id),
            source_handoff_bundle_id=approved_bundle["id"],
        )
        self.session.commit()
        return {
            "stageKey": stage_key,
            "artifactId": str(artifact.id),
            "artifactType": artifact.type.value,
            "artifactData": artifact.data,
            "workingBundle": bundle_snapshot,
            "activeHandoffBundle": approved_bundle,
            "approvalRequired": spec["role"] in _MANUAL_APPROVAL_STAGE_ROLES,
            "approvalRole": spec["role"],
            "runtimeBundleExportId": exported_bundle["id"],
            "runtimeProfileKey": spec["runtime_profile_key"],
            "hermesSessionId": run_result.hermes_session_id,
        }

    @staticmethod
    def _build_stage_query(*, spec: dict[str, Any], runtime_home: Path) -> str:
        manifest_path = runtime_home / "runtime" / "active_bundle" / "manifest.json"
        start_here_path = runtime_home / "runtime" / "START-HERE.md"
        if not manifest_path.exists():
            raise EmberSkillsFlowError(f"Runtime manifest does not exist: {manifest_path}")
        runtime_manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        projected_files = runtime_manifest.get("projectedFiles") or {}
        projected_supporting_docs = runtime_manifest.get("projectedSupportingDocs") or {}
        file_lines = [
            f"- {role}: {path}"
            for role, path in sorted(projected_files.items())
        ]
        supporting_lines = [
            f"- {role}: {path}"
            for role, path in sorted(projected_supporting_docs.items())
        ]
        return "\n".join(
            [
                "You are operating inside the local mOS EMBER skills runtime.",
                f"Read `{start_here_path}` and `{manifest_path}` before answering.",
                "The following strategy input files are mounted and readable right now:",
                *file_lines,
                "The following methodology files are mounted and readable right now:",
                *supporting_lines,
                spec["query"],
                "Do not claim that the active bundle or mounted files are inaccessible when the above files exist.",
                "Return only the exact requested markdown or JSON payload with no preamble, explanation, or refusal text.",
            ]
        )

    @staticmethod
    def _stage_thread_id(
        *,
        stage_key: str,
        runtime_profile_key: str,
        exported_bundle: dict[str, Any],
    ) -> str:
        export_hash = str(exported_bundle.get("exportHash") or "").strip()
        if not export_hash:
            raise EmberSkillsFlowError("Runtime bundle export is missing exportHash.")
        return f"strategy-stage-{runtime_profile_key}-{stage_key}-{export_hash[:16]}"

    def select_angle(
        self,
        *,
        angle_id: str,
        rationale: str,
    ) -> dict[str, Any]:
        working_bundle = self.bundle_service.get_active_bundle(bundle_type=SKILLS_WORKING_BUNDLE_TYPE)
        angle_pool = self._require_bundle_item(working_bundle, role="angle_library")
        angles = ((angle_pool["artifactData"] or {}).get("json") or {}).get("angles")
        if not isinstance(angles, list):
            raise EmberSkillsFlowError("Active angle_library artifact does not contain an angles list.")
        selected_angle = next(
            (
                angle
                for angle in angles
                if isinstance(angle, dict) and str(angle.get("angleId") or "").strip() == angle_id
            ),
            None,
        )
        if selected_angle is None:
            raise EmberSkillsFlowError(f"Angle id '{angle_id}' was not found in the active angle library.")

        artifact = self.bundle_service.create_document_artifact(
            artifact_type=ArtifactTypeEnum.skill_angle_selection,
            title="Selected Angle",
            role="angle_selection",
            document_format="json",
            markdown=None,
            json_payload={
                "selectedAngleId": angle_id,
                "rationale": rationale.strip(),
                "selectedAngle": deepcopy(selected_angle),
                "sourceArtifactId": angle_pool["artifactId"],
            },
            metadata_json={},
        )
        working_snapshot = self._upsert_artifact_to_working_bundle(
            role="angle_selection",
            artifact_id=str(artifact.id),
            source_handoff_bundle_id=self._active_handoff_bundle()["id"],
        )
        pending_handoff_bundle = self._create_pending_handoff_bundle(
            updated_roles={
                "angle_library": angle_pool["artifactId"],
                "angle_selection": str(artifact.id),
            },
            metadata_json={
                "approvalType": "angle_selection",
                "sourceWorkingBundleId": working_bundle["id"],
            },
        )
        self.session.commit()
        return {
            "artifactId": str(artifact.id),
            "artifactType": artifact.type.value,
            "artifactData": artifact.data,
            "workingBundle": working_snapshot,
            "pendingHandoffBundle": pending_handoff_bundle,
        }

    def select_headline(
        self,
        *,
        headline_id: str,
        rationale: str,
    ) -> dict[str, Any]:
        working_bundle = self.bundle_service.get_active_bundle(bundle_type=SKILLS_WORKING_BUNDLE_TYPE)
        headline_pool = self._require_bundle_item(working_bundle, role="headline_pool")
        headlines = ((headline_pool["artifactData"] or {}).get("json") or {}).get("headlines")
        if not isinstance(headlines, list):
            raise EmberSkillsFlowError("Active headline_pool artifact does not contain a headlines list.")
        selected_headline = next(
            (
                headline
                for headline in headlines
                if isinstance(headline, dict)
                and str(headline.get("headlineId") or "").strip() == headline_id
            ),
            None,
        )
        if selected_headline is None:
            raise EmberSkillsFlowError(
                f"Headline id '{headline_id}' was not found in the active headline pool."
            )

        artifact = self.bundle_service.create_document_artifact(
            artifact_type=ArtifactTypeEnum.skill_headline_selection,
            title="Selected Headline",
            role="headline_selection",
            document_format="json",
            markdown=None,
            json_payload={
                "selectedHeadlineId": headline_id,
                "rationale": rationale.strip(),
                "selectedHeadline": deepcopy(selected_headline),
                "sourceArtifactId": headline_pool["artifactId"],
            },
            metadata_json={},
        )
        working_snapshot = self._upsert_artifact_to_working_bundle(
            role="headline_selection",
            artifact_id=str(artifact.id),
            source_handoff_bundle_id=self._active_handoff_bundle()["id"],
        )
        pending_handoff_bundle = self._create_pending_handoff_bundle(
            updated_roles={
                "headline_pool": headline_pool["artifactId"],
                "headline_selection": str(artifact.id),
            },
            metadata_json={
                "approvalType": "headline_selection",
                "sourceWorkingBundleId": working_bundle["id"],
            },
        )
        self.session.commit()
        return {
            "artifactId": str(artifact.id),
            "artifactType": artifact.type.value,
            "artifactData": artifact.data,
            "workingBundle": working_snapshot,
            "pendingHandoffBundle": pending_handoff_bundle,
        }

    def approve_working_role(self, *, role: str) -> dict[str, Any]:
        normalized_role = role.strip()
        if not normalized_role:
            raise EmberSkillsFlowError("Approval role is required.")
        if normalized_role in {"angle_library", "headline_pool"}:
            raise EmberSkillsFlowError(
                f"Role '{normalized_role}' must be approved via the corresponding selection step."
            )
        if normalized_role in {"angle_selection", "headline_selection"}:
            raise EmberSkillsFlowError(
                f"Role '{normalized_role}' must be created via the corresponding selection endpoint."
            )
        working_bundle = self.bundle_service.get_active_bundle(bundle_type=SKILLS_WORKING_BUNDLE_TYPE)
        working_item = self._require_bundle_item(working_bundle, role=normalized_role)
        pending_handoff_bundle = self._create_pending_handoff_bundle(
            updated_roles={normalized_role: working_item["artifactId"]},
            metadata_json={
                "approvalType": "stage_role",
                "approvedRole": normalized_role,
                "sourceWorkingBundleId": working_bundle["id"],
            },
        )
        self.session.commit()
        return {
            "approvedRole": normalized_role,
            "artifactId": working_item["artifactId"],
            "pendingHandoffBundle": pending_handoff_bundle,
            "activeWorkingBundle": working_bundle,
        }

    def activate_handoff_bundle(self, *, bundle_id: str) -> dict[str, Any]:
        activated_bundle = self.bundle_service.activate_bundle(
            bundle_id=bundle_id,
            bundle_type=SKILLS_HANDOFF_BUNDLE_TYPE,
        )
        working_bundle = self._sync_working_bundle_from_handoff(handoff_bundle=activated_bundle)
        self.session.commit()
        return {
            "activeHandoffBundle": activated_bundle,
            "activeWorkingBundle": working_bundle,
        }

    def _persist_stage_output(
        self,
        *,
        stage_key: str,
        spec: dict[str, Any],
        raw_output: str,
        runtime_bundle_export: dict[str, Any],
        hermes_session_id: str,
    ):
        document_format = spec["document_format"]
        metadata_json = {
            "stageKey": stage_key,
            "runtimeBundleExportId": runtime_bundle_export["id"],
            "runtimeProfileKey": spec["runtime_profile_key"],
            "hermesSessionId": hermes_session_id,
        }
        if document_format == "markdown":
            markdown = raw_output.strip()
            if not markdown.startswith("# "):
                h1_index = markdown.find("# ")
                if h1_index >= 0:
                    markdown = markdown[h1_index:].strip()
            if not markdown.startswith("# "):
                raise EmberSkillsFlowError(
                    f"Stage '{stage_key}' returned markdown without a leading H1."
                )
            return self.bundle_service.create_document_artifact(
                artifact_type=spec["artifact_type"],
                title=stage_key.replace("_", " ").title(),
                role=spec["role"],
                document_format="markdown",
                markdown=markdown,
                json_payload=None,
                metadata_json=metadata_json,
            )

        payload = self._extract_json_object(raw_output)
        self._validate_json_stage(stage_key=stage_key, payload=payload)
        return self.bundle_service.create_document_artifact(
            artifact_type=spec["artifact_type"],
            title=stage_key.replace("_", " ").title(),
            role=spec["role"],
            document_format="json",
            markdown=None,
            json_payload=payload,
            metadata_json=metadata_json,
        )

    def _active_handoff_bundle(self) -> dict[str, Any]:
        return self.bundle_service.get_active_bundle(bundle_type=SKILLS_HANDOFF_BUNDLE_TYPE)

    def _active_working_bundle(self) -> dict[str, Any]:
        return self.bundle_service.get_active_bundle(bundle_type=SKILLS_WORKING_BUNDLE_TYPE)

    def _upsert_artifact_to_working_bundle(
        self,
        *,
        role: str,
        artifact_id: str,
        source_handoff_bundle_id: str,
    ) -> dict[str, Any]:
        current_bundle = self._active_working_bundle()
        artifact_roles = {
            item["role"]: item["artifactId"]
            for item in current_bundle["items"]
        }
        artifact_roles[role] = artifact_id
        return self.bundle_service.create_bundle(
            bundle_type=SKILLS_WORKING_BUNDLE_TYPE,
            title="EMBER Skills Working Bundle",
            status="draft",
            is_active=True,
            artifact_roles=artifact_roles,
            metadata_json={
                **(current_bundle.get("metadata") or {}),
                "supersededBundleId": current_bundle["id"],
                "sourceHandoffBundleId": source_handoff_bundle_id,
                "draftRole": role,
            },
            approved_by_user=None,
        )

    def _create_pending_handoff_bundle(
        self,
        *,
        updated_roles: dict[str, str],
        metadata_json: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        current_bundle = self._active_handoff_bundle()
        artifact_roles = {
            item["role"]: item["artifactId"]
            for item in current_bundle["items"]
        }
        artifact_roles.update(updated_roles)
        return self.bundle_service.create_bundle(
            bundle_type=SKILLS_HANDOFF_BUNDLE_TYPE,
            title="EMBER Skills Approved Bundle",
            status="approved",
            is_active=False,
            artifact_roles=artifact_roles,
            metadata_json={
                **(current_bundle.get("metadata") or {}),
                "supersededBundleId": current_bundle["id"],
                **(metadata_json or {}),
            },
            approved_by_user=self.created_by_user,
        )

    def _sync_working_bundle_from_handoff(self, *, handoff_bundle: dict[str, Any]) -> dict[str, Any]:
        current_working_bundle = self._active_working_bundle()
        artifact_roles = {
            item["role"]: item["artifactId"]
            for item in current_working_bundle["items"]
        }
        artifact_roles.update(
            {
                item["role"]: item["artifactId"]
                for item in handoff_bundle["items"]
            }
        )
        return self.bundle_service.create_bundle(
            bundle_type=SKILLS_WORKING_BUNDLE_TYPE,
            title="EMBER Skills Working Bundle",
            status="draft",
            is_active=True,
            artifact_roles=artifact_roles,
            metadata_json={
                **(current_working_bundle.get("metadata") or {}),
                "supersededBundleId": current_working_bundle["id"],
                "activatedHandoffBundleId": handoff_bundle["id"],
            },
            approved_by_user=None,
        )

    @staticmethod
    def _require_bundle_item(bundle_payload: dict[str, Any], *, role: str) -> dict[str, Any]:
        item = next((candidate for candidate in bundle_payload["items"] if candidate["role"] == role), None)
        if item is None:
            raise EmberSkillsFlowError(
                f"Active skills_handoff bundle is missing required role '{role}'."
            )
        return item

    @staticmethod
    def _validate_stage_requirements(
        *,
        bundle_payload: dict[str, Any],
        spec: dict[str, Any],
        stage_key: str,
    ) -> None:
        roles = {
            str(item.get("role") or "").strip()
            for item in bundle_payload.get("items") or []
            if isinstance(item, dict)
        }
        missing_roles = [
            role
            for role in spec.get("required_roles") or ()
            if role not in roles
        ]
        if missing_roles:
            raise EmberSkillsFlowError(
                f"Stage '{stage_key}' requires prior approved roles: {', '.join(missing_roles)}."
            )

        for prefix in spec.get("required_role_prefixes") or ():
            if not any(role.startswith(prefix) for role in roles):
                raise EmberSkillsFlowError(
                    f"Stage '{stage_key}' requires at least one approved role with prefix '{prefix}'."
                )

        required_foundational_doc_keys = [
            str(key).strip()
            for key in spec.get("required_foundational_doc_keys") or ()
            if str(key).strip()
        ]
        if required_foundational_doc_keys:
            missing_foundational_doc_keys = set(
                (bundle_payload.get("metadata") or {}).get("missingFoundationalDocKeys") or []
            )
            blocked_doc_keys = [
                key for key in required_foundational_doc_keys if key in missing_foundational_doc_keys
            ]
            if blocked_doc_keys:
                raise EmberSkillsFlowError(
                    f"Stage '{stage_key}' is blocked by missing foundational source items: "
                    f"{', '.join(blocked_doc_keys)}."
                )

    @staticmethod
    def _extract_json_object(raw_output: str) -> dict[str, Any]:
        text = raw_output.strip()
        try:
            payload = json.loads(text)
        except json.JSONDecodeError:
            match = re.search(r"\{.*\}", text, flags=re.DOTALL)
            if not match:
                raise EmberSkillsFlowError("Hermes did not return the required JSON object.")
            try:
                payload = json.loads(match.group(0))
            except json.JSONDecodeError as exc:
                raise EmberSkillsFlowError("Hermes returned invalid JSON.") from exc
        if not isinstance(payload, dict):
            raise EmberSkillsFlowError("Hermes JSON payload must be an object.")
        return payload

    @staticmethod
    def _validate_json_stage(*, stage_key: str, payload: dict[str, Any]) -> None:
        if stage_key == "angle_library":
            angles = payload.get("angles")
            if not isinstance(angles, list) or len(angles) < 4:
                raise EmberSkillsFlowError("angle_library must contain at least four angles.")
            for index, angle in enumerate(angles):
                if not isinstance(angle, dict):
                    raise EmberSkillsFlowError(f"angles[{index}] must be an object.")
                required_keys = ("angleId", "angleName", "description", "mechanism", "evidence")
                for key in required_keys:
                    if key == "evidence":
                        if not isinstance(angle.get(key), list) or not angle.get(key):
                            raise EmberSkillsFlowError(
                                f"angles[{index}].evidence must be a non-empty list."
                            )
                        continue
                    if not isinstance(angle.get(key), str) or not str(angle.get(key)).strip():
                        raise EmberSkillsFlowError(
                            f"angles[{index}].{key} must be a non-empty string."
                        )
            return

        if stage_key == "headline_pool":
            headlines = payload.get("headlines")
            if not isinstance(headlines, list) or len(headlines) < 12:
                raise EmberSkillsFlowError("headline_pool must contain at least twelve headlines.")
            for index, headline in enumerate(headlines):
                if not isinstance(headline, dict):
                    raise EmberSkillsFlowError(f"headlines[{index}] must be an object.")
                for key in ("headlineId", "headline", "rationale"):
                    if not isinstance(headline.get(key), str) or not str(headline.get(key)).strip():
                        raise EmberSkillsFlowError(
                            f"headlines[{index}].{key} must be a non-empty string."
                        )
            return

        if stage_key == "offer_document":
            required_keys = (
                "ump",
                "ums",
                "corePromise",
                "valueStackSummary",
                "pricingRationale",
                "selectedVariantId",
                "selectedVariantName",
                "offerDetailsMarkdown",
            )
            for key in required_keys:
                if not isinstance(payload.get(key), str) or not str(payload.get(key)).strip():
                    raise EmberSkillsFlowError(f"offer_document.{key} must be a non-empty string.")
            guarantee_type = payload.get("guaranteeType")
            if guarantee_type is not None and not isinstance(guarantee_type, str):
                raise EmberSkillsFlowError("offer_document.guaranteeType must be a string or null.")
            return

        raise EmberSkillsFlowError(f"Unsupported JSON validation stage '{stage_key}'.")
