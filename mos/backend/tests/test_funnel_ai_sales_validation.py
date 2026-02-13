from __future__ import annotations

from copy import deepcopy

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


def _find_sales_hero_props(puck_data: dict) -> dict:
    for obj in _walk_json(puck_data):
        if isinstance(obj, dict) and obj.get("type") == "SalesPdpHero":
            props = obj.get("props")
            if isinstance(props, dict):
                return props
    raise AssertionError("SalesPdpHero props not found in template puck data")


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
