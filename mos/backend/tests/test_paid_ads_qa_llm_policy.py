from __future__ import annotations

from datetime import datetime, timezone
from types import SimpleNamespace
from uuid import uuid4

import pytest
from sqlalchemy import select

from app.db.models import PaidAdsQaRun
from app.routers import meta_ads as meta_ads_router
from app.services import paid_ads_qa
from app.services.paid_ads_qa import (
    RULESET_VERSION,
    evaluate_meta_creative_policy_with_llm,
    get_ruleset,
)


def _spec(copy: str) -> dict[str, object]:
    return {
        "id": "creative-spec-1",
        "asset_id": "asset-1",
        "primary_text": copy,
        "headline": "Learn More",
        "description": "",
        "metadata_json": {},
    }


def _asset() -> SimpleNamespace:
    return SimpleNamespace(
        id="asset-1",
        storage_key="creative/test.jpg",
        content_type="image/jpeg",
        ai_metadata={},
    )


class _FakeMediaStorage:
    def download_bytes(self, *, key: str, bucket: str | None = None):
        assert key == "creative/test.jpg"
        return b"fake-image", "image/jpeg"


def test_meta_policy_classification_uses_llm_image_context(monkeypatch: pytest.MonkeyPatch) -> None:
    captured: dict[str, object] = {}

    def fake_llm(*, context, image_data_url):
        captured["context"] = context
        captured["image_data_url"] = image_data_url
        return {
            "model": "gpt-5.4-mini",
            "reasoningEffort": "high",
            "passed": False,
            "findings": [
                {
                    "ruleId": "META-IMAGE-001",
                    "status": "failed",
                    "title": "Visual policy risk",
                    "message": "The LLM visual review found fake authority framing in the creative.",
                    "evidence": {
                        "policyTrace": ["Meta Unacceptable Business Practices"],
                        "observations": ["medical authority visual framing"],
                    },
                    "fixGuidance": ["Use a neutral editorial visual."],
                }
            ],
            "revisionGuidance": ["Replace the image."],
        }

    monkeypatch.setattr(paid_ads_qa, "MediaStorage", _FakeMediaStorage)
    monkeypatch.setattr(paid_ads_qa, "_call_paid_ads_policy_llm", fake_llm)

    findings = evaluate_meta_creative_policy_with_llm(
        ruleset=get_ruleset(RULESET_VERSION),
        spec=_spec("Testosterone support can be discussed in general educational copy."),
        asset=_asset(),
        copy_blob="Testosterone support can be discussed in general educational copy.",
        destination_url="https://example.com/presale",
        page={"bodyText": "Privacy. Contact. Educational article."},
        artifact_ref="creative-spec-1",
    )

    assert [finding["ruleId"] for finding in findings] == ["META-IMAGE-001"]
    assert str(captured["image_data_url"]).startswith("data:image/jpeg;base64,")
    context = captured["context"]
    assert isinstance(context, dict)
    assert context["method"] == "LLM-only policy classification for copy, image, and landing-page risk."


def test_meta_policy_llm_flags_rejected_campaign_patterns_without_banning_testosterone(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    rejected_patterns = [
        (
            "GLP-1s are secretly crashing your testosterone.",
            {"META-UBP-001", "META-COPY-006"},
        ),
        (
            "Doctors did not mention what this weight loss protocol may do to your testosterone.",
            {"META-COPY-006"},
        ),
        (
            "If you are over 40 and gaining weight, this quiz explains what may be happening.",
            {"META-COPY-006"},
        ),
        (
            "Your energy is dropping and your gut will not budge.",
            {"META-COPY-006"},
        ),
        (
            "Researchers found a hidden reason men may lose their drive during rapid weight loss.",
            {"META-UBP-001"},
        ),
        (
            "This old-school mistake may be secretly crashing men's results.",
            {"META-UBP-001"},
        ),
    ]

    def fake_llm(*, context, image_data_url):
        copy = str(context["ad"]["combinedCopy"])
        findings = []
        if "secretly crashing" in copy or "hidden reason" in copy:
            findings.append(
                {
                    "ruleId": "META-UBP-001",
                    "status": "failed",
                    "title": "Unacceptable business practices risk",
                    "message": "The LLM policy review traced hidden-cause health framing to Meta UBP risk.",
                    "evidence": {"policyTrace": ["Meta Unacceptable Business Practices"]},
                    "fixGuidance": ["Remove hidden-cause framing."],
                }
            )
        if "your testosterone" in copy or "you are over 40" in copy or "your gut" in copy or "Your energy" in copy:
            findings.append(
                {
                    "ruleId": "META-COPY-006",
                    "status": "failed",
                    "title": "Personal attribute risk",
                    "message": "The LLM policy review found copy asserting or implying the viewer's health/body state.",
                    "evidence": {"policyTrace": ["Meta Personal Attributes"]},
                    "fixGuidance": ["Use non-personal educational framing."],
                }
            )
        return {
            "model": "gpt-5.4-mini",
            "reasoningEffort": "high",
            "passed": not findings,
            "findings": findings,
            "revisionGuidance": [],
        }

    monkeypatch.setattr(paid_ads_qa, "MediaStorage", _FakeMediaStorage)
    monkeypatch.setattr(paid_ads_qa, "_call_paid_ads_policy_llm", fake_llm)
    ruleset = get_ruleset(RULESET_VERSION)

    for copy, expected_rule_ids in rejected_patterns:
        findings = evaluate_meta_creative_policy_with_llm(
            ruleset=ruleset,
            spec=_spec(copy),
            asset=_asset(),
            copy_blob=copy,
            destination_url="https://example.com/presale",
            page={"bodyText": "Privacy. Contact. Educational article."},
            artifact_ref="creative-spec-1",
        )
        assert expected_rule_ids.issubset({finding["ruleId"] for finding in findings})

    allowed = "Testosterone support is discussed in this educational article."
    findings = evaluate_meta_creative_policy_with_llm(
        ruleset=ruleset,
        spec=_spec(allowed),
        asset=_asset(),
        copy_blob=allowed,
        destination_url="https://example.com/presale",
        page={"bodyText": "Privacy. Contact. Educational article."},
        artifact_ref="creative-spec-1",
    )
    assert findings == []


def test_meta_publish_gate_requires_matching_passed_paid_ads_qa_run(api_client, db_session) -> None:
    client_resp = api_client.post("/clients", json={"name": "QA Gate Client", "industry": "Health"})
    assert client_resp.status_code == 201
    client_id = client_resp.json()["id"]
    product_resp = api_client.post("/products", json={"clientId": client_id, "title": "QA Gate Product"})
    assert product_resp.status_code == 201
    campaign_resp = api_client.post(
        "/campaigns",
        json={
            "client_id": client_id,
            "product_id": product_resp.json()["id"],
            "name": "QA Gate Campaign",
            "channels": ["facebook"],
            "asset_brief_types": ["image"],
        },
    )
    assert campaign_resp.status_code == 201
    campaign_id = campaign_resp.json()["id"]
    asset_id = str(uuid4())

    missing = meta_ads_router._paid_ads_qa_publish_gate_blocker(
        session=db_session,
        org_id="00000000-0000-0000-0000-000000000001",
        campaign_id=campaign_id,
        generation_key="batch:latest-run",
        selected_asset_ids=[asset_id],
    )
    assert missing is not None
    assert "full paid ads QA" in missing

    db_session.add(
        PaidAdsQaRun(
            org_id="00000000-0000-0000-0000-000000000001",
            client_id=client_id,
            campaign_id=campaign_id,
            platform="meta",
            subject_type="campaign",
            subject_id=campaign_id,
            ruleset_version=RULESET_VERSION,
            status="failed",
            blocker_count=1,
            high_count=0,
            medium_count=0,
            low_count=0,
            needs_manual_review_count=0,
            checked_rule_ids=["META-POLICY-LLM-001"],
            report_markdown="# Paid Ads QA Report\n\nStatus: failed",
            metadata_json={
                "generationKey": "batch:latest-run",
                "generationAssetIds": [asset_id],
            },
            completed_at=datetime.now(timezone.utc),
        )
    )
    db_session.commit()

    failed = meta_ads_router._paid_ads_qa_publish_gate_blocker(
        session=db_session,
        org_id="00000000-0000-0000-0000-000000000001",
        campaign_id=campaign_id,
        generation_key="batch:latest-run",
        selected_asset_ids=[asset_id],
    )
    assert failed is not None
    assert "status is failed" in failed

    latest = db_session.scalars(select(PaidAdsQaRun).where(PaidAdsQaRun.campaign_id == campaign_id)).first()
    assert latest is not None
    latest.status = "passed"
    db_session.add(latest)
    db_session.commit()

    assert (
        meta_ads_router._paid_ads_qa_publish_gate_blocker(
            session=db_session,
            org_id="00000000-0000-0000-0000-000000000001",
            campaign_id=campaign_id,
            generation_key="batch:latest-run",
            selected_asset_ids=[asset_id],
        )
        is None
    )
