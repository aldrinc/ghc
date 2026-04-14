from __future__ import annotations

import json
from pathlib import Path

from app.services.ember_import_adapter import build_ember_manual_creative_context_request


def _write(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def _write_minimal_ember_bundle(root: Path) -> Path:
    ember_root = root / "EMBER"
    _write(
        ember_root / "EMBER-KNOWLEDGE-BASE.md",
        """# EMBER Knowledge Base

**Full product name:** Ember: Brain Clarity Protocol
**Format:** Gummy
**Active ingredient:** Creapure creatine monohydrate, 5g clinical dose per serving
**Guarantee:** Complete Clarity Promise
**Voice register:** Clinical expertise softened by personal vulnerability.
**Key line:** "I spent 18 years studying why brains fail. Then mine went silent."
""",
    )
    _write(
        ember_root / "signal-hunter" / "SIGNAL-HUNTER-REPORT-EMBER.md",
        """# SIGNAL HUNTER REPORT: EMBER

### Dominant Buyer Identity (F3)
Previously sharp, capable women who now fear they are losing their mind.
""",
    )
    _write(
        ember_root / "cso" / "EMBER-CSO.md",
        """# EMBER COPY STRATEGY OBJECT (CSO)

### 3. audience_state
Capable women in perimenopause who feel like their brain is betraying them.

### 5. desired_outcome
Trust my own brain again.

### 6. angle_name
Not Dementia — Depletion: Perimenopause Brain Fog as Creatine Fuel Deficit

### 7. belief_shift
- **Current belief:** It's aging.
- **Bridge:** The brain may be running low on fuel.
- **New belief:** I can refuel it.

### 8. mechanism_frame
Creatine helps recharge ATP and supports brain energy.

### 9. proof_stack
1. Women carry lower creatine stores than men.
2. Creatine supports working memory.
3. Buyers repeatedly describe dementia fear and doctor dismissal.

### 11. offer_frame
30 Day Supply / 60 Day Supply / 90 Day Supply.

### 12. cta_goal
Start Your Brain Clarity Protocol

### 13. inference_boundary
Use adjacent evidence, not disease-treatment claims.
""",
    )
    _write(
        ember_root / "offer" / "EMBER-OFFER-DOCUMENT.json",
        json.dumps(
            {
                "protocol_description": "Take two gummies each morning.",
                "bundle_tiers": [
                    {
                        "tier_name": "30 Day Supply",
                        "contents": "1x supply + guide",
                        "price": "$42",
                        "compare_at": "$67",
                        "savings": "Save $25",
                        "per_day_cost": "$1.40/day",
                        "framing": "Try It",
                        "is_default": False,
                    },
                    {
                        "tier_name": "60 Day Supply",
                        "contents": "2x supply + tracker + free shipping",
                        "price": "$64",
                        "compare_at": "$134",
                        "savings": "Save $70",
                        "per_day_cost": "$1.07/day",
                        "framing": "Most Popular",
                        "is_default": True,
                    },
                ],
                "guarantee": {
                    "name": "Complete Clarity Promise",
                    "terms": "Finish 30 days and get a refund if the fog does not lift.",
                    "confidence_language": "We expect you'll feel the shift before day 30.",
                },
                "price_anchor": {
                    "current_spend": "Most women already spend too much on symptom-chasing fixes.",
                    "daily_cost_frame": "Less than a daily coffee.",
                    "per_incident_frame": "Less than one doctor copay.",
                },
                "upsell_structure": {
                    "post_purchase": "Add another 30 Day Supply at 40% off.",
                    "cross_sell": "Pair with a sleep protocol.",
                    "subscription_frame": "Save 15% on every resupply.",
                },
                "proof_requirements": ["Show felt-symptom improvement."],
            }
        ),
    )
    _write(
        ember_root / "headlines" / "HEADLINE-POOL-EMBER-BRAIN-FUEL-DEFICIT.md",
        """4. "She Spent 18 Years Studying Why Brains Fail. Then Hers Went Silent Mid-Sentence at a Conference."
""",
    )
    _write(
        ember_root / "pages" / "EMBER-PRESALE-ADVERTORIAL.md",
        """# Presale Advertorial

**Headline:** "A Little-Known Fuel Deficit That Makes Women Over 45 Feel Like They're Losing Their Mind — While Their Doctors Say Nothing Is Wrong"

## Disclaimer
This product is not intended to diagnose, treat, cure, or prevent any disease.
""",
    )
    _write(
        ember_root / "pages" / "EMBER-SALES-PAGE.md",
        """# Sales Page

**Headline:** "Experience Ember — Sharper Recall, Steady Focus, and the Confidence to Trust Your Own Brain Again"
""",
    )
    return ember_root


def test_build_ember_manual_creative_context_request_maps_minimal_bundle(tmp_path: Path) -> None:
    ember_root = _write_minimal_ember_bundle(tmp_path)

    request = build_ember_manual_creative_context_request(ember_root)
    payload = request.model_dump(mode="json", by_alias=True)

    assert payload["provider"] == "manual"
    assert payload["angles"]["selectedAngleId"] == "not-dementia-depletion-perimenopause-brain-fog-as-creatine-fuel-deficit"
    assert payload["offer"]["selectedVariantId"] == "60-day-supply"
    assert payload["copyDocument"]["headline"].startswith("A Little-Known Fuel Deficit")
    assert payload["copyContext"]["audienceProductMarkdown"].startswith("## Audience")
    assert "## Product" in payload["copyContext"]["audienceProductMarkdown"]
    assert "## Selected Angle" in payload["copyContext"]["audienceProductMarkdown"]
    assert "## Offer Core" in payload["copyContext"]["audienceProductMarkdown"]
    assert "## Value Stack" in payload["copyContext"]["audienceProductMarkdown"]
    assert payload["copyContext"]["brandVoiceMarkdown"].startswith("# Brand Voice")
    assert payload["copyContext"]["complianceMarkdown"].startswith("# Compliance")
    assert payload["copyContext"]["mentalModelsMarkdown"].startswith("# Mental Models")
    assert "## Unaware" in payload["copyContext"]["awarenessAngleMatrixMarkdown"]
    assert "## Most-Aware" in payload["copyContext"]["awarenessAngleMatrixMarkdown"]
    assert payload["experimentSpecs"][0]["variants"][0]["channels"] == ["facebook"]
