from __future__ import annotations

from typing import Any, Dict, Iterable, List, Optional

import sqlalchemy as sa
from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.db.models import (
    Ad,
    AdCreative,
    AdCreativeMembership,
    AdTeardown,
    AdTeardownAdCopyBlock,
    AdTeardownAssertion,
    AdTeardownAssertionEvidence,
    AdTeardownCTA,
    AdTeardownEvidenceItem,
    AdTeardownNarrativeBeat,
    AdTeardownNumericClaim,
    AdTeardownProductionRequirement,
    AdTeardownProofUsage,
    AdTeardownStoryboardScene,
    AdTeardownTargetingSignal,
    AdTeardownTranscriptSegment,
    Brand,
    MediaAsset,
)
from app.db.repositories.base import Repository
from app.domain import taxonomy
from app.schemas.teardowns import (
    TeardownAssertionInput,
    TeardownAssertionResponse,
    TeardownEvidenceInput,
    TeardownEvidenceResponse,
    TeardownResponse,
    TeardownUpsertRequest,
)


class TeardownsRepository(Repository):
    def __init__(self, session: Session) -> None:
        super().__init__(session)

    # ---------- helpers ----------
    def _resolve_creative_id(self, org_id: str, *, creative_id: Optional[str], ad_id: Optional[str]) -> str:
        if creative_id:
            creative = self.session.scalar(
                select(AdCreative).where(AdCreative.id == creative_id, AdCreative.org_id == org_id)
            )
            if not creative:
                raise ValueError("Creative not found for org")
            return str(creative.id)

        if not ad_id:
            raise ValueError("Provide either creative_id or ad_id")

        stmt = (
            select(AdCreative.id)
            .join(AdCreativeMembership, AdCreativeMembership.creative_id == AdCreative.id)
            .join(Ad, Ad.id == AdCreativeMembership.ad_id)
            .join(Brand, Brand.id == Ad.brand_id)
            .where(Ad.id == ad_id, Brand.org_id == org_id)
        )
        creative_id_row = self.session.scalar(stmt)
        if not creative_id_row:
            raise ValueError("Ad has no creative membership or not in org")
        return str(creative_id_row)

    def _validate_org_creative(self, org_id: str, creative_id: str) -> AdCreative:
        creative = self.session.scalar(
            select(AdCreative).where(AdCreative.id == creative_id, AdCreative.org_id == org_id)
        )
        if not creative:
            raise ValueError("Creative not found for org")
        return creative

    # ---------- write ----------
    def upsert_teardown(
        self,
        *,
        org_id: str,
        payload: TeardownUpsertRequest,
        created_by_user_id: Optional[str],
    ) -> TeardownResponse:
        creative_id = self._resolve_creative_id(org_id, creative_id=payload.creative_id, ad_id=payload.ad_id)
        creative = self._validate_org_creative(org_id, creative_id)
        taxonomy.funnel_stage_allowed(payload.funnel_stage)

        teardown = self.session.scalar(
            select(AdTeardown).where(
                AdTeardown.org_id == org_id,
                AdTeardown.creative_id == creative.id,
                AdTeardown.is_canonical.is_(True),
            )
        )

        if teardown:
            teardown.schema_version = payload.schema_version or teardown.schema_version
            teardown.captured_at = payload.captured_at or teardown.captured_at
            teardown.funnel_stage = payload.funnel_stage or teardown.funnel_stage
            teardown.one_liner = payload.one_liner or teardown.one_liner
            teardown.algorithmic_thesis = payload.algorithmic_thesis or teardown.algorithmic_thesis
            teardown.hook_score = payload.hook_score if payload.hook_score is not None else teardown.hook_score
            teardown.raw_payload = payload.raw_payload or teardown.raw_payload or {}
            teardown.client_id = payload.client_id or teardown.client_id
            teardown.campaign_id = payload.campaign_id or teardown.campaign_id
            teardown.research_run_id = payload.research_run_id or teardown.research_run_id
        else:
            teardown = AdTeardown(
                org_id=org_id,
                creative_id=creative.id,
                client_id=payload.client_id,
                campaign_id=payload.campaign_id,
                research_run_id=payload.research_run_id,
                created_by_user_id=created_by_user_id,
                schema_version=payload.schema_version or 1,
                captured_at=payload.captured_at,
                funnel_stage=payload.funnel_stage,
                one_liner=payload.one_liner,
                algorithmic_thesis=payload.algorithmic_thesis,
                hook_score=payload.hook_score,
                raw_payload=payload.raw_payload or {},
                is_canonical=True,
            )
            self.session.add(teardown)

        self.session.flush()
        ref_map = self._replace_evidence(teardown.id, payload.evidence_items)
        self._replace_assertions(
            teardown.id,
            payload.assertions,
            ref_map,
            created_by_user_id=created_by_user_id,
        )
        self.session.commit()
        self.session.refresh(teardown)
        return self.get_by_id(org_id=org_id, teardown_id=str(teardown.id), include_children=True)

    def _replace_evidence(self, teardown_id: str, evidence_items: Iterable[TeardownEvidenceInput]) -> dict[str, str]:
        self.session.execute(delete(AdTeardownEvidenceItem).where(AdTeardownEvidenceItem.teardown_id == teardown_id))
        self.session.flush()

        ref_to_id: dict[str, str] = {}
        storyboard_seen: set[int] = set()
        for idx, ev in enumerate(evidence_items):
            ev_type = taxonomy.assert_one_of("evidence_type", ev.evidence_type)
            if not ev_type:
                raise ValueError("evidence_type is required")

            base = AdTeardownEvidenceItem(
                teardown_id=teardown_id,
                evidence_type=ev_type,
                start_ms=ev.start_ms,
                end_ms=ev.end_ms,
            )
            self.session.add(base)
            self.session.flush()

            ref = ev.client_ref or f"evidence_{idx}"
            ref_to_id[ref] = str(base.id)

            if ev_type == "transcript_segment":
                speaker = taxonomy.assert_one_of("speaker_role", ev.speaker_role)
                segment = AdTeardownTranscriptSegment(
                    evidence_item_id=base.id,
                    speaker_role=speaker,
                    spoken_text=ev.spoken_text,
                    onscreen_text=ev.onscreen_text,
                    audio_notes=ev.audio_notes,
                )
                self.session.add(segment)
            elif ev_type == "storyboard_scene":
                if ev.scene_no is None:
                    raise ValueError("scene_no required for storyboard_scene")
                if ev.scene_no in storyboard_seen:
                    raise ValueError(f"Duplicate scene_no {ev.scene_no} in storyboard")
                storyboard_seen.add(ev.scene_no)
                scene = AdTeardownStoryboardScene(
                    evidence_item_id=base.id,
                    scene_no=ev.scene_no,
                    visual_description=ev.visual_description,
                    action_blocking=ev.action_blocking,
                    narrative_job=ev.narrative_job,
                    onscreen_text=ev.onscreen_text,
                )
                self.session.add(scene)
            elif ev_type == "numeric_claim":
                verification_status = taxonomy.assert_one_of("verification_status", ev.verification_status or "unverified")
                claim = AdTeardownNumericClaim(
                    evidence_item_id=base.id,
                    value_numeric=ev.value_numeric,
                    unit=ev.unit,
                    claim_text=ev.claim_text or "",
                    claim_topic=ev.claim_topic,
                    verification_status=verification_status or "unverified",
                    source_url=ev.source_url,
                )
                self.session.add(claim)
            elif ev_type == "targeting_signal":
                modality = taxonomy.assert_one_of("signal_modality", ev.modality)
                category = taxonomy.assert_one_of("signal_category", ev.category)
                if not ev.value:
                    raise ValueError("value required for targeting_signal")
                signal = AdTeardownTargetingSignal(
                    evidence_item_id=base.id,
                    modality=modality or "",
                    category=category or "",
                    value=ev.value,
                    is_observation=ev.is_observation if ev.is_observation is not None else True,
                    confidence=ev.confidence,
                )
                self.session.add(signal)
            elif ev_type == "narrative_beat":
                beat_key = taxonomy.assert_one_of("beat_key", ev.beat_key)
                beat = AdTeardownNarrativeBeat(
                    evidence_item_id=base.id,
                    beat_key=beat_key or "",
                    description=ev.description or "",
                )
                self.session.add(beat)
            elif ev_type == "proof_usage":
                proof_type = taxonomy.assert_one_of("proof_type", ev.proof_type)
                proof = AdTeardownProofUsage(
                    evidence_item_id=base.id,
                    proof_type=proof_type or "",
                    description=ev.proof_description,
                )
                self.session.add(proof)
            elif ev_type == "cta":
                cta_kind = taxonomy.assert_one_of("cta_kind", ev.cta_kind)
                cta = AdTeardownCTA(
                    evidence_item_id=base.id,
                    cta_kind=cta_kind or "",
                    cta_text=ev.cta_text or "",
                    offer_stack_present=ev.offer_stack_present,
                    risk_reversal_present=ev.risk_reversal_present,
                    notes=ev.notes,
                )
                self.session.add(cta)
            elif ev_type == "production_requirement":
                req_type = taxonomy.assert_one_of("req_type", ev.req_type)
                req = AdTeardownProductionRequirement(
                    evidence_item_id=base.id,
                    req_type=req_type or "",
                    value=ev.req_value or "",
                )
                self.session.add(req)
            elif ev_type == "ad_copy_block":
                field = taxonomy.assert_one_of("ad_copy_field", ev.copy_field)
                copy = AdTeardownAdCopyBlock(
                    evidence_item_id=base.id,
                    field=field or "",
                    text=ev.copy_text,
                    raw_text=ev.copy_raw_text,
                    language=ev.copy_language,
                )
                self.session.add(copy)
            else:
                raise ValueError(f"Unsupported evidence_type {ev_type}")

        self.session.flush()
        return ref_to_id

    def _replace_assertions(
        self,
        teardown_id: str,
        assertions: Iterable[TeardownAssertionInput],
        evidence_ref_map: dict[str, str],
        created_by_user_id: Optional[str],
    ) -> None:
        self.session.execute(
            delete(AdTeardownAssertion).where(AdTeardownAssertion.teardown_id == teardown_id)
        )
        self.session.flush()

        # evidence map by client_ref to id
        evidence_rows = self.session.execute(
            select(AdTeardownEvidenceItem.id).where(AdTeardownEvidenceItem.teardown_id == teardown_id)
        ).all()
        evidence_ids = {str(row.id) for row in evidence_rows}

        for idx, assertion in enumerate(assertions):
            assertion_type = taxonomy.assertion_type_allowed(assertion.assertion_type)
            if not assertion_type:
                raise ValueError("assertion_type is required")
            row = AdTeardownAssertion(
                teardown_id=teardown_id,
                assertion_type=assertion_type,
                assertion_text=assertion.assertion_text,
                confidence=assertion.confidence,
                created_by_user_id=created_by_user_id,
            )
            self.session.add(row)
            self.session.flush()

            if assertion.evidence_refs:
                for ref in assertion.evidence_refs:
                    mapped = evidence_ref_map.get(ref) or ref if ref in evidence_ids else None
                    if not mapped:
                        # allow raw evidence id references
                        if ref in evidence_ids:
                            mapped = ref
                        else:
                            raise ValueError(f"Unknown evidence_ref {ref} for assertion")
                    link = AdTeardownAssertionEvidence(assertion_id=row.id, evidence_item_id=mapped)
                    self.session.add(link)
        self.session.flush()

    # ---------- read ----------
    def get_by_id(self, *, org_id: str, teardown_id: str, include_children: bool) -> TeardownResponse:
        teardown = self.session.scalar(
            select(AdTeardown).where(AdTeardown.id == teardown_id, AdTeardown.org_id == org_id)
        )
        if not teardown:
            raise ValueError("Teardown not found")
        return self._serialize_teardown(teardown, include_children=include_children)

    def get_canonical_for_creative(self, *, org_id: str, creative_id: str, include_children: bool) -> TeardownResponse:
        teardown = self.session.scalar(
            select(AdTeardown)
            .where(
                AdTeardown.org_id == org_id,
                AdTeardown.creative_id == creative_id,
                AdTeardown.is_canonical.is_(True),
            )
            .order_by(AdTeardown.created_at.desc())
        )
        if not teardown:
            raise ValueError("Teardown not found")
        return self._serialize_teardown(teardown, include_children=include_children)

    def get_canonical_for_ad(self, *, org_id: str, ad_id: str, include_children: bool) -> TeardownResponse:
        creative_id = self._resolve_creative_id(org_id, creative_id=None, ad_id=ad_id)
        return self.get_canonical_for_creative(org_id=org_id, creative_id=creative_id, include_children=include_children)

    def _serialize_teardown(self, teardown: AdTeardown, *, include_children: bool) -> TeardownResponse:
        creative = self.session.get(AdCreative, teardown.creative_id)
        brand = self.session.get(Brand, creative.brand_id) if creative else None
        primary_media_url = None
        if creative and creative.primary_media_asset_id:
            media = self.session.get(MediaAsset, creative.primary_media_asset_id)
            membership_ad_id = self.session.scalar(
                select(AdCreativeMembership.ad_id)
                .where(AdCreativeMembership.creative_id == creative.id)
                .limit(1)
            )
            if media and membership_ad_id:
                preview = (
                    f"/ads/{membership_ad_id}/media/{media.id}/preview"
                    if media.preview_storage_key or media.storage_key
                    else None
                )
                original = f"/ads/{membership_ad_id}/media/{media.id}" if media.storage_key else None
                primary_media_url = preview or original or media.stored_url or media.source_url

        evidence_items: list[TeardownEvidenceResponse] = []
        assertions: list[TeardownAssertionResponse] = []

        if include_children:
            evidence_items = self._load_evidence(teardown.id)
            assertions = self._load_assertions(teardown.id)

        return TeardownResponse(
            id=str(teardown.id),
            org_id=str(teardown.org_id),
            creative_id=str(teardown.creative_id),
            brand_id=str(creative.brand_id) if creative else None,
            brand_name=brand.canonical_name if brand else None,
            channel=creative.channel.value if creative and hasattr(creative, "channel") else None,
            creative_fingerprint=creative.creative_fingerprint if creative else None,
            primary_media_asset_url=primary_media_url,
            client_id=str(teardown.client_id) if teardown.client_id else None,
            campaign_id=str(teardown.campaign_id) if teardown.campaign_id else None,
            research_run_id=str(teardown.research_run_id) if teardown.research_run_id else None,
            schema_version=teardown.schema_version,
            captured_at=teardown.captured_at,
            funnel_stage=teardown.funnel_stage,
            one_liner=teardown.one_liner,
            algorithmic_thesis=teardown.algorithmic_thesis,
            hook_score=teardown.hook_score,
            raw_payload=teardown.raw_payload or {},
            is_canonical=teardown.is_canonical,
            created_at=teardown.created_at,
            updated_at=teardown.updated_at,
            evidence_items=evidence_items,
            assertions=assertions,
        )

    def _load_evidence(self, teardown_id: str) -> list[TeardownEvidenceResponse]:
        evidence_rows = list(
            self.session.scalars(
                select(AdTeardownEvidenceItem).where(AdTeardownEvidenceItem.teardown_id == teardown_id)
            ).all()
        )
        responses: list[TeardownEvidenceResponse] = []
        for item in evidence_rows:
            payload: Dict[str, Any] = {}
            ev_type = item.evidence_type
            if ev_type == "transcript_segment":
                seg = self.session.get(AdTeardownTranscriptSegment, item.id)
                if seg:
                    payload = {
                        "speaker_role": seg.speaker_role,
                        "spoken_text": seg.spoken_text,
                        "onscreen_text": seg.onscreen_text,
                        "audio_notes": seg.audio_notes,
                    }
            elif ev_type == "storyboard_scene":
                scene = self.session.get(AdTeardownStoryboardScene, item.id)
                if scene:
                    payload = {
                        "scene_no": scene.scene_no,
                        "visual_description": scene.visual_description,
                        "action_blocking": scene.action_blocking,
                        "narrative_job": scene.narrative_job,
                        "onscreen_text": scene.onscreen_text,
                    }
            elif ev_type == "numeric_claim":
                claim = self.session.get(AdTeardownNumericClaim, item.id)
                if claim:
                    payload = {
                        "value_numeric": claim.value_numeric,
                        "unit": claim.unit,
                        "claim_text": claim.claim_text,
                        "claim_topic": claim.claim_topic,
                        "verification_status": claim.verification_status,
                        "source_url": claim.source_url,
                    }
            elif ev_type == "targeting_signal":
                signal = self.session.get(AdTeardownTargetingSignal, item.id)
                if signal:
                    payload = {
                        "modality": signal.modality,
                        "category": signal.category,
                        "value": signal.value,
                        "is_observation": signal.is_observation,
                        "confidence": signal.confidence,
                    }
            elif ev_type == "narrative_beat":
                beat = self.session.get(AdTeardownNarrativeBeat, item.id)
                if beat:
                    payload = {
                        "beat_key": beat.beat_key,
                        "description": beat.description,
                    }
            elif ev_type == "proof_usage":
                proof = self.session.get(AdTeardownProofUsage, item.id)
                if proof:
                    payload = {
                        "proof_type": proof.proof_type,
                        "description": proof.description,
                    }
            elif ev_type == "cta":
                cta = self.session.get(AdTeardownCTA, item.id)
                if cta:
                    payload = {
                        "cta_kind": cta.cta_kind,
                        "cta_text": cta.cta_text,
                        "offer_stack_present": cta.offer_stack_present,
                        "risk_reversal_present": cta.risk_reversal_present,
                        "notes": cta.notes,
                    }
            elif ev_type == "production_requirement":
                req = self.session.get(AdTeardownProductionRequirement, item.id)
                if req:
                    payload = {
                        "req_type": req.req_type,
                        "value": req.value,
                    }
            elif ev_type == "ad_copy_block":
                copy = self.session.get(AdTeardownAdCopyBlock, item.id)
                if copy:
                    payload = {
                        "field": copy.field,
                        "text": copy.text,
                        "raw_text": copy.raw_text,
                        "language": copy.language,
                    }

            responses.append(
                TeardownEvidenceResponse(
                    id=str(item.id),
                    evidence_type=item.evidence_type,
                    start_ms=item.start_ms,
                    end_ms=item.end_ms,
                    payload=payload,
                )
            )
        return responses

    def _load_assertions(self, teardown_id: str) -> list[TeardownAssertionResponse]:
        assertion_rows = list(
            self.session.scalars(
                select(AdTeardownAssertion).where(AdTeardownAssertion.teardown_id == teardown_id)
            ).all()
        )
        responses: list[TeardownAssertionResponse] = []
        for assertion in assertion_rows:
            links = list(
                self.session.scalars(
                    select(AdTeardownAssertionEvidence.evidence_item_id).where(
                        AdTeardownAssertionEvidence.assertion_id == assertion.id
                    )
                ).all()
            )
            responses.append(
                TeardownAssertionResponse(
                    id=str(assertion.id),
                    assertion_type=assertion.assertion_type,
                    assertion_text=assertion.assertion_text,
                    confidence=assertion.confidence,
                    evidence_item_ids=[str(link) for link in links],
                    created_by_user_id=str(assertion.created_by_user_id)
                    if assertion.created_by_user_id
                    else None,
                    created_at=assertion.created_at,
                )
            )
        return responses

    # ---------- search ----------
    def search(
        self,
        *,
        org_id: str,
        client_id: Optional[str] = None,
        campaign_id: Optional[str] = None,
        hook_type: Optional[str] = None,
        proof_type: Optional[str] = None,
        beat_key: Optional[str] = None,
        signal_category: Optional[str] = None,
        numeric_unit: Optional[str] = None,
        claim_topic: Optional[str] = None,
        claim_text_contains: Optional[str] = None,
        limit: int = 50,
        offset: int = 0,
        include_children: bool = False,
    ) -> list[TeardownResponse]:
        stmt = select(AdTeardown).where(AdTeardown.org_id == org_id)
        if client_id:
            stmt = stmt.where(AdTeardown.client_id == client_id)
        if campaign_id:
            stmt = stmt.where(AdTeardown.campaign_id == campaign_id)
        if hook_type:
            stmt = stmt.where(AdTeardown.raw_payload.contains({"hook_type": hook_type}))

        if proof_type:
            proof_exists = (
                select(sa.literal(1))
                .select_from(AdTeardownEvidenceItem)
                .join(AdTeardownProofUsage, AdTeardownProofUsage.evidence_item_id == AdTeardownEvidenceItem.id)
                .where(
                    AdTeardownEvidenceItem.teardown_id == AdTeardown.id,
                    AdTeardownEvidenceItem.evidence_type == "proof_usage",
                    AdTeardownProofUsage.proof_type == proof_type,
                )
                .exists()
            )
            stmt = stmt.where(proof_exists)

        if beat_key:
            beat_exists = (
                select(sa.literal(1))
                .select_from(AdTeardownEvidenceItem)
                .join(AdTeardownNarrativeBeat, AdTeardownNarrativeBeat.evidence_item_id == AdTeardownEvidenceItem.id)
                .where(
                    AdTeardownEvidenceItem.teardown_id == AdTeardown.id,
                    AdTeardownEvidenceItem.evidence_type == "narrative_beat",
                    AdTeardownNarrativeBeat.beat_key == beat_key,
                )
                .exists()
            )
            stmt = stmt.where(beat_exists)

        if signal_category:
            signal_exists = (
                select(sa.literal(1))
                .select_from(AdTeardownEvidenceItem)
                .join(AdTeardownTargetingSignal, AdTeardownTargetingSignal.evidence_item_id == AdTeardownEvidenceItem.id)
                .where(
                    AdTeardownEvidenceItem.teardown_id == AdTeardown.id,
                    AdTeardownEvidenceItem.evidence_type == "targeting_signal",
                    AdTeardownTargetingSignal.category == signal_category,
                )
                .exists()
            )
            stmt = stmt.where(signal_exists)

        if numeric_unit or claim_topic or claim_text_contains:
            claim_exists = (
                select(sa.literal(1))
                .select_from(AdTeardownEvidenceItem)
                .join(AdTeardownNumericClaim, AdTeardownNumericClaim.evidence_item_id == AdTeardownEvidenceItem.id)
                .where(AdTeardownEvidenceItem.teardown_id == AdTeardown.id)
            )
            if numeric_unit:
                claim_exists = claim_exists.where(AdTeardownNumericClaim.unit == numeric_unit)
            if claim_topic:
                claim_exists = claim_exists.where(AdTeardownNumericClaim.claim_topic == claim_topic)
            if claim_text_contains:
                claim_exists = claim_exists.where(
                    AdTeardownNumericClaim.claim_text.ilike(f"%{claim_text_contains}%")
                )
            stmt = stmt.where(claim_exists.exists())

        stmt = stmt.order_by(AdTeardown.created_at.desc()).limit(limit).offset(offset)
        teardowns = list(self.session.scalars(stmt).all())
        return [self._serialize_teardown(td, include_children=include_children) for td in teardowns]
