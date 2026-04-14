from __future__ import annotations

from dataclasses import dataclass

from app.db.models import Product, ProductVariant
from app.services.storefront_templates import StorefrontTemplateDescriptor


@dataclass(frozen=True)
class StorefrontBindingPreviewRequirement:
    key: str
    label: str
    source: str
    required: bool
    status: str
    detail: str


@dataclass(frozen=True)
class StorefrontBindingPreview:
    template_id: str
    client_id: str
    product_id: str | None
    product_title: str | None
    variant_id: str | None
    variant_title: str | None
    variant_provider: str | None
    ready: bool
    requirements: tuple[StorefrontBindingPreviewRequirement, ...]
    notes: tuple[str, ...]


def _normalize_provider(provider: str | None) -> str | None:
    cleaned = str(provider or "").strip().lower()
    return cleaned or None


def build_storefront_binding_preview(
    *,
    template: StorefrontTemplateDescriptor,
    client_id: str,
    product: Product | None,
    variant: ProductVariant | None,
) -> StorefrontBindingPreview:
    requirements: list[StorefrontBindingPreviewRequirement] = []
    variant_provider = _normalize_provider(variant.provider if variant is not None else None)
    medusa_variant_id = str(variant.external_price_id or "").strip() if variant is not None else ""

    for requirement in template.required_bindings:
        status = "missing"
        detail = "Binding is not configured yet."

        if requirement.key == "product":
            if product is None:
                detail = "Select a workspace product to resolve product-level storefront bindings."
            elif variant is None:
                detail = "Select a Medusa-linked variant before product bindings can be confirmed."
            elif variant_provider != "medusa":
                status = "unsupported"
                provider_label = variant_provider or "unknown"
                detail = (
                    f"The selected variant uses '{provider_label}'. Product bindings stay unresolved until a "
                    "Medusa-linked variant is selected."
                )
            elif not medusa_variant_id:
                detail = "The selected Medusa variant is missing its external Medusa id."
            else:
                status = "ready"
                detail = f"Product '{product.title}' is selected for this workspace preview."
        elif requirement.key == "selected_variant":
            if variant is None:
                detail = "Select a product variant to resolve selected-variant storefront bindings."
            elif variant_provider != "medusa":
                status = "unsupported"
                provider_label = variant_provider or "unknown"
                detail = (
                    f"Variant '{variant.title}' uses '{provider_label}'. Selected-variant storefront bindings "
                    "currently require a Medusa-managed variant."
                )
            elif not medusa_variant_id:
                detail = "The selected Medusa variant is missing its external Medusa id."
            else:
                status = "ready"
                detail = (
                    f"Variant '{variant.title}' is selected for runtime pricing and checkout state."
                )
        elif requirement.key == "pricing":
            if variant is None:
                detail = "Select a variant before pricing bindings can be evaluated."
            elif variant_provider != "medusa":
                status = "unsupported"
                provider_label = variant_provider or "unknown"
                detail = (
                    f"Pricing bindings currently require a Medusa-managed variant. The selected provider is "
                    f"'{provider_label}'."
                )
            elif not medusa_variant_id:
                detail = "The selected Medusa variant is missing its external Medusa id."
            elif variant.price is None or not variant.currency:
                detail = "Variant pricing is incomplete. Price and currency are both required."
            else:
                status = "ready"
                detail = "Variant price and currency are available for storefront rendering."
        elif requirement.key == "inventory":
            if variant is None:
                detail = "Select a variant before inventory bindings can be evaluated."
            elif variant_provider != "medusa":
                status = "unsupported"
                provider_label = variant_provider or "unknown"
                detail = (
                    f"Inventory bindings currently require a Medusa-managed variant. The selected provider is "
                    f"'{provider_label}'."
                )
            elif not medusa_variant_id:
                detail = "The selected Medusa variant is missing its external Medusa id."
            elif (
                variant.inventory_quantity is None
                and not str(variant.inventory_policy or "").strip()
                and not str(variant.inventory_management or "").strip()
            ):
                detail = "Variant inventory fields are empty. Populate quantity or inventory policy data."
            else:
                status = "ready"
                if str(variant.inventory_management or "").strip().lower() == "mos_local_only":
                    detail = (
                        "Variant inventory fields are present for availability messaging in mOS, "
                        "but Medusa stock-location quantity sync is not configured yet."
                    )
                else:
                    detail = "Variant inventory fields are present for availability messaging."
        elif requirement.key == "checkout_action":
            if variant is None:
                detail = "Select a variant before checkout bindings can be evaluated."
            elif variant_provider != "medusa":
                status = "unsupported"
                provider_label = variant_provider or "unknown"
                detail = (
                    f"Variant provider is '{provider_label}'. Storefront checkout actions currently "
                    "require a Medusa-managed variant."
                )
            elif not medusa_variant_id:
                detail = "Medusa checkout requires an external Medusa variant id."
            else:
                status = "ready"
                detail = "The selected variant can drive a Medusa-managed checkout action."

        requirements.append(
            StorefrontBindingPreviewRequirement(
                key=requirement.key,
                label=requirement.label,
                source=requirement.source,
                required=requirement.required,
                status=status,
                detail=detail,
            )
        )

    ready = all(
        requirement.status == "ready" for requirement in requirements if requirement.required
    )
    notes = [
        "MOS remains the source of truth for composition, styling, and non-commerce content slots.",
    ]
    if template.page_type == "pre_sell":
        notes.append(
            "Pre-sell templates still expect MOS-authored narrative and proof modules above the commerce CTA."
        )

    return StorefrontBindingPreview(
        template_id=template.template_id,
        client_id=client_id,
        product_id=str(product.id) if product is not None else None,
        product_title=product.title if product is not None else None,
        variant_id=str(variant.id) if variant is not None else None,
        variant_title=variant.title if variant is not None else None,
        variant_provider=variant_provider,
        ready=ready,
        requirements=tuple(requirements),
        notes=tuple(notes),
    )
