from __future__ import annotations

import ast
import json
import uuid
from collections.abc import Iterator
from datetime import datetime, timezone
from typing import Any, Literal, Optional, cast

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.enums import FunnelPageVersionSourceEnum, FunnelPageVersionStatusEnum
from app.db.models import Funnel, FunnelPage, FunnelPageVersion
from app.llm.client import LLMClient, LLMGenerationParams
from app.services.funnels import default_puck_data
from app.services.funnels import _walk_json as walk_json  # reuse internal helper
from app.services.funnels import create_funnel_image_asset


_ASSISTANT_MESSAGE_MAX_CHARS = 600
_REPAIR_PREVIOUS_RESPONSE_MAX_CHARS = 4000
_CLAUDE_MAX_OUTPUT_TOKENS = 64000


class _AssistantMessageJsonExtractor:
    """
    Incrementally extracts and JSON-unescapes the value of the top-level "assistantMessage" field
    from a streamed JSON response.
    """

    def __init__(self) -> None:
        self._pattern = '"assistantMessage"'
        self._search_window = ""
        self._state: Literal["search", "after_key", "after_colon", "in_string", "done"] = "search"
        self._escape = False
        self._unicode_remaining = 0
        self._unicode_buffer = ""
        self._pending_high_surrogate: int | None = None

    def feed(self, chunk: str) -> str:
        emitted: list[str] = []

        for ch in chunk:
            if self._state == "done":
                break

            if self._state == "search":
                self._search_window = (self._search_window + ch)[-len(self._pattern) :]
                if self._search_window.endswith(self._pattern):
                    self._state = "after_key"
                continue

            if self._state == "after_key":
                if ch.isspace():
                    continue
                if ch == ":":
                    self._state = "after_colon"
                else:
                    # Unexpected token; reset search.
                    self._state = "search"
                    self._search_window = ""
                continue

            if self._state == "after_colon":
                if ch.isspace():
                    continue
                if ch == '"':
                    self._state = "in_string"
                else:
                    # assistantMessage isn't a string; stop trying to stream it.
                    self._state = "done"
                continue

            if self._state != "in_string":
                continue

            if self._unicode_remaining:
                if ch.lower() in "0123456789abcdef":
                    self._unicode_buffer += ch
                    self._unicode_remaining -= 1
                    if self._unicode_remaining == 0:
                        codepoint = int(self._unicode_buffer, 16)
                        self._unicode_buffer = ""
                        if self._pending_high_surrogate is not None:
                            high = self._pending_high_surrogate
                            self._pending_high_surrogate = None
                            if 0xDC00 <= codepoint <= 0xDFFF:
                                combined = 0x10000 + ((high - 0xD800) << 10) + (codepoint - 0xDC00)
                                emitted.append(chr(combined))
                            else:
                                emitted.append(chr(high))
                                emitted.append(chr(codepoint))
                        elif 0xD800 <= codepoint <= 0xDBFF:
                            self._pending_high_surrogate = codepoint
                        else:
                            emitted.append(chr(codepoint))
                else:
                    # Invalid escape; emit raw and reset.
                    self._unicode_remaining = 0
                    self._unicode_buffer = ""
                    emitted.append(ch)
                continue

            if self._escape:
                self._escape = False
                if ch in ('"', "\\", "/"):
                    emitted.append(ch)
                elif ch == "b":
                    emitted.append("\b")
                elif ch == "f":
                    emitted.append("\f")
                elif ch == "n":
                    emitted.append("\n")
                elif ch == "r":
                    emitted.append("\r")
                elif ch == "t":
                    emitted.append("\t")
                elif ch == "u":
                    self._unicode_remaining = 4
                    self._unicode_buffer = ""
                else:
                    emitted.append(ch)
                continue

            if ch == "\\":
                self._escape = True
                continue
            if ch == '"':
                if self._pending_high_surrogate is not None:
                    emitted.append(chr(self._pending_high_surrogate))
                    self._pending_high_surrogate = None
                self._state = "done"
                continue

            emitted.append(ch)

        return "".join(emitted)


def _extract_json_object(text: str) -> dict[str, Any]:
    text = text.strip()
    if not text:
        raise ValueError("Model returned empty response")
    for candidate in (text, _repair_json_text(text)):
        if not candidate:
            continue
        try:
            parsed = json.loads(candidate)
            if isinstance(parsed, dict):
                return cast(dict[str, Any], parsed)
        except Exception:
            pass
        try:
            parsed = ast.literal_eval(candidate)
            if isinstance(parsed, dict):
                return cast(dict[str, Any], parsed)
        except Exception:
            pass

    start: int | None = None
    depth = 0
    in_string = False
    escape = False
    for i, ch in enumerate(text):
        if start is None:
            if ch == "{":
                start = i
                depth = 1
                in_string = False
                escape = False
            continue

        if in_string:
            if escape:
                escape = False
                continue
            if ch == "\\":
                escape = True
                continue
            if ch == '"':
                in_string = False
            continue

        if ch == '"':
            in_string = True
            continue
        if ch == "{":
            depth += 1
            continue
        if ch == "}":
            depth -= 1
            if depth == 0:
                candidate = text[start : i + 1]
                start = None
                for attempt in (candidate, _repair_json_text(candidate)):
                    if not attempt:
                        continue
                    try:
                        parsed = json.loads(attempt)
                    except Exception:
                        parsed = None
                    if parsed is None:
                        try:
                            parsed = ast.literal_eval(attempt)
                        except Exception:
                            parsed = None
                    if isinstance(parsed, dict):
                        return cast(dict[str, Any], parsed)

    raise ValueError("Model did not return a JSON object")


def _repair_json_text(text: str) -> str:
    if not text:
        return text
    repaired = _strip_trailing_commas(text)
    return _escape_unescaped_control_chars(repaired)


def _strip_trailing_commas(text: str) -> str:
    out: list[str] = []
    in_string = False
    escape = False
    for ch in text:
        if in_string:
            out.append(ch)
            if escape:
                escape = False
                continue
            if ch == "\\":
                escape = True
                continue
            if ch == '"':
                in_string = False
            continue

        if ch == '"':
            in_string = True
            out.append(ch)
            continue

        if ch in ("}", "]"):
            j = len(out) - 1
            while j >= 0 and out[j].isspace():
                j -= 1
            if j >= 0 and out[j] == ",":
                out.pop(j)
        out.append(ch)

    return "".join(out)


def _escape_unescaped_control_chars(text: str) -> str:
    out: list[str] = []
    in_string = False
    escape = False
    for ch in text:
        if in_string:
            if escape:
                out.append(ch)
                escape = False
                continue
            if ch == "\\":
                out.append(ch)
                escape = True
                continue
            if ch == '"':
                in_string = False
                out.append(ch)
                continue
            if ch == "\n":
                out.append("\\n")
                continue
            if ch == "\r":
                out.append("\\r")
                continue
            if ch == "\t":
                out.append("\\t")
                continue
            if ch == "\b":
                out.append("\\b")
                continue
            if ch == "\f":
                out.append("\\f")
                continue
            if ord(ch) < 0x20:
                out.append(f"\\u{ord(ch):04x}")
                continue
            out.append(ch)
            continue

        if ch == '"':
            in_string = True
        out.append(ch)

    return "".join(out)


def _coerce_assistant_message(raw: Any) -> str:
    if not isinstance(raw, str) or not raw.strip():
        return "Generated a new draft page."
    message = raw.strip()
    if len(message) <= _ASSISTANT_MESSAGE_MAX_CHARS:
        return message
    truncated = message[:_ASSISTANT_MESSAGE_MAX_CHARS].rstrip()
    if not truncated.endswith("..."):
        truncated = f"{truncated}..."
    return truncated


def _coerce_max_tokens(model: Optional[str], max_tokens: Optional[int]) -> Optional[int]:
    if not model:
        return max_tokens
    lower = model.lower()
    if lower.startswith("claude"):
        if max_tokens is None:
            return _CLAUDE_MAX_OUTPUT_TOKENS
        return min(max_tokens, _CLAUDE_MAX_OUTPUT_TOKENS)
    return max_tokens


def _sanitize_puck_data(data: Any) -> dict[str, Any]:
    if not isinstance(data, dict):
        return default_puck_data()
    root = data.get("root")
    content = data.get("content")
    zones = data.get("zones")
    if not isinstance(root, dict):
        root = {"props": {}}
    elif not isinstance(root.get("props"), dict):
        root["props"] = {}
    if not isinstance(content, list):
        content = []
    if not isinstance(zones, dict):
        zones = {}
    return {"root": root, "content": content, "zones": zones}


def _ensure_block_ids(puck_data: dict[str, Any]) -> None:
    seen: set[str] = set()
    for obj in walk_json(puck_data):
        if not isinstance(obj, dict):
            continue
        t = obj.get("type")
        props = obj.get("props")
        if not isinstance(t, str) or not isinstance(props, dict):
            continue
        block_id = props.get("id")
        if not isinstance(block_id, str) or not block_id.strip() or block_id in seen:
            block_id = str(uuid.uuid4())
            props["id"] = block_id
        seen.add(block_id)


def _coerce_puck_data(raw: Any) -> Any:
    if isinstance(raw, str):
        text = raw.strip()
        if text:
            try:
                return _extract_json_object(text)
            except Exception:
                try:
                    return json.loads(text)
                except Exception:
                    try:
                        return json.loads(_repair_json_text(text))
                    except Exception:
                        return raw
    return raw


def _puck_response_format() -> dict[str, Any]:
    return {
        "type": "json_schema",
        "json_schema": {
            "name": "PuckDraft",
            "strict": True,
            "schema": {
                "type": "object",
                "additionalProperties": False,
                "properties": {
                    "assistantMessage": {"type": "string"},
                    "puckData": {
                        "type": "object",
                        "additionalProperties": True,
                        "properties": {
                            "root": {"type": "object", "additionalProperties": True},
                            "content": {
                                "type": "array",
                                "items": {
                                    "type": "object",
                                    "additionalProperties": True,
                                    "properties": {
                                        "type": {"type": "string"},
                                        "props": {"type": "object", "additionalProperties": True},
                                    },
                                    "required": ["type", "props"],
                                },
                            },
                            "zones": {"type": "object", "additionalProperties": True},
                        },
                        "required": ["root", "content", "zones"],
                    },
                },
                "required": ["assistantMessage", "puckData"],
            },
        },
    }


def _prompt_wants_header_footer(prompt: str) -> tuple[bool, bool]:
    lowered = (prompt or "").lower()
    wants_header = ("header" in lowered) or ("navigation" in lowered) or (" nav" in lowered) or lowered.startswith("nav")
    wants_footer = "footer" in lowered
    return wants_header, wants_footer


def _puck_has_section_purpose(puck_data: dict[str, Any], purpose: str) -> bool:
    content = puck_data.get("content")
    if not isinstance(content, list):
        return False
    for item in content:
        if not isinstance(item, dict):
            continue
        if item.get("type") != "Section":
            continue
        props = item.get("props")
        if isinstance(props, dict) and props.get("purpose") == purpose:
            return True
    return False


def _make_component(component_type: str, props: dict[str, Any]) -> dict[str, Any]:
    if "id" not in props or not isinstance(props.get("id"), str) or not props.get("id"):
        props["id"] = str(uuid.uuid4())
    return {"type": component_type, "props": props}


def _inject_header_footer_if_missing(
    *,
    puck_data: dict[str, Any],
    page_name: str,
    current_page_id: str,
    page_context: list[dict[str, Any]],
    wants_header: bool,
    wants_footer: bool,
) -> None:
    content = puck_data.get("content")
    if not isinstance(content, list):
        content = []
        puck_data["content"] = content

    if wants_header and not _puck_has_section_purpose(puck_data, "header"):
        nav_targets = [p for p in page_context if str(p.get("id")) and str(p.get("id")) != str(current_page_id)]
        nav_targets = nav_targets[:2]
        nav_buttons: list[dict[str, Any]] = []
        for p in nav_targets:
            nav_buttons.append(
                _make_component(
                    "Button",
                    {
                        "label": str(p.get("name") or "Page"),
                        "variant": "secondary",
                        "size": "sm",
                        "align": "right",
                        "linkType": "funnelPage",
                        "targetPageId": str(p.get("id")),
                    },
                )
            )

        header_left: list[dict[str, Any]] = [
            _make_component(
                "Heading",
                {"text": page_name or "Header", "level": 4, "align": "left"},
            ),
        ]
        header_right: list[dict[str, Any]] = nav_buttons or [
            _make_component(
                "Button",
                {"label": "Continue", "variant": "secondary", "size": "sm", "align": "right"},
            )
        ]
        header = _make_component(
            "Section",
            {
                "purpose": "header",
                "layout": "full",
                "containerWidth": "lg",
                "variant": "default",
                "padding": "sm",
                "content": [
                    _make_component(
                        "Columns",
                        {"ratio": "2:1", "gap": "md", "left": header_left, "right": header_right},
                    )
                ],
            },
        )
        content.insert(0, header)

    if wants_footer and not _puck_has_section_purpose(puck_data, "footer"):
        footer_items: list[dict[str, Any]] = [
            _make_component(
                "Text",
                {
                    "text": "Educational only. Not medical advice. If you have symptoms that worsen or take medications, consult a licensed clinician.",
                    "size": "sm",
                    "tone": "muted",
                },
            )
        ]
        footer = _make_component(
            "Section",
            {
                "purpose": "footer",
                "layout": "full",
                "containerWidth": "lg",
                "variant": "muted",
                "padding": "md",
                "content": footer_items,
            },
        )
        content.append(footer)


def _sanitize_component_tree(items: Any, allowed_types: set[str]) -> list[dict[str, Any]]:
    if not isinstance(items, list):
        return []
    cleaned: list[dict[str, Any]] = []
    for raw in items:
        if not isinstance(raw, dict):
            continue
        t = raw.get("type")
        props = raw.get("props")
        if not isinstance(t, str) or t not in allowed_types or not isinstance(props, dict):
            continue

        # Ensure slot-like children are lists to avoid runtime errors.
        if t == "Section":
            if not isinstance(props.get("content"), list):
                props["content"] = []
            props["content"] = _sanitize_component_tree(props.get("content"), allowed_types)
        elif t == "Columns":
            if not isinstance(props.get("left"), list):
                props["left"] = []
            if not isinstance(props.get("right"), list):
                props["right"] = []
            props["left"] = _sanitize_component_tree(props.get("left"), allowed_types)
            props["right"] = _sanitize_component_tree(props.get("right"), allowed_types)
        elif t == "FeatureGrid":
            if not isinstance(props.get("features"), list):
                props["features"] = []
        elif t == "Testimonials":
            if not isinstance(props.get("testimonials"), list):
                props["testimonials"] = []
        elif t == "FAQ":
            if not isinstance(props.get("items"), list):
                props["items"] = []

        cleaned.append(cast(dict[str, Any], raw))

    return cleaned


def _fill_ai_images(
    *,
    session: Session,
    org_id: str,
    client_id: str,
    puck_data: dict[str, Any],
    max_images: int = 3,
) -> tuple[int, list[dict[str, Any]]]:
    generated: list[dict[str, Any]] = []
    count = 0
    for obj in walk_json(puck_data):
        if count >= max_images:
            break
        if not isinstance(obj, dict):
            continue
        if obj.get("type") != "Image":
            continue
        props = obj.get("props")
        if not isinstance(props, dict):
            continue
        if props.get("assetPublicId"):
            continue
        prompt = props.get("prompt")
        if not isinstance(prompt, str) or not prompt.strip():
            continue
        try:
            asset = create_funnel_image_asset(
                session=session,
                org_id=org_id,
                client_id=client_id,
                prompt=prompt.strip(),
                aspect_ratio=None,
                usage_context={"kind": "funnel_page_image"},
            )
            props["assetPublicId"] = str(asset.public_id)
            generated.append({"prompt": prompt.strip(), "publicId": str(asset.public_id), "assetId": str(asset.id)})
            count += 1
        except Exception as exc:  # noqa: BLE001
            generated.append({"prompt": prompt.strip(), "error": str(exc)})
            count += 1
    return count, generated


def generate_funnel_page_draft(
    *,
    session: Session,
    org_id: str,
    user_id: str,
    funnel_id: str,
    page_id: str,
    prompt: str,
    messages: Optional[list[dict[str, str]]] = None,
    current_puck_data: Optional[dict[str, Any]] = None,
    model: Optional[str] = None,
    temperature: float = 0.2,
    max_tokens: Optional[int] = None,
    generate_images: bool = True,
    max_images: int = 3,
) -> tuple[str, FunnelPageVersion, dict[str, Any], list[dict[str, Any]]]:
    llm = LLMClient()
    model_id = model or llm.default_model
    max_tokens = _coerce_max_tokens(model_id, max_tokens)

    funnel = session.scalars(select(Funnel).where(Funnel.org_id == org_id, Funnel.id == funnel_id)).first()
    if not funnel:
        raise ValueError("Funnel not found")

    page = session.scalars(
        select(FunnelPage).where(FunnelPage.funnel_id == funnel_id, FunnelPage.id == page_id)
    ).first()
    if not page:
        raise ValueError("Page not found")

    pages = list(
        session.scalars(
            select(FunnelPage)
            .where(FunnelPage.funnel_id == funnel_id)
            .order_by(FunnelPage.ordering.asc(), FunnelPage.created_at.asc())
        ).all()
    )
    page_context = [{"id": str(p.id), "name": p.name, "slug": p.slug} for p in pages]

    latest_draft = session.scalars(
        select(FunnelPageVersion)
        .where(
            FunnelPageVersion.page_id == page_id,
            FunnelPageVersion.status == FunnelPageVersionStatusEnum.draft,
        )
        .order_by(FunnelPageVersion.created_at.desc(), FunnelPageVersion.id.desc())
    ).first()
    base_puck = current_puck_data or (latest_draft.puck_data if latest_draft else None)
    if not isinstance(base_puck, dict):
        base_puck = None

    system = {
        "role": "system",
        "content": (
            "You are generating content for a Puck editor sales page.\n\n"
            "You MUST output valid JSON only (no markdown, no code fences, no commentary).\n"
            "Do not wrap the output in ``` or any code fences.\n"
            "The response must start with '{' and end with '}' (no leading or trailing text).\n"
            "Use \\n for line breaks inside JSON string values (no raw newlines).\n"
            "Return exactly ONE JSON object with this shape:\n"
            '{ "assistantMessage": string, "puckData": { "root": { "props": object }, "content": ComponentData[], "zones": object } }\n\n'
            "Output the top-level keys in this exact order: assistantMessage, puckData.\n\n"
            "assistantMessage requirements:\n"
            "- Plain text (no markdown)\n"
            f"- Keep it under {_ASSISTANT_MESSAGE_MAX_CHARS} characters (short summary only; do not include full page copy)\n"
            "- Provide a short preview of the page (headings + main CTA only) so it looks good in a chat bubble\n"
            "- Include a medical safety disclaimer and avoid making medical claims\n\n"
            "Copy goals:\n"
            "- High-converting direct-response structure (clear promise, benefits, proof, objections/FAQ, repeated CTA)\n"
            "- Be specific and scannable (short paragraphs, bullets)\n"
            "- Use ethical persuasion; avoid fear-mongering\n\n"
            "Layout guidance:\n"
            "- Default to Section.layout='full' for most sections (full-width background)\n"
            "- Use Section.containerWidth='lg' for a modern website width (use 'xl' if you need more)\n"
            "- Alternate Section.variant between 'default' and 'muted' to create clear visual sections\n\n"
            "Structure guidance:\n"
            "- Use Section as the top-level blocks in puckData.content (do not place bare Heading/Text directly at the root)\n"
            "- Use Columns inside Sections for two-column layouts (image + copy)\n\n"
            "Header/Footer guidance:\n"
            "- If the user requests a header: add a Section with props.purpose='header' as the FIRST item in puckData.content\n"
            "- If the user requests a footer: add a Section with props.purpose='footer' as the LAST item in puckData.content\n"
            "- Header should include brand + simple navigation (Buttons linking to internal pages when available)\n"
            "- Footer should include a brief disclaimer + secondary links (Buttons)\n\n"
            "ComponentData shape:\n"
            "- Every component must be an object with keys: type, props\n"
            "- props should include a string id (unique per component)\n\n"
            "Available primitives (component types) and their props:\n"
            "1) Section: props { id, purpose?, layout?, containerWidth?, variant?, padding?, content? }\n"
            "   - purpose: 'header' | 'section' | 'footer'\n"
            "   - layout: 'full' | 'contained' | 'card'\n"
            "     - full = full-width background, content constrained to containerWidth\n"
            "     - contained = background constrained to containerWidth (no card styling)\n"
            "     - card = contained card with border/rounding/shadow (avoid for modern landing pages)\n"
            "   - containerWidth: 'sm' | 'md' | 'lg' | 'xl'\n"
            "   - content is a slot: ComponentData[]\n"
            "2) Columns: props { id, ratio?, gap?, left?, right? }\n"
            "   - left/right are slots: ComponentData[]\n"
            "3) Heading: props { id, text, level?, align? }\n"
            "   - level: 1|2|3|4 (H1-H4)\n"
            "   - align: 'left' | 'center'\n"
            "4) Text: props { id, text, size?, tone?, align? }\n"
            "   - size: 'sm' | 'md' | 'lg'\n"
            "   - tone: 'default' | 'muted'\n"
            "   - align: 'left' | 'center'\n"
            "5) Spacer: props { id, height }\n"
            "6) Image: props { id, prompt, alt, assetPublicId?, src?, radius? }\n"
            "   - radius: 'none' | 'md' | 'lg'\n"
            "7) Button: props { id, label, variant?, size?, width?, align?, linkType?, targetPageId?, href? }\n"
            "   - variant: 'primary' | 'secondary'\n"
            "   - size: 'sm' | 'md' | 'lg'\n"
            "   - width: 'auto' | 'full'\n"
            "   - align: 'left' | 'center' | 'right'\n"
            "   - If linkType='funnelPage': include targetPageId\n"
            "   - If linkType='external': include href\n"
            "8) FeatureGrid: props { id, title?, columns?, features? }\n"
            "9) Testimonials: props { id, title?, testimonials? }\n"
            "10) FAQ: props { id, title?, items? }\n\n"
            "Root props (optional):\n"
            "- root.props.title\n"
            "- root.props.description\n\n"
            "Internal funnel pages you can link to (targetPageId should be one of these ids):\n"
            f"{json.dumps(page_context, ensure_ascii=False)}\n\n"
            "Current page puckData (may be null):\n"
            f"{json.dumps(base_puck, ensure_ascii=False)}"
        ),
    }

    conversation: list[dict[str, str]] = []
    if messages:
        for msg in messages:
            role = msg.get("role")
            content = msg.get("content")
            if role in ("user", "assistant") and isinstance(content, str) and content.strip():
                conversation.append({"role": cast(Literal["user", "assistant"], role), "content": content.strip()})
    if prompt and prompt.strip():
        conversation.append({"role": "user", "content": prompt.strip()})
    if not conversation:
        conversation.append({"role": "user", "content": "Generate a simple funnel landing page."})

    base_prompt_parts = [system["content"]] + [f"{m['role'].upper()}: {m['content']}" for m in conversation]
    compiled_prompt = "\n\n".join(base_prompt_parts + ["Return JSON now."])

    allowed_types = {
        "Section",
        "Columns",
        "Heading",
        "Text",
        "Button",
        "Image",
        "Spacer",
        "FeatureGrid",
        "Testimonials",
        "FAQ",
    }

    params = LLMGenerationParams(
        model=model_id,
        max_tokens=max_tokens,
        temperature=temperature,
        use_reasoning=True,
        use_web_search=False,
        response_format=_puck_response_format(),
    )
    out = llm.generate_text(compiled_prompt, params=params)

    try:
        obj = _extract_json_object(out)
    except Exception as exc:  # noqa: BLE001
        repair_lines = [
            "The previous response was invalid JSON. Regenerate from scratch.",
            f"Error: {exc}",
            f"assistantMessage must be under {_ASSISTANT_MESSAGE_MAX_CHARS} characters.",
            "The response must start with '{' and end with '}' (no code fences).",
        ]
        if len(out) <= _REPAIR_PREVIOUS_RESPONSE_MAX_CHARS:
            repair_lines.append(f"Previous response:\n{out}")
        repair_lines.append("Return corrected JSON only.")
        repair_prompt = "\n\n".join(base_prompt_parts + repair_lines)
        out = llm.generate_text(repair_prompt, params=params)
        obj = _extract_json_object(out)

    assistant_message = _coerce_assistant_message(obj.get("assistantMessage") if isinstance(obj, dict) else None)

    puck_data_raw = _coerce_puck_data(obj.get("puckData") if isinstance(obj, dict) else None)
    puck_data = _sanitize_puck_data(puck_data_raw)
    puck_data["content"] = _sanitize_component_tree(puck_data.get("content"), allowed_types)
    zones = puck_data.get("zones")
    if isinstance(zones, dict):
        for key, value in list(zones.items()):
            zones[key] = _sanitize_component_tree(value, allowed_types)
    _ensure_block_ids(puck_data)
    if not puck_data.get("content"):
        repair_prompt = "\n\n".join(
            base_prompt_parts
            + [
                "Your previous response resulted in an empty page.",
                "Return a complete page using the available component types listed above.",
                f"assistantMessage must be under {_ASSISTANT_MESSAGE_MAX_CHARS} characters.",
                "The response must start with '{' and end with '}' (no code fences).",
                f"Previous response:\n{out}" if len(out) <= _REPAIR_PREVIOUS_RESPONSE_MAX_CHARS else "",
                "Return corrected JSON only.",
            ]
        )
        out = llm.generate_text(repair_prompt, params=params)
        obj = _extract_json_object(out)
        assistant_message = _coerce_assistant_message(obj.get("assistantMessage") if isinstance(obj, dict) else None)
        puck_data_raw = _coerce_puck_data(obj.get("puckData") if isinstance(obj, dict) else None)
        puck_data = _sanitize_puck_data(puck_data_raw)
        puck_data["content"] = _sanitize_component_tree(puck_data.get("content"), allowed_types)
        zones = puck_data.get("zones")
        if isinstance(zones, dict):
            for key, value in list(zones.items()):
                zones[key] = _sanitize_component_tree(value, allowed_types)
        _ensure_block_ids(puck_data)

    wants_header, wants_footer = _prompt_wants_header_footer(prompt)
    missing_header = wants_header and not _puck_has_section_purpose(puck_data, "header")
    missing_footer = wants_footer and not _puck_has_section_purpose(puck_data, "footer")
    if missing_header or missing_footer:
        requirements: list[str] = []
        if missing_header:
            requirements.append(
                "- Add a header Section as the FIRST item with props.purpose='header', layout='full', containerWidth='lg', padding='sm'."
            )
            requirements.append("- Header content should include brand + navigation Buttons (link to internal pages when available).")
        if missing_footer:
            requirements.append(
                "- Add a footer Section as the LAST item with props.purpose='footer', layout='full', containerWidth='lg', variant='muted', padding='md'."
            )
            requirements.append("- Footer content should include a brief disclaimer + secondary navigation Buttons.")

        repair_prompt = "\n\n".join(
            base_prompt_parts
            + [
                "Your previous response did not include the requested header/footer sections in puckData.content.",
                *requirements,
                "Keep the rest of the page content unchanged.",
                f"Previous response:\n{out}",
                "Return corrected JSON only.",
            ]
        )
        out = llm.generate_text(repair_prompt, params=params)
        obj = _extract_json_object(out)
        assistant_message = _coerce_assistant_message(obj.get("assistantMessage") if isinstance(obj, dict) else None)
        puck_data_raw = _coerce_puck_data(obj.get("puckData") if isinstance(obj, dict) else None)
        puck_data = _sanitize_puck_data(puck_data_raw)
        puck_data["content"] = _sanitize_component_tree(puck_data.get("content"), allowed_types)
        zones = puck_data.get("zones")
        if isinstance(zones, dict):
            for key, value in list(zones.items()):
                zones[key] = _sanitize_component_tree(value, allowed_types)
        _ensure_block_ids(puck_data)

    _inject_header_footer_if_missing(
        puck_data=puck_data,
        page_name=page.name,
        current_page_id=page_id,
        page_context=page_context,
        wants_header=wants_header,
        wants_footer=wants_footer,
    )

    if not puck_data.get("content"):
        raise RuntimeError("AI generation produced an empty page (no content).")

    root_props = puck_data.get("root", {}).get("props") if isinstance(puck_data.get("root"), dict) else None
    if isinstance(root_props, dict):
        title = root_props.get("title")
        if not isinstance(title, str) or not title.strip():
            root_props["title"] = page.name
        desc = root_props.get("description")
        if not isinstance(desc, str):
            root_props["description"] = ""

    generated_images: list[dict[str, Any]] = []
    if generate_images:
        try:
            _, generated_images = _fill_ai_images(
                session=session,
                org_id=org_id,
                client_id=str(funnel.client_id),
                puck_data=puck_data,
                max_images=max_images,
            )
        except Exception as exc:  # noqa: BLE001
            generated_images = [{"error": str(exc)}]

    version = FunnelPageVersion(
        page_id=page.id,
        status=FunnelPageVersionStatusEnum.draft,
        puck_data=puck_data,
        source=FunnelPageVersionSourceEnum.ai,
        created_at=datetime.now(timezone.utc),
        ai_metadata={
            "prompt": prompt,
            "messages": conversation,
            "model": model or llm.default_model,
            "temperature": temperature,
            "generatedAt": datetime.now(timezone.utc).isoformat(),
            "generatedImages": generated_images,
            "actorUserId": user_id,
        },
    )
    session.add(version)
    session.commit()
    session.refresh(version)
    return assistant_message, version, puck_data, generated_images


def stream_funnel_page_draft(
    *,
    session: Session,
    org_id: str,
    user_id: str,
    funnel_id: str,
    page_id: str,
    prompt: str,
    messages: Optional[list[dict[str, str]]] = None,
    current_puck_data: Optional[dict[str, Any]] = None,
    model: Optional[str] = None,
    temperature: float = 0.2,
    max_tokens: Optional[int] = None,
    generate_images: bool = True,
    max_images: int = 3,
) -> Iterator[dict[str, Any]]:
    """
    Runs the page-draft generation while returning stream-friendly events.

    Event shapes (dict):
    - {type:"start", model:string}
    - {type:"text", text:string} (assistantMessage deltas)
    - {type:"status", status:string}
    - {type:"done", assistantMessage, puckData, draftVersionId, generatedImages}
    - {type:"error", message}
    """

    llm = LLMClient()
    model_id = model or llm.default_model
    max_tokens = _coerce_max_tokens(model_id, max_tokens)

    yield {"type": "start", "model": model_id}
    yield {"type": "status", "status": "generating"}

    try:
        funnel = session.scalars(select(Funnel).where(Funnel.org_id == org_id, Funnel.id == funnel_id)).first()
        if not funnel:
            raise ValueError("Funnel not found")

        page = session.scalars(
            select(FunnelPage).where(FunnelPage.funnel_id == funnel_id, FunnelPage.id == page_id)
        ).first()
        if not page:
            raise ValueError("Page not found")

        pages = list(
            session.scalars(
                select(FunnelPage)
                .where(FunnelPage.funnel_id == funnel_id)
                .order_by(FunnelPage.ordering.asc(), FunnelPage.created_at.asc())
            ).all()
        )
        page_context = [{"id": str(p.id), "name": p.name, "slug": p.slug} for p in pages]

        latest_draft = session.scalars(
            select(FunnelPageVersion)
            .where(
                FunnelPageVersion.page_id == page_id,
                FunnelPageVersion.status == FunnelPageVersionStatusEnum.draft,
            )
            .order_by(FunnelPageVersion.created_at.desc(), FunnelPageVersion.id.desc())
        ).first()
        base_puck = current_puck_data or (latest_draft.puck_data if latest_draft else None)
        if not isinstance(base_puck, dict):
            base_puck = None

        system = {
            "role": "system",
            "content": (
                "You are generating content for a Puck editor sales page.\n\n"
                "You MUST output valid JSON only (no markdown, no code fences, no commentary).\n"
                "Do not wrap the output in ``` or any code fences.\n"
                "The response must start with '{' and end with '}' (no leading or trailing text).\n"
                "Use \\n for line breaks inside JSON string values (no raw newlines).\n"
                "Return exactly ONE JSON object with this shape:\n"
                '{ "assistantMessage": string, "puckData": { "root": { "props": object }, "content": ComponentData[], "zones": object } }\n\n'
                "Output the top-level keys in this exact order: assistantMessage, puckData.\n\n"
                "assistantMessage requirements:\n"
                "- Plain text (no markdown)\n"
                f"- Keep it under {_ASSISTANT_MESSAGE_MAX_CHARS} characters (short summary only; do not include full page copy)\n"
                "- Provide a short preview of the page (headings + main CTA only) so it looks good in a chat bubble\n"
                "- Include a medical safety disclaimer and avoid making medical claims\n\n"
                "Copy goals:\n"
                "- High-converting direct-response structure (clear promise, benefits, proof, objections/FAQ, repeated CTA)\n"
                "- Be specific and scannable (short paragraphs, bullets)\n"
                "- Use ethical persuasion; avoid fear-mongering\n\n"
                "Layout guidance:\n"
                "- Default to Section.layout='full' for most sections (full-width background)\n"
                "- Use Section.containerWidth='lg' for a modern website width (use 'xl' if you need more)\n"
                "- Alternate Section.variant between 'default' and 'muted' to create clear visual sections\n\n"
                "Structure guidance:\n"
                "- Use Section as the top-level blocks in puckData.content (do not place bare Heading/Text directly at the root)\n"
                "- Use Columns inside Sections for two-column layouts (image + copy)\n\n"
                "Header/Footer guidance:\n"
                "- If the user requests a header: add a Section with props.purpose='header' as the FIRST item in puckData.content\n"
                "- If the user requests a footer: add a Section with props.purpose='footer' as the LAST item in puckData.content\n"
                "- Header should include brand + simple navigation (Buttons linking to internal pages when available)\n"
                "- Footer should include a brief disclaimer + secondary links (Buttons)\n\n"
                "ComponentData shape:\n"
                "- Every component must be an object with keys: type, props\n"
                "- props should include a string id (unique per component)\n\n"
                "Available primitives (component types) and their props:\n"
                "1) Section: props { id, purpose?, layout?, containerWidth?, variant?, padding?, content? }\n"
                "   - purpose: 'header' | 'section' | 'footer'\n"
                "   - layout: 'full' | 'contained' | 'card'\n"
                "     - full = full-width background, content constrained to containerWidth\n"
                "     - contained = background constrained to containerWidth (no card styling)\n"
                "     - card = contained card with border/rounding/shadow (avoid for modern landing pages)\n"
                "   - containerWidth: 'sm' | 'md' | 'lg' | 'xl'\n"
                "   - content is a slot: ComponentData[]\n"
                "2) Columns: props { id, ratio?, gap?, left?, right? }\n"
                "   - left/right are slots: ComponentData[]\n"
                "3) Heading: props { id, text, level?, align? }\n"
                "   - level: 1|2|3|4 (H1-H4)\n"
                "   - align: 'left' | 'center'\n"
                "4) Text: props { id, text, size?, tone?, align? }\n"
                "   - size: 'sm' | 'md' | 'lg'\n"
                "   - tone: 'default' | 'muted'\n"
                "   - align: 'left' | 'center'\n"
                "5) Spacer: props { id, height }\n"
                "6) Image: props { id, prompt, alt, assetPublicId?, src?, radius? }\n"
                "   - radius: 'none' | 'md' | 'lg'\n"
                "7) Button: props { id, label, variant?, size?, width?, align?, linkType?, targetPageId?, href? }\n"
                "   - variant: 'primary' | 'secondary'\n"
                "   - size: 'sm' | 'md' | 'lg'\n"
                "   - width: 'auto' | 'full'\n"
                "   - align: 'left' | 'center' | 'right'\n"
                "   - If linkType='funnelPage': include targetPageId\n"
                "   - If linkType='external': include href\n"
                "8) FeatureGrid: props { id, title?, columns?, features? }\n"
                "9) Testimonials: props { id, title?, testimonials? }\n"
                "10) FAQ: props { id, title?, items? }\n\n"
                "Root props (optional):\n"
                "- root.props.title\n"
                "- root.props.description\n\n"
                "Internal funnel pages you can link to (targetPageId should be one of these ids):\n"
                f"{json.dumps(page_context, ensure_ascii=False)}\n\n"
                "Current page puckData (may be null):\n"
                f"{json.dumps(base_puck, ensure_ascii=False)}"
            ),
        }

        conversation: list[dict[str, str]] = []
        if messages:
            for msg in messages:
                role = msg.get("role")
                content = msg.get("content")
                if role in ("user", "assistant") and isinstance(content, str) and content.strip():
                    conversation.append(
                        {"role": cast(Literal["user", "assistant"], role), "content": content.strip()}
                    )
        if prompt and prompt.strip():
            conversation.append({"role": "user", "content": prompt.strip()})
        if not conversation:
            conversation.append({"role": "user", "content": "Generate a simple funnel landing page."})

        base_prompt_parts = [system["content"]] + [f"{m['role'].upper()}: {m['content']}" for m in conversation]
        compiled_prompt = "\n\n".join(base_prompt_parts + ["Return JSON now."])

        allowed_types = {
            "Section",
            "Columns",
            "Heading",
            "Text",
            "Button",
            "Image",
            "Spacer",
            "FeatureGrid",
            "Testimonials",
            "FAQ",
        }

        params = LLMGenerationParams(
            model=model_id,
            max_tokens=max_tokens,
            temperature=temperature,
            use_reasoning=True,
            use_web_search=False,
            response_format=_puck_response_format(),
        )

        extractor = _AssistantMessageJsonExtractor()
        raw_parts: list[str] = []
        for delta in llm.stream_text(compiled_prompt, params=params):
            raw_parts.append(delta)
            if delta:
                yield {"type": "raw", "text": delta}
            assistant_delta = extractor.feed(delta)
            if assistant_delta:
                yield {"type": "text", "text": assistant_delta}

        out = "".join(raw_parts)

        try:
            obj = _extract_json_object(out)
        except Exception as exc:  # noqa: BLE001
            yield {"type": "status", "status": "repairing"}
            repair_lines = [
                "The previous response was invalid JSON. Regenerate from scratch.",
                f"Error: {exc}",
                f"assistantMessage must be under {_ASSISTANT_MESSAGE_MAX_CHARS} characters.",
                "The response must start with '{' and end with '}' (no code fences).",
            ]
            if len(out) <= _REPAIR_PREVIOUS_RESPONSE_MAX_CHARS:
                repair_lines.append(f"Previous response:\n{out}")
            repair_lines.append("Return corrected JSON only.")
            repair_prompt = "\n\n".join(base_prompt_parts + repair_lines)
            out = llm.generate_text(repair_prompt, params=params)
            obj = _extract_json_object(out)

        assistant_message = _coerce_assistant_message(obj.get("assistantMessage") if isinstance(obj, dict) else None)

        puck_data_raw = _coerce_puck_data(obj.get("puckData") if isinstance(obj, dict) else None)
        puck_data = _sanitize_puck_data(puck_data_raw)
        puck_data["content"] = _sanitize_component_tree(puck_data.get("content"), allowed_types)
        zones = puck_data.get("zones")
        if isinstance(zones, dict):
            for key, value in list(zones.items()):
                zones[key] = _sanitize_component_tree(value, allowed_types)
        _ensure_block_ids(puck_data)

        if not puck_data.get("content"):
            yield {"type": "status", "status": "repairing_empty"}
            repair_prompt = "\n\n".join(
                base_prompt_parts
                + [
                    "Your previous response resulted in an empty page.",
                    "Return a complete page using the available component types listed above.",
                    f"assistantMessage must be under {_ASSISTANT_MESSAGE_MAX_CHARS} characters.",
                    "The response must start with '{' and end with '}' (no code fences).",
                    f"Previous response:\n{out}" if len(out) <= _REPAIR_PREVIOUS_RESPONSE_MAX_CHARS else "",
                    "Return corrected JSON only.",
                ]
            )
            out = llm.generate_text(repair_prompt, params=params)
            obj = _extract_json_object(out)
            assistant_message = _coerce_assistant_message(obj.get("assistantMessage") if isinstance(obj, dict) else None)
            puck_data_raw = _coerce_puck_data(obj.get("puckData") if isinstance(obj, dict) else None)
            puck_data = _sanitize_puck_data(puck_data_raw)
            puck_data["content"] = _sanitize_component_tree(puck_data.get("content"), allowed_types)
            zones = puck_data.get("zones")
            if isinstance(zones, dict):
                for key, value in list(zones.items()):
                    zones[key] = _sanitize_component_tree(value, allowed_types)
            _ensure_block_ids(puck_data)

        wants_header, wants_footer = _prompt_wants_header_footer(prompt)
        missing_header = wants_header and not _puck_has_section_purpose(puck_data, "header")
        missing_footer = wants_footer and not _puck_has_section_purpose(puck_data, "footer")
        if missing_header or missing_footer:
            yield {"type": "status", "status": "repairing_header_footer"}
            requirements: list[str] = []
            if missing_header:
                requirements.append(
                    "- Add a header Section as the FIRST item with props.purpose='header', layout='full', containerWidth='lg', padding='sm'."
                )
                requirements.append(
                    "- Header content should include brand + navigation Buttons (link to internal pages when available)."
                )
            if missing_footer:
                requirements.append(
                    "- Add a footer Section as the LAST item with props.purpose='footer', layout='full', containerWidth='lg', variant='muted', padding='md'."
                )
                requirements.append("- Footer content should include a brief disclaimer + secondary navigation Buttons.")

            repair_prompt = "\n\n".join(
                base_prompt_parts
                + [
                    "Your previous response did not include the requested header/footer sections in puckData.content.",
                    *requirements,
                    "Keep the rest of the page content unchanged.",
                    f"Previous response:\n{out}",
                    "Return corrected JSON only.",
                ]
            )
            out = llm.generate_text(repair_prompt, params=params)
            obj = _extract_json_object(out)
            assistant_message = _coerce_assistant_message(obj.get("assistantMessage") if isinstance(obj, dict) else None)
            puck_data_raw = _coerce_puck_data(obj.get("puckData") if isinstance(obj, dict) else None)
            puck_data = _sanitize_puck_data(puck_data_raw)
            puck_data["content"] = _sanitize_component_tree(puck_data.get("content"), allowed_types)
            zones = puck_data.get("zones")
            if isinstance(zones, dict):
                for key, value in list(zones.items()):
                    zones[key] = _sanitize_component_tree(value, allowed_types)
            _ensure_block_ids(puck_data)

        _inject_header_footer_if_missing(
            puck_data=puck_data,
            page_name=page.name,
            current_page_id=page_id,
            page_context=page_context,
            wants_header=wants_header,
            wants_footer=wants_footer,
        )

        if not puck_data.get("content"):
            yield {"type": "error", "message": "AI generation produced an empty page (no content)."}
            return

        root_props = puck_data.get("root", {}).get("props") if isinstance(puck_data.get("root"), dict) else None
        if isinstance(root_props, dict):
            title = root_props.get("title")
            if not isinstance(title, str) or not title.strip():
                root_props["title"] = page.name
            desc = root_props.get("description")
            if not isinstance(desc, str):
                root_props["description"] = ""

        generated_images: list[dict[str, Any]] = []
        if generate_images:
            yield {"type": "status", "status": "generating_images"}
            try:
                _, generated_images = _fill_ai_images(
                    session=session,
                    org_id=org_id,
                    client_id=str(funnel.client_id),
                    puck_data=puck_data,
                    max_images=max_images,
                )
            except Exception as exc:  # noqa: BLE001
                generated_images = [{"error": str(exc)}]

        version = FunnelPageVersion(
            page_id=page.id,
            status=FunnelPageVersionStatusEnum.draft,
            puck_data=puck_data,
            source=FunnelPageVersionSourceEnum.ai,
            created_at=datetime.now(timezone.utc),
            ai_metadata={
                "prompt": prompt,
                "messages": conversation,
                "model": model_id,
                "temperature": temperature,
                "generatedAt": datetime.now(timezone.utc).isoformat(),
                "generatedImages": generated_images,
                "actorUserId": user_id,
            },
        )
        session.add(version)
        session.commit()
        session.refresh(version)

        yield {
            "type": "done",
            "assistantMessage": assistant_message,
            "puckData": puck_data,
            "draftVersionId": str(version.id),
            "generatedImages": generated_images,
        }
        return
    except Exception as exc:  # noqa: BLE001
        yield {"type": "error", "message": str(exc)}
        return
