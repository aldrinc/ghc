import json

from app.services.funnel_templates import _resolve_asset_bytes, list_funnel_templates


def _walk_json(node):
    if isinstance(node, dict):
        yield node
        for value in node.values():
            yield from _walk_json(value)
    elif isinstance(node, list):
        for item in node:
            yield from _walk_json(item)


def test_funnel_templates_include_testimonial_markers():
    templates = {t.template_id: t for t in list_funnel_templates()}
    assert "sales-pdp" in templates
    assert "pre-sales-listicle" in templates

    for template_id in ("sales-pdp", "pre-sales-listicle"):
        tmpl = templates[template_id]
        count = 0
        for obj in _walk_json(tmpl.puck_data):
            if isinstance(obj, dict) and ("testimonialTemplate" in obj or "testimonial_template" in obj):
                count += 1
        assert count > 0, f"Template {template_id} is missing testimonial markers (testimonialTemplate)."


def test_funnel_templates_can_resolve_local_assets():
    templates = list_funnel_templates()
    assert templates, "No funnel templates were loaded."

    for tmpl in templates:
        asset_prefix = tmpl.asset_prefix
        asset_base_path = tmpl.asset_base_path
        if not asset_prefix or not asset_base_path:
            # Templates may intentionally omit local assets; nothing to validate.
            continue

        srcs: set[str] = set()
        for obj in _walk_json(tmpl.puck_data):
            if not isinstance(obj, dict):
                continue
            for key in ("src", "thumbSrc", "swatchImageSrc", "iconSrc"):
                value = obj.get(key)
                if isinstance(value, str) and value.startswith(asset_prefix):
                    srcs.add(value)

        assert srcs, f"Template {tmpl.template_id} has asset_base_path but no local asset src values."

        for src in sorted(srcs):
            content, _content_type, _origin = _resolve_asset_bytes(
                src=src,
                asset_base_path=asset_base_path,
                asset_prefix=asset_prefix,
            )
            assert (
                content is not None
            ), f"Template {tmpl.template_id} could not resolve local asset src={json.dumps(src)}"

