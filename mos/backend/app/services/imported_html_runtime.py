from __future__ import annotations

from dataclasses import dataclass, field
from html.parser import HTMLParser
import re
from typing import Any, Literal
from urllib.parse import urlparse

from pydantic import BaseModel, ConfigDict, Field

from app.db.models import ProductVariant
from app.services.campaign_destinations import normalize_destination_type
from app.services.funnel_template_categories import resolve_funnel_template_public_stage
from app.services.paid_ads_qa import clean_optional_text


IMPORTED_HTML_INSTRUMENTATION_SCHEMA_VERSION = "imported-html-instrumentation-v1"
ImportedHtmlPageStage = Literal["pre_sales", "sales", "checkout", "thank_you", "custom"]
ImportedHtmlBindingEvent = Literal["click"]
ImportedHtmlTrackEventType = Literal["pre_sales_to_sales_click", "sales_to_checkout_click", "custom_page_click"]

_IDENTIFIER_RE = re.compile(r"[A-Za-z_][A-Za-z0-9_-]*")
_TAG_RE = re.compile(r"[A-Za-z][A-Za-z0-9_-]*")
_ATTR_NAME_RE = re.compile(r"[A-Za-z_:][A-Za-z0-9_:\.-]*")
_HTTPS_SCHEMES = {"https"}


def resolve_funnel_page_stage(
    *,
    slug: str | None = None,
    template_id: str | None = None,
    page_name: str | None = None,
) -> ImportedHtmlPageStage:
    template_stage = resolve_funnel_template_public_stage(template_id)
    if template_stage:
        return template_stage

    normalized = normalize_destination_type(slug)
    if normalized == "pre-sales":
        return "pre_sales"
    if normalized == "sales":
        return "sales"
    if normalized == "checkout":
        return "checkout"
    if normalized == "thank-you":
        return "thank_you"

    normalized_name = clean_optional_text(page_name)
    if normalized_name:
        lowered_name = normalized_name.lower()
        if (
            "pre-sales" in lowered_name
            or "presales" in lowered_name
            or "advertorial" in lowered_name
        ):
            return "pre_sales"
        if "sales" in lowered_name or "pdp" in lowered_name or "product page" in lowered_name:
            return "sales"
        if "checkout" in lowered_name:
            return "checkout"
        if "thank" in lowered_name:
            return "thank_you"
    return "custom"


def imported_html_selector_hint() -> str:
    return (
        "Supported selector syntax: a single simple CSS selector only. "
        "Allowed pieces are tag, #id, .class, [attr], [attr='value'], [attr=\"value\"], and optional :checked. "
        "Do not use commas, descendant combinators, child combinators, sibling combinators, :nth-*, :has(), or text-based selectors. "
        "Binding selectors may intentionally match multiple identical CTA elements when they should all share the same behavior."
    )


@dataclass(slots=True)
class _HtmlNode:
    tag: str
    attrs: dict[str, str] = field(default_factory=dict)
    children: list["_HtmlNode"] = field(default_factory=list)
    text_parts: list[str] = field(default_factory=list)

    @property
    def class_names(self) -> set[str]:
        raw = self.attrs.get("class", "")
        if not raw:
            return set()
        return {part for part in raw.split() if part}

    @property
    def text_content(self) -> str:
        child_text = "".join(child.text_content for child in self.children)
        return "".join(self.text_parts) + child_text


class _HtmlTreeParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.root = _HtmlNode(tag="__root__")
        self._stack: list[_HtmlNode] = [self.root]

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        node = _HtmlNode(
            tag=tag.lower(),
            attrs={name.lower(): (value if value is not None else "") for name, value in attrs},
        )
        self._stack[-1].children.append(node)
        self._stack.append(node)

    def handle_startendtag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        node = _HtmlNode(
            tag=tag.lower(),
            attrs={name.lower(): (value if value is not None else "") for name, value in attrs},
        )
        self._stack[-1].children.append(node)

    def handle_endtag(self, tag: str) -> None:
        lowered = tag.lower()
        for idx in range(len(self._stack) - 1, 0, -1):
            if self._stack[idx].tag == lowered:
                del self._stack[idx:]
                return

    def handle_data(self, data: str) -> None:
        if data:
            self._stack[-1].text_parts.append(data)


@dataclass(frozen=True, slots=True)
class _RestrictedSelector:
    raw: str
    tag: str | None = None
    id_value: str | None = None
    class_names: tuple[str, ...] = ()
    attrs: tuple[tuple[str, str | None], ...] = ()
    checked: bool = False


class ImportedHtmlOptionSelector(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str = Field(min_length=1, max_length=120)
    selector: str = Field(min_length=1, max_length=300)
    source: Literal["value", "text"] = "value"


class ImportedHtmlFixedVariantResolver(BaseModel):
    model_config = ConfigDict(extra="forbid")

    type: Literal["fixed"]
    variantId: str = Field(min_length=1)


class ImportedHtmlOptionValuesVariantResolver(BaseModel):
    model_config = ConfigDict(extra="forbid")

    type: Literal["option_values"]
    optionSelectors: list[ImportedHtmlOptionSelector] = Field(default_factory=list, min_length=1)


ImportedHtmlVariantResolver = ImportedHtmlFixedVariantResolver | ImportedHtmlOptionValuesVariantResolver


class ImportedHtmlExternalUrlByVariant(BaseModel):
    model_config = ConfigDict(extra="forbid")

    variantId: str = Field(min_length=1)
    url: str = Field(min_length=1, max_length=4096)


class ImportedHtmlPublicCheckoutConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    mode: Literal["public_checkout"]
    variantResolver: ImportedHtmlVariantResolver


class ImportedHtmlExternalCheckoutConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    mode: Literal["external_checkout_url"]
    variantResolver: ImportedHtmlVariantResolver
    externalUrlsByVariant: list[ImportedHtmlExternalUrlByVariant] = Field(default_factory=list, min_length=1)


ImportedHtmlCheckoutConfig = ImportedHtmlPublicCheckoutConfig | ImportedHtmlExternalCheckoutConfig


class ImportedHtmlInternalNavigationBinding(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str = Field(min_length=1, max_length=120)
    type: Literal["internal_navigation"]
    selector: str = Field(min_length=1, max_length=300)
    event: ImportedHtmlBindingEvent = "click"
    targetPageId: str = Field(min_length=1)
    trackEventType: ImportedHtmlTrackEventType = "custom_page_click"


class ImportedHtmlCheckoutBinding(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str = Field(min_length=1, max_length=120)
    type: Literal["checkout"]
    selector: str = Field(min_length=1, max_length=300)
    event: ImportedHtmlBindingEvent = "click"
    trackEventType: ImportedHtmlTrackEventType = "sales_to_checkout_click"
    checkout: ImportedHtmlCheckoutConfig


class ImportedHtmlTrackOnlyBinding(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str = Field(min_length=1, max_length=120)
    type: Literal["track_only"]
    selector: str = Field(min_length=1, max_length=300)
    event: ImportedHtmlBindingEvent = "click"
    trackEventType: ImportedHtmlTrackEventType = "custom_page_click"


ImportedHtmlBinding = (
    ImportedHtmlInternalNavigationBinding
    | ImportedHtmlCheckoutBinding
    | ImportedHtmlTrackOnlyBinding
)


class ImportedHtmlInstrumentationManifest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schemaVersion: Literal[IMPORTED_HTML_INSTRUMENTATION_SCHEMA_VERSION]
    pageStage: ImportedHtmlPageStage
    bindings: list[ImportedHtmlBinding] = Field(default_factory=list)


class ImportedHtmlRuntimeValidationError(ValueError):
    pass


def imported_html_instrumentation_schema() -> dict[str, Any]:
    raw_schema = ImportedHtmlInstrumentationManifest.model_json_schema()
    defs = raw_schema.get("$defs") if isinstance(raw_schema.get("$defs"), dict) else {}

    def _inline(node: Any) -> Any:
        if isinstance(node, list):
            return [_inline(item) for item in node]
        if not isinstance(node, dict):
            return node

        ref = node.get("$ref")
        if isinstance(ref, str) and ref.startswith("#/$defs/"):
            ref_key = ref.split("/", 2)[-1]
            target = defs.get(ref_key)
            if not isinstance(target, dict):
                raise ImportedHtmlRuntimeValidationError(
                    f"instrumentationManifest schema references unknown definition '{ref_key}'."
                )
            merged = _inline(target)
            extras = {key: value for key, value in node.items() if key != "$ref"}
            if not extras:
                return merged
            if not isinstance(merged, dict):
                return merged
            return {
                **merged,
                **{key: _inline(value) for key, value in extras.items()},
            }

        return {
            key: _inline(value)
            for key, value in node.items()
            if key != "$defs"
        }

    return _inline(raw_schema)


def coerce_imported_html_instrumentation_manifest(raw: Any) -> dict[str, Any]:
    if raw is None:
        raise ImportedHtmlRuntimeValidationError("instrumentationManifest is required for imported HTML pages.")
    try:
        manifest = ImportedHtmlInstrumentationManifest.model_validate(raw)
    except Exception as exc:  # noqa: BLE001
        raise ImportedHtmlRuntimeValidationError(f"instrumentationManifest is invalid. {exc}") from exc
    return manifest.model_dump(mode="json")


def validate_imported_html_document_manifest(
    *,
    html_document: str,
    instrumentation_manifest: dict[str, Any] | None,
    current_page_stage: ImportedHtmlPageStage,
    current_page_id: str | None = None,
    next_page_id: str | None = None,
    available_target_page_ids: set[str] | None = None,
    checkout_ready_variants: list[ProductVariant] | None = None,
    require_stage_bindings: bool = False,
) -> dict[str, Any]:
    manifest = ImportedHtmlInstrumentationManifest.model_validate(
        coerce_imported_html_instrumentation_manifest(instrumentation_manifest)
    )
    if manifest.pageStage != current_page_stage:
        raise ImportedHtmlRuntimeValidationError(
            "instrumentationManifest.pageStage must match the imported page stage. "
            f"Expected '{current_page_stage}', received '{manifest.pageStage}'."
        )

    root = _parse_html_document(html_document)
    seen_ids: set[str] = set()
    available_target_page_ids = available_target_page_ids or set()
    checkout_ready_variants = checkout_ready_variants or []
    checkout_variant_ids = {str(variant.id) for variant in checkout_ready_variants}

    navigation_count = 0
    checkout_count = 0

    for binding in manifest.bindings:
        if binding.id in seen_ids:
            raise ImportedHtmlRuntimeValidationError(
                f"instrumentationManifest contains duplicate binding id '{binding.id}'."
            )
        seen_ids.add(binding.id)
        _validate_selector_match_count(
            html_root=root,
            selector=binding.selector,
            context_label=f"binding '{binding.id}'",
            min_matches=1,
        )

        if binding.type == "internal_navigation":
            navigation_count += 1
            if binding.targetPageId == current_page_id:
                raise ImportedHtmlRuntimeValidationError(
                    f"Binding '{binding.id}' cannot target the current page."
                )
            if available_target_page_ids and binding.targetPageId not in available_target_page_ids:
                raise ImportedHtmlRuntimeValidationError(
                    f"Binding '{binding.id}' targets unknown page '{binding.targetPageId}'."
                )
            if binding.trackEventType not in {"pre_sales_to_sales_click", "custom_page_click"}:
                raise ImportedHtmlRuntimeValidationError(
                    f"Binding '{binding.id}' has unsupported internal navigation trackEventType '{binding.trackEventType}'."
                )
            if current_page_stage == "pre_sales" and next_page_id and binding.targetPageId != next_page_id:
                raise ImportedHtmlRuntimeValidationError(
                    f"Pre-sales binding '{binding.id}' must target the configured next page '{next_page_id}'."
                )
        elif binding.type == "checkout":
            checkout_count += 1
            if binding.trackEventType not in {"sales_to_checkout_click", "custom_page_click"}:
                raise ImportedHtmlRuntimeValidationError(
                    f"Binding '{binding.id}' has unsupported checkout trackEventType '{binding.trackEventType}'."
                )
            _validate_checkout_binding(
                binding=binding,
                html_root=root,
                checkout_variant_ids=checkout_variant_ids,
                checkout_ready_variants=checkout_ready_variants,
            )

    if require_stage_bindings:
        if current_page_stage == "pre_sales" and navigation_count < 1:
            raise ImportedHtmlRuntimeValidationError(
                "Imported pre-sales HTML pages must include at least one internal_navigation binding."
            )
        if current_page_stage == "sales" and checkout_count < 1:
            raise ImportedHtmlRuntimeValidationError(
                "Imported sales HTML pages must include at least one checkout binding."
            )

    return manifest.model_dump(mode="json")


def build_imported_html_generation_context(
    *,
    current_page_stage: ImportedHtmlPageStage,
    current_page_id: str,
    next_page_id: str | None,
    page_targets: list[dict[str, Any]],
    checkout_ready_variants: list[ProductVariant],
) -> dict[str, Any]:
    serialized_variants: list[dict[str, Any]] = []
    for variant in checkout_ready_variants:
        option_values = variant.option_values if isinstance(variant.option_values, dict) else {}
        serialized_variants.append(
            {
                "id": str(variant.id),
                "title": str(variant.title or "").strip(),
                "provider": str(variant.provider or "").strip().lower() or None,
                "optionValues": option_values,
            }
        )
    return {
        "schemaVersion": IMPORTED_HTML_INSTRUMENTATION_SCHEMA_VERSION,
        "currentPageStage": current_page_stage,
        "currentPageId": current_page_id,
        "nextPageId": next_page_id,
        "pageTargets": page_targets,
        "checkoutReadyVariants": serialized_variants,
    }


def _parse_html_document(html_document: str) -> _HtmlNode:
    parser = _HtmlTreeParser()
    parser.feed(html_document)
    parser.close()
    return parser.root


def _validate_checkout_binding(
    *,
    binding: ImportedHtmlCheckoutBinding,
    html_root: _HtmlNode,
    checkout_variant_ids: set[str],
    checkout_ready_variants: list[ProductVariant],
) -> None:
    resolver = binding.checkout.variantResolver
    if resolver.type == "fixed":
        if resolver.variantId not in checkout_variant_ids:
            raise ImportedHtmlRuntimeValidationError(
                f"Checkout binding '{binding.id}' references unknown variant '{resolver.variantId}'."
            )
    elif resolver.type == "option_values":
        seen_option_names: set[str] = set()
        for option_selector in resolver.optionSelectors:
            lowered_name = option_selector.name.strip().lower()
            if lowered_name in seen_option_names:
                raise ImportedHtmlRuntimeValidationError(
                    f"Checkout binding '{binding.id}' contains duplicate option selector name '{option_selector.name}'."
                )
            seen_option_names.add(lowered_name)
            _validate_selector_match_count(
                html_root=html_root,
                selector=option_selector.selector,
                context_label=f"binding '{binding.id}' option '{option_selector.name}'",
                min_matches=1,
                max_matches=1,
            )
        if checkout_ready_variants:
            selector_names = {option.name.strip() for option in resolver.optionSelectors}
            matching_variants = [
                variant
                for variant in checkout_ready_variants
                if isinstance(variant.option_values, dict)
                and selector_names.issubset({str(key) for key in variant.option_values.keys()})
            ]
            if not matching_variants:
                raise ImportedHtmlRuntimeValidationError(
                    f"Checkout binding '{binding.id}' option selector names do not match any checkout-ready variant options."
                )
    else:  # pragma: no cover
        raise ImportedHtmlRuntimeValidationError(
            f"Checkout binding '{binding.id}' has unsupported variant resolver type."
        )

    if binding.checkout.mode == "external_checkout_url":
        url_map: dict[str, str] = {}
        for item in binding.checkout.externalUrlsByVariant:
            if item.variantId in url_map:
                raise ImportedHtmlRuntimeValidationError(
                    f"Checkout binding '{binding.id}' has duplicate external checkout URL entries for variant '{item.variantId}'."
                )
            if item.variantId not in checkout_variant_ids:
                raise ImportedHtmlRuntimeValidationError(
                    f"Checkout binding '{binding.id}' references unknown external checkout variant '{item.variantId}'."
                )
            _validate_https_url(item.url, binding_id=binding.id, variant_id=item.variantId)
            url_map[item.variantId] = item.url
        if binding.checkout.variantResolver.type == "fixed":
            if binding.checkout.variantResolver.variantId not in url_map:
                raise ImportedHtmlRuntimeValidationError(
                    f"Checkout binding '{binding.id}' is missing an external checkout URL for its fixed variant."
                )
        elif not url_map:
            raise ImportedHtmlRuntimeValidationError(
                f"Checkout binding '{binding.id}' must include at least one external checkout URL."
            )


def _validate_https_url(url: str, *, binding_id: str, variant_id: str) -> None:
    parsed = urlparse(url.strip())
    if parsed.scheme not in _HTTPS_SCHEMES or not parsed.netloc:
        raise ImportedHtmlRuntimeValidationError(
            f"Checkout binding '{binding_id}' variant '{variant_id}' must use an absolute https URL."
        )


def _validate_selector_match_count(
    *,
    html_root: _HtmlNode,
    selector: str,
    context_label: str,
    min_matches: int = 1,
    max_matches: int | None = None,
) -> None:
    parsed = _parse_restricted_selector(selector)
    matches = [node for node in _iter_html_nodes(html_root) if _node_matches_selector(node, parsed)]
    if len(matches) < min_matches:
        raise ImportedHtmlRuntimeValidationError(
            f"{context_label} selector '{selector}' must match at least {min_matches} element(s) in the imported HTML. "
            f"Matched {len(matches)}."
        )
    if max_matches is not None and len(matches) > max_matches:
        raise ImportedHtmlRuntimeValidationError(
            f"{context_label} selector '{selector}' must match no more than {max_matches} element(s) in the imported HTML. "
            f"Matched {len(matches)}."
        )


def _iter_html_nodes(node: _HtmlNode):
    for child in node.children:
        yield child
        yield from _iter_html_nodes(child)


def _parse_restricted_selector(selector: str) -> _RestrictedSelector:
    raw = selector.strip()
    if not raw:
        raise ImportedHtmlRuntimeValidationError("Selectors must be non-empty strings.")
    if "," in raw or ">" in raw or "+" in raw or "~" in raw:
        raise ImportedHtmlRuntimeValidationError(
            f"Unsupported selector '{selector}'. {imported_html_selector_hint()}"
        )
    if _selector_has_combinator_whitespace(raw):
        raise ImportedHtmlRuntimeValidationError(
            f"Unsupported selector '{selector}'. {imported_html_selector_hint()}"
        )

    idx = 0
    length = len(raw)
    tag: str | None = None
    id_value: str | None = None
    classes: list[str] = []
    attrs: list[tuple[str, str | None]] = []
    checked = False

    tag_match = _TAG_RE.match(raw, idx)
    if tag_match:
        tag = tag_match.group(0).lower()
        idx = tag_match.end()

    while idx < length:
        char = raw[idx]
        if char == "#":
            idx += 1
            match = _IDENTIFIER_RE.match(raw, idx)
            if not match:
                raise ImportedHtmlRuntimeValidationError(
                    f"Unsupported selector '{selector}'. {imported_html_selector_hint()}"
                )
            if id_value is not None:
                raise ImportedHtmlRuntimeValidationError(
                    f"Unsupported selector '{selector}'. Only one #id is allowed."
                )
            id_value = match.group(0)
            idx = match.end()
            continue
        if char == ".":
            idx += 1
            match = _IDENTIFIER_RE.match(raw, idx)
            if not match:
                raise ImportedHtmlRuntimeValidationError(
                    f"Unsupported selector '{selector}'. {imported_html_selector_hint()}"
                )
            classes.append(match.group(0))
            idx = match.end()
            continue
        if char == "[":
            end_idx = raw.find("]", idx + 1)
            if end_idx == -1:
                raise ImportedHtmlRuntimeValidationError(
                    f"Unsupported selector '{selector}'. Unterminated attribute selector."
                )
            content = raw[idx + 1 : end_idx]
            if not content:
                raise ImportedHtmlRuntimeValidationError(
                    f"Unsupported selector '{selector}'. Empty attribute selector."
                )
            if "=" in content:
                attr_name, raw_value = content.split("=", 1)
                attr_name = attr_name.strip().lower()
                raw_value = raw_value.strip()
                if not attr_name or not _ATTR_NAME_RE.fullmatch(attr_name):
                    raise ImportedHtmlRuntimeValidationError(
                        f"Unsupported selector '{selector}'. Invalid attribute name."
                    )
                if (raw_value.startswith('"') and raw_value.endswith('"')) or (
                    raw_value.startswith("'") and raw_value.endswith("'")
                ):
                    attr_value = raw_value[1:-1]
                else:
                    attr_value = raw_value
                attrs.append((attr_name, attr_value))
            else:
                attr_name = content.strip().lower()
                if not attr_name or not _ATTR_NAME_RE.fullmatch(attr_name):
                    raise ImportedHtmlRuntimeValidationError(
                        f"Unsupported selector '{selector}'. Invalid attribute name."
                    )
                attrs.append((attr_name, None))
            idx = end_idx + 1
            continue
        if raw.startswith(":checked", idx):
            checked = True
            idx += len(":checked")
            continue
        raise ImportedHtmlRuntimeValidationError(
            f"Unsupported selector '{selector}'. {imported_html_selector_hint()}"
        )

    return _RestrictedSelector(
        raw=raw,
        tag=tag,
        id_value=id_value,
        class_names=tuple(classes),
        attrs=tuple(attrs),
        checked=checked,
    )


def _selector_has_combinator_whitespace(selector: str) -> bool:
    in_brackets = False
    quote_char: str | None = None
    for char in selector:
        if quote_char:
            if char == quote_char:
                quote_char = None
            continue
        if char in {"'", '"'}:
            quote_char = char
            continue
        if char == "[":
            in_brackets = True
            continue
        if char == "]":
            in_brackets = False
            continue
        if char.isspace() and not in_brackets:
            return True
    return False


def _node_matches_selector(node: _HtmlNode, selector: _RestrictedSelector) -> bool:
    if selector.tag and node.tag != selector.tag:
        return False
    if selector.id_value is not None and node.attrs.get("id") != selector.id_value:
        return False
    if selector.class_names and not set(selector.class_names).issubset(node.class_names):
        return False
    for attr_name, attr_value in selector.attrs:
        if attr_name not in node.attrs:
            return False
        if attr_value is not None and node.attrs.get(attr_name) != attr_value:
            return False
    if selector.checked:
        checked_values = {"", "checked", "true", "1"}
        selected_values = {"", "selected", "true", "1"}
        if node.tag == "input":
            if node.attrs.get("checked", "").lower() not in checked_values:
                return False
        elif node.tag == "option":
            if node.attrs.get("selected", "").lower() not in selected_values:
                return False
        else:
            aria_checked = node.attrs.get("aria-checked", "").strip().lower()
            if aria_checked not in {"true", "1"}:
                return False
    return True
