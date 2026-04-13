from __future__ import annotations


_TEMPLATE_CATEGORY_ALIASES = {
    "presales": "presales",
    "pre-sales": "presales",
    "pre_sales": "presales",
    "sales": "sales",
}


def normalize_template_category(value: str | None) -> str | None:
    cleaned = str(value or "").strip().lower()
    if not cleaned:
        return None
    return _TEMPLATE_CATEGORY_ALIASES.get(cleaned)


def infer_template_category_from_id(template_id: str | None) -> str | None:
    cleaned = str(template_id or "").strip().lower()
    if not cleaned:
        return None
    if cleaned in {"pre-sales-listicle", "pre_sales_listicle"}:
        return "presales"
    if cleaned in {"sales-pdp", "sales_pdp"}:
        return "sales"
    if cleaned.startswith(("presales-", "pre-sales-", "pre_sales_")):
        return "presales"
    if cleaned.startswith(("sales-", "sales_")):
        return "sales"
    return None


def resolve_funnel_template_category(template_id: str | None) -> str | None:
    category = normalize_template_category(template_id)
    if category:
        return category
    return infer_template_category_from_id(template_id)


def resolve_funnel_template_public_stage(template_id: str | None) -> str | None:
    category = resolve_funnel_template_category(template_id)
    if category == "presales":
        return "pre_sales"
    if category == "sales":
        return "sales"
    return None


def resolve_funnel_template_artifact_slug(template_id: str | None) -> str | None:
    category = resolve_funnel_template_category(template_id)
    if category == "presales":
        return "presales"
    if category == "sales":
        return "sales"
    return None
