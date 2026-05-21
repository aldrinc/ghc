from __future__ import annotations

import copy
from typing import Any

HTML_DEPLOY_INLINE_ASSET_PAYLOAD_KEYS = (
    "htmlDeployAssetPayloads",
    "html_deploy_asset_payloads",
)
HTML_DEPLOY_STATIC_ASSET_PAYLOAD_KEYS = (
    "htmlDeployStaticAssetPayloads",
    "html_deploy_static_asset_payloads",
)
HTML_DEPLOY_PAYLOAD_KEYS = (
    *HTML_DEPLOY_INLINE_ASSET_PAYLOAD_KEYS,
    *HTML_DEPLOY_STATIC_ASSET_PAYLOAD_KEYS,
)


def strip_inline_html_deploy_asset_payloads(value: Any) -> Any:
    if isinstance(value, list):
        return [strip_inline_html_deploy_asset_payloads(item) for item in value]
    if isinstance(value, dict):
        return {
            key: strip_inline_html_deploy_asset_payloads(item)
            for key, item in value.items()
            if key not in HTML_DEPLOY_PAYLOAD_KEYS
        }
    return value


def preserve_inline_html_deploy_asset_payloads(
    *,
    incoming_puck_data: dict[str, Any],
    source_puck_data: dict[str, Any] | None,
) -> dict[str, Any]:
    if not isinstance(source_puck_data, dict):
        return incoming_puck_data

    merged = copy.deepcopy(incoming_puck_data)
    _preserve_payloads(incoming=merged, source=source_puck_data)
    return merged


def _preserve_payloads(*, incoming: Any, source: Any) -> None:
    if isinstance(incoming, dict) and isinstance(source, dict):
        _preserve_imported_html_document_payloads(incoming=incoming, source=source)

        for key, incoming_value in incoming.items():
            if key in HTML_DEPLOY_PAYLOAD_KEYS:
                continue
            source_value = source.get(key)
            _preserve_payloads(incoming=incoming_value, source=source_value)
        return

    if not isinstance(incoming, list) or not isinstance(source, list):
        return

    source_by_id = {
        str(item.get("id")): item
        for item in source
        if isinstance(item, dict) and str(item.get("id") or "").strip()
    }
    for index, incoming_item in enumerate(incoming):
        source_item = None
        if isinstance(incoming_item, dict):
            incoming_id = str(incoming_item.get("id") or "").strip()
            if incoming_id:
                source_item = source_by_id.get(incoming_id)
        if source_item is None and not source_by_id and index < len(source):
            source_item = source[index]
        _preserve_payloads(incoming=incoming_item, source=source_item)


def _preserve_imported_html_document_payloads(
    *, incoming: dict[str, Any], source: dict[str, Any]
) -> None:
    if str(incoming.get("type") or "").strip() != "ImportedHtmlDocument":
        return
    if str(source.get("type") or "").strip() != "ImportedHtmlDocument":
        return

    incoming_props = incoming.get("props")
    source_props = source.get("props")
    if not isinstance(incoming_props, dict) or not isinstance(source_props, dict):
        return

    for key in HTML_DEPLOY_PAYLOAD_KEYS:
        if key in incoming_props or key not in source_props:
            continue
        incoming_props[key] = copy.deepcopy(source_props[key])
