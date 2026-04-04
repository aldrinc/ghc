from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from app.services.funnel_templates import get_funnel_template


@dataclass(frozen=True)
class StorefrontTemplateBindingRequirement:
    key: str
    label: str
    source: str
    description: str
    required: bool = True


@dataclass(frozen=True)
class StorefrontTemplateStylePolicy:
    locked_token_groups: tuple[str, ...]
    editable_token_groups: tuple[str, ...]


@dataclass(frozen=True)
class StorefrontTemplateImportProvenance:
    source_type: str
    source_template_id: str
    notes: tuple[str, ...]


@dataclass(frozen=True)
class StorefrontTemplateDescriptor:
    template_id: str
    name: str
    description: str | None
    preview_image: str | None
    family: str
    variant: str
    version: str
    page_type: str
    required_bindings: tuple[StorefrontTemplateBindingRequirement, ...]
    config_slots: tuple[str, ...]
    style_policy: StorefrontTemplateStylePolicy
    import_provenance: StorefrontTemplateImportProvenance
    puck_data: dict[str, Any]


@dataclass(frozen=True)
class _StorefrontTemplateBlueprint:
    family: str
    variant: str
    version: str
    page_type: str
    required_bindings: tuple[StorefrontTemplateBindingRequirement, ...]
    config_slots: tuple[str, ...]
    style_policy: StorefrontTemplateStylePolicy
    import_provenance: StorefrontTemplateImportProvenance


_PRODUCT_BINDING = StorefrontTemplateBindingRequirement(
    key="product",
    label="Product",
    source="medusa",
    description="Resolve the Medusa product record used to populate the page.",
)

_SELECTED_VARIANT_BINDING = StorefrontTemplateBindingRequirement(
    key="selected_variant",
    label="Selected variant",
    source="medusa",
    description="Resolve the currently selected sellable variant for price and checkout state.",
)

_PRICING_BINDING = StorefrontTemplateBindingRequirement(
    key="pricing",
    label="Pricing",
    source="medusa",
    description="Expose price, compare-at price, and currency for the selected variant.",
)

_INVENTORY_BINDING = StorefrontTemplateBindingRequirement(
    key="inventory",
    label="Inventory",
    source="medusa",
    description="Expose inventory or inventory policy for urgency and availability messaging.",
)

_CHECKOUT_ACTION_BINDING = StorefrontTemplateBindingRequirement(
    key="checkout_action",
    label="Checkout action",
    source="medusa",
    description="Provide a Medusa-backed checkout action for the selected variant.",
)


_TEMPLATE_BLUEPRINTS: dict[str, _StorefrontTemplateBlueprint] = {
    "sales-pdp": _StorefrontTemplateBlueprint(
        family="sales-pdp",
        variant="bold-proof",
        version="1.0.0",
        page_type="product_detail",
        required_bindings=(
            _PRODUCT_BINDING,
            _SELECTED_VARIANT_BINDING,
            _PRICING_BINDING,
            _INVENTORY_BINDING,
            _CHECKOUT_ACTION_BINDING,
        ),
        config_slots=(
            "hero_media",
            "offer_stack",
            "proof_modules",
            "comparison_module",
            "faq",
            "sticky_cta",
        ),
        style_policy=StorefrontTemplateStylePolicy(
            locked_token_groups=(
                "layout.geometry",
                "layout.section_spacing",
                "components.offer_stack",
            ),
            editable_token_groups=(
                "brand",
                "colors",
                "typography",
                "surfaces",
                "buttons",
            ),
        ),
        import_provenance=StorefrontTemplateImportProvenance(
            source_type="mos_funnel_template",
            source_template_id="sales-pdp",
            notes=(
                "Generalized from the existing PuppyPad sales funnel template.",
                "Acts as the first product-detail storefront template family variant.",
            ),
        ),
    ),
    "pre-sales-listicle": _StorefrontTemplateBlueprint(
        family="listicle-presell",
        variant="editorial-proof",
        version="1.0.0",
        page_type="pre_sell",
        required_bindings=(
            _PRODUCT_BINDING,
            _SELECTED_VARIANT_BINDING,
            _CHECKOUT_ACTION_BINDING,
        ),
        config_slots=(
            "hero_story",
            "reason_stack",
            "proof_modules",
            "bridge_cta",
            "footer_disclaimers",
        ),
        style_policy=StorefrontTemplateStylePolicy(
            locked_token_groups=(
                "layout.article_flow",
                "layout.proof_density",
                "components.bridge_cta",
            ),
            editable_token_groups=(
                "brand",
                "colors",
                "typography",
                "surfaces",
                "buttons",
            ),
        ),
        import_provenance=StorefrontTemplateImportProvenance(
            source_type="mos_funnel_template",
            source_template_id="pre-sales-listicle",
            notes=(
                "Generalized from the existing PuppyPad pre-sales funnel template.",
                "Acts as the first pre-sell storefront template family variant.",
            ),
        ),
    ),
}


def _build_descriptor(template_id: str) -> StorefrontTemplateDescriptor | None:
    blueprint = _TEMPLATE_BLUEPRINTS.get(template_id)
    if blueprint is None:
        return None

    template = get_funnel_template(template_id)
    if template is None:
        return None

    return StorefrontTemplateDescriptor(
        template_id=template.template_id,
        name=template.name,
        description=template.description,
        preview_image=template.preview_image,
        family=blueprint.family,
        variant=blueprint.variant,
        version=blueprint.version,
        page_type=blueprint.page_type,
        required_bindings=blueprint.required_bindings,
        config_slots=blueprint.config_slots,
        style_policy=blueprint.style_policy,
        import_provenance=blueprint.import_provenance,
        puck_data=template.puck_data,
    )


def list_storefront_templates() -> list[StorefrontTemplateDescriptor]:
    descriptors = [_build_descriptor(template_id) for template_id in sorted(_TEMPLATE_BLUEPRINTS)]
    return [descriptor for descriptor in descriptors if descriptor is not None]


def get_storefront_template(template_id: str) -> StorefrontTemplateDescriptor | None:
    return _build_descriptor(template_id)
