from __future__ import annotations

from copy import deepcopy
from datetime import datetime, timezone

import pytest

from app.services import funnel_ai
from app.services.funnel_templates import get_funnel_template


def _walk_json(node):
    if isinstance(node, dict):
        yield node
        for value in node.values():
            yield from _walk_json(value)
    elif isinstance(node, list):
        for item in node:
            yield from _walk_json(item)


def _sales_template_puck_data() -> dict:
    template = get_funnel_template("sales-pdp")
    assert template is not None
    return deepcopy(template.puck_data)


def _pre_sales_template_puck_data() -> dict:
    template = get_funnel_template("pre-sales-listicle")
    assert template is not None
    return deepcopy(template.puck_data)


def _find_sales_hero_props(puck_data: dict) -> dict:
    for obj in _walk_json(puck_data):
        if isinstance(obj, dict) and obj.get("type") == "SalesPdpHero":
            props = obj.get("props")
            if isinstance(props, dict):
                return props
    raise AssertionError("SalesPdpHero props not found in template puck data")


def _find_sales_hero_urgency(puck_data: dict) -> dict:
    hero_props = _find_sales_hero_props(puck_data)
    config = hero_props.get("config")
    assert isinstance(config, dict)
    purchase = config.get("purchase")
    assert isinstance(purchase, dict)
    cta = purchase.get("cta")
    assert isinstance(cta, dict)
    urgency = cta.get("urgency")
    assert isinstance(urgency, dict)
    return urgency


def _find_pre_sales_floating_cta_config(puck_data: dict) -> dict:
    for obj in _walk_json(puck_data):
        if isinstance(obj, dict) and obj.get("type") == "PreSalesFloatingCta":
            props = obj.get("props")
            if not isinstance(props, dict):
                continue
            config = props.get("config")
            if isinstance(config, dict):
                return config
    raise AssertionError("PreSalesFloatingCta config not found in template puck data")


def _find_pre_sales_reasons_config(puck_data: dict) -> list[dict]:
    for obj in _walk_json(puck_data):
        if isinstance(obj, dict) and obj.get("type") == "PreSalesReasons":
            props = obj.get("props")
            if not isinstance(props, dict):
                continue
            config = props.get("config")
            if isinstance(config, list):
                return config
    raise AssertionError("PreSalesReasons config not found in template puck data")


def test_sales_template_validation_accepts_default_sales_hero_modal_shape():
    puck_data = _sales_template_puck_data()
    funnel_ai._validate_sales_pdp_component_configs(puck_data)


def test_sales_template_requires_faq_component_type():
    puck_data = _sales_template_puck_data()
    required = funnel_ai._required_template_component_types(puck_data, template_kind="sales-pdp")
    assert "SalesPdpFaq" in required


def test_sales_template_validation_rejects_missing_free_gifts_modal_block():
    puck_data = _sales_template_puck_data()
    hero_props = _find_sales_hero_props(puck_data)
    modals = hero_props.get("modals")
    assert isinstance(modals, dict)
    modals.pop("freeGifts", None)

    with pytest.raises(ValueError, match=r"SalesPdpHero\.modals\.freeGifts must be an object"):
        funnel_ai._validate_sales_pdp_component_configs(puck_data)


def test_sales_pdp_urgency_rows_restore_monthly_sold_out_format():
    reference_puck_data = _sales_template_puck_data()
    generated_puck_data = _sales_template_puck_data()
    generated_urgency = _find_sales_hero_urgency(generated_puck_data)
    generated_urgency["message"] = "Limited inventory available. Secure your mask today."
    generated_urgency["rows"] = [
        {"label": "IN STOCK", "value": "Available Now", "tone": "highlight"},
        {"label": "SHIPPING", "value": "Fast & Free", "tone": "muted"},
    ]

    funnel_ai._enforce_sales_pdp_urgency_month_rows(
        puck_data=generated_puck_data,
        reference_puck_data=reference_puck_data,
        now=datetime(2026, 2, 16, tzinfo=timezone.utc),
    )

    repaired_urgency = _find_sales_hero_urgency(generated_puck_data)
    assert repaired_urgency.get("message") == "We are selling out more than expected. Order now before we run out again."
    repaired_rows = repaired_urgency.get("rows")
    assert isinstance(repaired_rows, list) and len(repaired_rows) == 2
    assert repaired_rows[0]["label"] == "JANUARY"
    assert repaired_rows[0]["tone"] == "muted"
    assert "Sold Out" in repaired_rows[0]["value"]
    assert repaired_rows[1]["label"] == "FEBRUARY"
    assert repaired_rows[1]["tone"] == "highlight"
    assert "99% Sold" in repaired_rows[1]["value"]


def test_sales_pdp_urgency_rows_use_previous_month_in_january():
    reference_puck_data = _sales_template_puck_data()
    generated_puck_data = _sales_template_puck_data()

    funnel_ai._enforce_sales_pdp_urgency_month_rows(
        puck_data=generated_puck_data,
        reference_puck_data=reference_puck_data,
        now=datetime(2026, 1, 5, tzinfo=timezone.utc),
    )

    rows = _find_sales_hero_urgency(generated_puck_data)["rows"]
    assert rows[0]["label"] == "DECEMBER"
    assert rows[1]["label"] == "JANUARY"


def test_sales_pdp_urgency_rows_require_sold_metrics():
    reference_puck_data = _sales_template_puck_data()
    generated_puck_data = _sales_template_puck_data()
    for data in (reference_puck_data, generated_puck_data):
        urgency = _find_sales_hero_urgency(data)
        urgency["message"] = "We are selling out more than expected. Order now before we run out again."
        urgency["rows"] = [
            {"label": "IN STOCK", "value": "Available Now"},
            {"label": "SHIPPING", "value": "Fast & Free"},
        ]

    with pytest.raises(
        ValueError,
        match=r"urgency\.rows must include one 'Sold Out' value and one '99% Sold' style value with percentages",
    ):
        funnel_ai._enforce_sales_pdp_urgency_month_rows(
            puck_data=generated_puck_data,
            reference_puck_data=reference_puck_data,
            now=datetime(2026, 2, 16, tzinfo=timezone.utc),
        )


def test_pre_sales_floating_cta_trigger_repairs_invalid_show_after_id():
    reference_puck_data = _pre_sales_template_puck_data()
    generated_puck_data = _pre_sales_template_puck_data()
    cta = _find_pre_sales_floating_cta_config(generated_puck_data)
    cta["showAfterId"] = "pre-sales-reasons"

    funnel_ai._enforce_pre_sales_floating_cta_config(
        puck_data=generated_puck_data,
        reference_puck_data=reference_puck_data,
    )

    repaired = _find_pre_sales_floating_cta_config(generated_puck_data)
    assert repaired.get("showAfterId") == "listicle-end"


def test_pre_sales_floating_cta_trigger_falls_back_to_listicle_end_when_reasons_invalid():
    reference_puck_data = _pre_sales_template_puck_data()
    generated_puck_data = _pre_sales_template_puck_data()
    reasons = _find_pre_sales_reasons_config(generated_puck_data)
    for reason in reasons:
        if isinstance(reason, dict):
            reason["number"] = "invalid"
    cta = _find_pre_sales_floating_cta_config(generated_puck_data)
    cta["showAfterId"] = "reason-3"

    funnel_ai._enforce_pre_sales_floating_cta_config(
        puck_data=generated_puck_data,
        reference_puck_data=reference_puck_data,
    )

    repaired = _find_pre_sales_floating_cta_config(generated_puck_data)
    assert repaired.get("showAfterId") == "listicle-end"


def test_pre_sales_validation_rejects_invalid_floating_cta_trigger_id():
    puck_data = _pre_sales_template_puck_data()
    cta = _find_pre_sales_floating_cta_config(puck_data)
    cta["showAfterId"] = "pre-sales-reasons"

    with pytest.raises(ValueError, match=r"showAfterId/showAfterReason must reference one of"):
        funnel_ai._validate_pre_sales_listicle_component_configs(puck_data)


def test_align_sales_checkout_option_ids_to_variant_matrix():
    purchase = {
        "size": {
            "options": [
                {"id": "standard", "label": "Standard", "sizeIn": "12x9", "sizeCm": "30x23"},
                {"id": "extended", "label": "Extended", "sizeIn": "14x10", "sizeCm": "35x25"},
            ]
        },
        "color": {
            "options": [
                {"id": "midnight-black", "label": "Midnight Black"},
                {"id": "pearl-white", "label": "Pearl White"},
            ]
        },
        "offer": {
            "options": [
                {"id": "1", "title": "Single", "image": {"alt": "Single"}, "price": 299},
                {"id": "2", "title": "Duo", "image": {"alt": "Duo"}, "price": 499},
                {"id": "3", "title": "Family", "image": {"alt": "Family"}, "price": 699},
            ]
        },
    }
    variants = [
        {"title": "Single Device", "amount_cents": 29900, "option_values": {"sizeId": "onesize", "colorId": "white", "offerId": "single"}},
        {"title": "Share & Save Duo", "amount_cents": 49900, "option_values": {"sizeId": "onesize", "colorId": "white", "offerId": "double"}},
        {"title": "Family Bundle", "amount_cents": 69900, "option_values": {"sizeId": "onesize", "colorId": "white", "offerId": "triple"}},
    ]

    changed = funnel_ai._align_sales_pdp_purchase_options_to_variants(purchase=purchase, variants=variants)

    assert changed is True
    assert [item["id"] for item in purchase["size"]["options"]] == ["onesize"]
    assert [item["id"] for item in purchase["color"]["options"]] == ["white"]
    assert [item["id"] for item in purchase["offer"]["options"]] == ["single", "double", "triple"]
    assert [item["title"] for item in purchase["offer"]["options"]] == [
        "Single Device",
        "Share & Save Duo",
        "Family Bundle",
    ]


def test_align_sales_checkout_option_ids_noop_when_ids_already_match():
    purchase = {
        "size": {"options": [{"id": "onesize", "label": "One Size", "sizeIn": "", "sizeCm": ""}]},
        "color": {"options": [{"id": "white", "label": "White"}]},
        "offer": {
            "options": [
                {"id": "single", "title": "Single Device", "image": {"alt": "Single"}, "price": 299.0},
                {"id": "double", "title": "Share & Save Duo", "image": {"alt": "Duo"}, "price": 499.0},
            ]
        },
    }
    variants = [
        {"title": "Single Device", "amount_cents": 29900, "option_values": {"sizeId": "onesize", "colorId": "white", "offerId": "single"}},
        {"title": "Share & Save Duo", "amount_cents": 49900, "option_values": {"sizeId": "onesize", "colorId": "white", "offerId": "double"}},
    ]

    changed = funnel_ai._align_sales_pdp_purchase_options_to_variants(purchase=purchase, variants=variants)

    assert changed is False


def test_align_sales_checkout_option_ids_requires_variant_option_values():
    purchase = {
        "size": {"options": [{"id": "onesize", "label": "One Size", "sizeIn": "", "sizeCm": ""}]},
        "color": {"options": [{"id": "white", "label": "White"}]},
        "offer": {"options": [{"id": "single", "title": "Single Device", "image": {"alt": "Single"}, "price": 299.0}]},
    }

    with pytest.raises(ValueError, match="option_values"):
        funnel_ai._align_sales_pdp_purchase_options_to_variants(
            purchase=purchase,
            variants=[{"title": "Single Device", "amount_cents": 29900}],
        )


def test_align_sales_checkout_option_ids_supports_single_offer_dimension_variants():
    purchase = {
        "size": {"options": [{"id": "small", "label": "Small", "sizeIn": "12x9", "sizeCm": "30x23"}]},
        "color": {"options": [{"id": "gray", "label": "Gray"}]},
        "offer": {
            "options": [
                {"id": "legacy-single", "title": "Single", "image": {"alt": "Single"}, "price": 299.0},
            ]
        },
    }
    variants = [
        {"title": "Single Device", "amount_cents": 29900, "option_values": {"Bundle": "single"}},
        {"title": "Share & Save Duo", "amount_cents": 49900, "option_values": {"Bundle": "double"}},
        {"title": "Family Bundle", "amount_cents": 69900, "option_values": {"Bundle": "family"}},
    ]

    changed = funnel_ai._align_sales_pdp_purchase_options_to_variants(purchase=purchase, variants=variants)

    assert changed is True
    assert [item["id"] for item in purchase["size"]["options"]] == ["__default_size"]
    assert [item["id"] for item in purchase["color"]["options"]] == ["__default_color"]
    assert [item["id"] for item in purchase["offer"]["options"]] == ["single", "double", "family"]
    variant_schema = purchase.get("variantSchema")
    assert isinstance(variant_schema, dict)
    assert variant_schema == {
        "dimensions": [
            {
                "id": "offerId",
                "type": "offer",
                "label": "Offer",
                "sourceKey": "Bundle",
            }
        ],
        "defaults": {"sizeId": "__default_size", "colorId": "__default_color"},
    }


def test_align_sales_checkout_option_ids_uses_explicit_options_schema_mapping():
    purchase = {
        "size": {"options": [{"id": "small", "label": "Small", "sizeIn": "12x9", "sizeCm": "30x23"}]},
        "color": {"options": [{"id": "gray", "label": "Gray"}]},
        "offer": {
            "options": [
                {"id": "legacy", "title": "Legacy", "image": {"alt": "Legacy"}, "price": 299.0},
            ]
        },
    }
    variants = [
        {
            "title": "Single Device",
            "amount_cents": 29900,
            "option_values": {"Fit": "onesize", "Tone": "white", "Package": "single"},
        },
        {
            "title": "Share & Save Duo",
            "amount_cents": 49900,
            "option_values": {"Fit": "onesize", "Tone": "white", "Package": "double"},
        },
    ]
    options_schema = {
        "salesPdpVariantMapping": {
            "sizeId": "Fit",
            "colorId": "Tone",
            "offerId": "Package",
        }
    }

    changed = funnel_ai._align_sales_pdp_purchase_options_to_variants(
        purchase=purchase,
        variants=variants,
        options_schema=options_schema,
    )

    assert changed is True
    assert [item["id"] for item in purchase["size"]["options"]] == ["onesize"]
    assert [item["id"] for item in purchase["color"]["options"]] == ["white"]
    assert [item["id"] for item in purchase["offer"]["options"]] == ["single", "double"]
    variant_schema = purchase.get("variantSchema")
    assert isinstance(variant_schema, dict)
    assert variant_schema["dimensions"] == [
        {"id": "sizeId", "type": "size", "label": "Size", "sourceKey": "Fit"},
        {"id": "colorId", "type": "color", "label": "Color", "sourceKey": "Tone"},
        {"id": "offerId", "type": "offer", "label": "Offer", "sourceKey": "Package"},
    ]
    assert "defaults" not in variant_schema


def test_align_sales_checkout_option_ids_rejects_unmapped_variant_keys():
    purchase = {
        "size": {"options": [{"id": "onesize", "label": "One Size", "sizeIn": "", "sizeCm": ""}]},
        "color": {"options": [{"id": "white", "label": "White"}]},
        "offer": {"options": [{"id": "single", "title": "Single Device", "image": {"alt": "Single"}, "price": 299.0}]},
    }
    variants = [
        {
            "title": "Single Device",
            "amount_cents": 29900,
            "option_values": {"Bundle": "single", "Region": "us"},
        },
        {
            "title": "Share & Save Duo",
            "amount_cents": 49900,
            "option_values": {"Bundle": "double", "Region": "us"},
        },
    ]

    with pytest.raises(ValueError, match="unmapped keys"):
        funnel_ai._align_sales_pdp_purchase_options_to_variants(
            purchase=purchase,
            variants=variants,
        )
