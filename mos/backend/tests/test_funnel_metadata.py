from __future__ import annotations

from app.services.funnel_metadata import build_public_page_metadata, normalize_public_page_metadata


def test_normalize_public_page_metadata_replaces_template_defaults_for_sales_pdp() -> None:
    puck_data = {
        "root": {
            "props": {
                "title": "PuppyPad PDP Template",
                "description": "A React + Vite template that recreates the PuppyPad PDP layout.",
            }
        },
        "content": [
            {
                "type": "SalesPdpPage",
                "props": {
                    "content": [
                        {
                            "type": "SalesPdpHero",
                            "props": {
                                "config": {
                                    "purchase": {
                                        "title": "The Honest Herbalist Handbook",
                                        "benefits": [
                                            {
                                                "text": "Four-step Interaction Triage Workflow (list -> flags -> verify -> questions)"
                                            },
                                            {"text": "Red-flag herb and food contraindication reference"},
                                        ],
                                    }
                                }
                            },
                        }
                    ]
                },
            }
        ],
    }

    metadata = normalize_public_page_metadata(
        puck_data=puck_data,
        page_name="Sales",
        page_slug="sales",
        brand_name="The Honest Herbalist",
        product_title=None,
    )

    assert metadata["title"] == "The Honest Herbalist Handbook"
    assert metadata["description"].startswith("The Honest Herbalist Handbook.")
    assert "Four-step Interaction Triage Workflow" in metadata["description"]
    assert puck_data["root"]["props"]["title"] == "The Honest Herbalist Handbook"
    assert puck_data["root"]["props"]["description"] == metadata["description"]


def test_normalize_public_page_metadata_preserves_explicit_custom_values() -> None:
    puck_data = {
        "root": {
            "props": {
                "title": "Rapid Pass | The Honest Herbalist",
                "description": "Interaction triage checklist for rapid herb and drug safety review.",
            }
        },
        "content": [],
    }

    metadata = normalize_public_page_metadata(
        puck_data=puck_data,
        page_name="Sales",
        page_slug="sales",
        brand_name="The Honest Herbalist",
        product_title="Rapid Pass",
    )

    assert metadata["title"] == "Rapid Pass | The Honest Herbalist"
    assert metadata["description"] == "Interaction triage checklist for rapid herb and drug safety review."


def test_build_public_page_metadata_falls_back_to_brand_and_page_label() -> None:
    metadata = build_public_page_metadata(
        puck_data={"root": {"props": {"title": "", "description": ""}}, "content": []},
        page_name="Quiz",
        page_slug="quiz",
        brand_name="The Honest Herbalist",
        product_title=None,
    )

    assert metadata["title"] == "The Honest Herbalist | Quiz"
    assert metadata["description"] == "Quiz for The Honest Herbalist."
    assert metadata["lang"] == "en"
