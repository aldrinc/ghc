from app.services.funnel_templates import (
    list_funnel_templates,
    resolve_funnel_template_artifact_slug,
    resolve_funnel_template_category,
    resolve_funnel_template_public_stage,
)


def test_template_registry_exposes_global_presales_variants() -> None:
    templates = {template.template_id: template for template in list_funnel_templates()}

    assert "pre-sales-listicle" in templates
    assert "sales-pdp" in templates
    assert "presales-omni-template" in templates
    assert "presales-happyv-template" in templates

    assert templates["presales-omni-template"].name == "omni-template"
    assert templates["presales-happyv-template"].name == "happyv-template"
    assert templates["presales-omni-template"].category == "presales"
    assert templates["presales-happyv-template"].category == "presales"


def test_template_category_helpers_support_global_presales_variants() -> None:
    assert resolve_funnel_template_category("pre-sales-listicle") == "presales"
    assert resolve_funnel_template_category("sales-pdp") == "sales"
    assert resolve_funnel_template_category("presales-omni-template") == "presales"
    assert resolve_funnel_template_category("presales-happyv-template") == "presales"

    assert resolve_funnel_template_public_stage("presales-omni-template") == "pre_sales"
    assert resolve_funnel_template_public_stage("sales-pdp") == "sales"

    assert resolve_funnel_template_artifact_slug("presales-happyv-template") == "presales"
    assert resolve_funnel_template_artifact_slug("sales-pdp") == "sales"
