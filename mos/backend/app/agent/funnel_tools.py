from __future__ import annotations

import hashlib
import json
import time
from collections.abc import Generator
from copy import deepcopy
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Literal, Optional, cast

from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import select

from app.agent.runtime import BaseTool
from app.agent.types import ToolContext, ToolResult
from app.config import settings
from app.db.enums import FunnelPageReviewStatusEnum, FunnelPageVersionSourceEnum, FunnelPageVersionStatusEnum
from app.db.models import Funnel, FunnelPage, FunnelPageVersion, Product, ProductVariant
from app.db.repositories.agent_artifacts import AgentArtifactsRepository
from app.db.repositories.claude_context_files import ClaudeContextFilesRepository
from app.llm.client import LLMClient, LLMGenerationParams
from app.services.claude_files import build_document_blocks, call_claude_structured_message
from app.services.design_systems import resolve_design_system_tokens
from app.services.funnel_templates import get_funnel_template
from app.services.funnels import extract_internal_links, publish_funnel
from app.services.funnel_testimonials import generate_funnel_page_testimonials

# Reuse funnel_ai internals to keep behavior consistent while we split orchestration.
from app.services import funnel_ai as funnel_ai


_ObjectiveTemplateKind = Literal["sales-pdp", "pre-sales-listicle"]


def _resolve_template_kind(template_id: str) -> _ObjectiveTemplateKind | None:
    if template_id == "sales-pdp":
        return "sales-pdp"
    if template_id == "pre-sales-listicle":
        return "pre-sales-listicle"
    return None


def _allowed_component_types(template_kind: str | None, *, template_mode: bool = False) -> set[str]:
    # Template pages should preserve structure, so restrict "creative" primitives to avoid
    # the LLM inserting extra sections/blocks that are not part of the template.
    if template_mode and template_kind == "sales-pdp":
        return {
            "SalesPdpPage",
            "SalesPdpHeader",
            "SalesPdpHero",
            "SalesPdpVideos",
            "SalesPdpMarquee",
            "SalesPdpStoryProblem",
            "SalesPdpStorySolution",
            "SalesPdpComparison",
            "SalesPdpGuarantee",
            "SalesPdpFaq",
            "SalesPdpReviews",
            "SalesPdpReviewWall",
            "SalesPdpFooter",
            "SalesPdpReviewSlider",
            "SalesPdpTemplate",
        }
    if template_mode and template_kind == "pre-sales-listicle":
        return {
            "PreSalesPage",
            "PreSalesHero",
            "PreSalesReasons",
            "PreSalesReviews",
            "PreSalesMarquee",
            "PreSalesPitch",
            "PreSalesReviewWall",
            "PreSalesFooter",
            "PreSalesFloatingCta",
            "PreSalesTemplate",
        }

    allowed = {
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
    if template_kind == "sales-pdp":
        allowed.update(
            {
                "SalesPdpPage",
                "SalesPdpHeader",
                "SalesPdpHero",
                "SalesPdpVideos",
                "SalesPdpMarquee",
                "SalesPdpStoryProblem",
                "SalesPdpStorySolution",
                "SalesPdpComparison",
                "SalesPdpGuarantee",
                "SalesPdpFaq",
                "SalesPdpReviews",
                "SalesPdpReviewWall",
                "SalesPdpFooter",
                "SalesPdpReviewSlider",
                "SalesPdpTemplate",
            }
        )
    elif template_kind == "pre-sales-listicle":
        allowed.update(
            {
                "PreSalesPage",
                "PreSalesHero",
                "PreSalesReasons",
                "PreSalesReviews",
                "PreSalesMarquee",
                "PreSalesPitch",
                "PreSalesReviewWall",
                "PreSalesFooter",
                "PreSalesFloatingCta",
                "PreSalesTemplate",
            }
        )
    return allowed


@dataclass(frozen=True)
class _TemplateContext:
    template_id: str | None
    template_mode: bool
    template_kind: str | None


def _build_attachment_guidance(attachment_summaries: list[dict[str, Any]]) -> str:
    if not attachment_summaries:
        return ""
    lines = [
        "Attached images guidance:",
        "- Use Image.props.assetPublicId to place an attached image as-is.",
        "- Use Image.props.referenceAssetPublicId with a prompt to generate a new image based on an attachment.",
        "- Do not invent assetPublicId/referenceAssetPublicId values.",
        "Attached images:",
    ]
    for item in attachment_summaries:
        line = f"- {item.get('publicId')}"
        filename = item.get("filename") or ""
        if filename:
            line += f" (filename: {filename})"
        if item.get("width") and item.get("height"):
            line += f" [{item.get('width')}x{item.get('height')}]"
        lines.append(line)
    return "\n".join(lines) + "\n\n"


_TRACE_TEXT_PREVIEW_MAX_CHARS = 4000


def _sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _text_preview(text: str, *, limit: int = _TRACE_TEXT_PREVIEW_MAX_CHARS) -> str:
    return text[:limit]


def _persist_agent_artifact(
    *,
    ctx: ToolContext,
    kind: str,
    key: str | None,
    data_json: dict[str, Any],
) -> None:
    if not ctx.tool_call_id:
        raise RuntimeError("ToolContext.tool_call_id is required to persist agent artifacts.")
    AgentArtifactsRepository(ctx.session).create(run_id=ctx.run_id, kind=kind, key=key, data_json=data_json)


class ContextLoadFunnelArgs(BaseModel):
    model_config = ConfigDict(extra="forbid")

    orgId: str
    funnelId: str
    pageId: str
    currentPuckData: Optional[dict[str, Any]] = None
    templateId: Optional[str] = None


class ContextLoadFunnelTool(BaseTool[ContextLoadFunnelArgs]):
    name = "context.load_funnel"
    ArgsModel = ContextLoadFunnelArgs

    def run(self, *, ctx: ToolContext, args: ContextLoadFunnelArgs) -> ToolResult:
        if args.orgId != ctx.org_id:
            raise ValueError("orgId mismatch")

        funnel = ctx.session.scalars(
            select(Funnel).where(Funnel.org_id == ctx.org_id, Funnel.id == args.funnelId)
        ).first()
        if not funnel:
            raise ValueError("Funnel not found")

        page = ctx.session.scalars(
            select(FunnelPage).where(FunnelPage.funnel_id == args.funnelId, FunnelPage.id == args.pageId)
        ).first()
        if not page:
            raise ValueError("Page not found")

        resolved_template_id = funnel_ai._resolve_template_id(args.templateId, page)
        template = get_funnel_template(resolved_template_id) if resolved_template_id else None
        if resolved_template_id and not template:
            raise ValueError("Template not found")

        template_kind = None
        if template is not None:
            template_kind = _resolve_template_kind(template.template_id)
            if template_kind is None:
                raise ValueError(f"Template {template.template_id} is not supported for AI generation")

        pages = list(
            ctx.session.scalars(
                select(FunnelPage)
                .where(FunnelPage.funnel_id == args.funnelId)
                .order_by(FunnelPage.ordering.asc(), FunnelPage.created_at.asc())
            ).all()
        )
        page_context = [{"id": str(p.id), "name": p.name, "slug": p.slug} for p in pages]
        page_id_set = {str(p.id) for p in pages}

        latest_draft = ctx.session.scalars(
            select(FunnelPageVersion)
            .where(
                FunnelPageVersion.page_id == args.pageId,
                FunnelPageVersion.status == FunnelPageVersionStatusEnum.draft,
            )
            .order_by(FunnelPageVersion.created_at.desc(), FunnelPageVersion.id.desc())
        ).first()

        base_puck = args.currentPuckData or (latest_draft.puck_data if latest_draft else None)
        if not isinstance(base_puck, dict):
            base_puck = None
        if template is not None and base_puck is None:
            base_puck = template.puck_data

        required_types: list[str] = []
        if template is not None:
            # Required components should track the active template definition, not the stored page puckData.
            # Older funnels may have been created from a previous template structure; DraftApplyOverridesTool
            # upgrades/merges them with the latest template before validation.
            required_source = template.puck_data if isinstance(template.puck_data, dict) else base_puck
            if isinstance(required_source, dict):
                required_types = sorted(
                    funnel_ai._required_template_component_types(required_source, template_kind=template_kind)
                )

        allowed_types = sorted(
            _allowed_component_types(template_kind, template_mode=template is not None)
        )

        template_ctx = _TemplateContext(
            template_id=resolved_template_id,
            template_mode=template is not None,
            template_kind=template_kind,
        )

        ui_details = {
            "funnelId": str(funnel.id),
            "clientId": str(funnel.client_id),
            "productId": str(funnel.product_id) if funnel.product_id else None,
            "campaignId": str(funnel.campaign_id) if funnel.campaign_id else None,
            "pageId": str(page.id),
            "pageName": page.name,
            "pageSlug": page.slug,
            "pageContext": page_context,
            "pageIdSet": sorted(page_id_set),
            "basePuckData": base_puck,
            "templateId": template_ctx.template_id,
            "templateMode": template_ctx.template_mode,
            "templateKind": template_ctx.template_kind,
            "allowedTypes": allowed_types,
            "requiredTypes": required_types,
        }

        llm_output = json.dumps(
            {
                "templateId": template_ctx.template_id,
                "templateKind": template_ctx.template_kind,
                "allowedTypes": allowed_types,
            },
            ensure_ascii=False,
            separators=(",", ":"),
        )
        return ToolResult(llm_output=llm_output, ui_details=ui_details, attachments=[])


class ContextLoadProductOfferArgs(BaseModel):
    model_config = ConfigDict(extra="forbid")

    orgId: str
    funnelId: str
    clientId: str


class ContextLoadProductOfferTool(BaseTool[ContextLoadProductOfferArgs]):
    name = "context.load_product_offer"
    ArgsModel = ContextLoadProductOfferArgs

    def run(self, *, ctx: ToolContext, args: ContextLoadProductOfferArgs) -> ToolResult:
        if args.orgId != ctx.org_id:
            raise ValueError("orgId mismatch")
        funnel = ctx.session.scalars(
            select(Funnel).where(Funnel.org_id == ctx.org_id, Funnel.id == args.funnelId)
        ).first()
        if not funnel:
            raise ValueError("Funnel not found")

        product, offer, product_context = funnel_ai._load_product_context(
            session=ctx.session,
            org_id=ctx.org_id,
            client_id=args.clientId,
            funnel=funnel,
        )

        ui_details = {
            "productId": str(product.id) if product else None,
            "selectedOfferId": str(funnel.selected_offer_id) if funnel.selected_offer_id else None,
            "productContext": product_context,
        }
        if offer:
            ui_details["offerId"] = str(offer.id)

        llm_output = product_context
        return ToolResult(llm_output=llm_output, ui_details=ui_details, attachments=[])


class ContextLoadDesignTokensArgs(BaseModel):
    model_config = ConfigDict(extra="forbid")

    orgId: str
    clientId: str
    funnelId: str
    pageId: str


class ContextLoadDesignTokensTool(BaseTool[ContextLoadDesignTokensArgs]):
    name = "context.load_design_tokens"
    ArgsModel = ContextLoadDesignTokensArgs

    def run(self, *, ctx: ToolContext, args: ContextLoadDesignTokensArgs) -> ToolResult:
        if args.orgId != ctx.org_id:
            raise ValueError("orgId mismatch")

        funnel = ctx.session.scalars(
            select(Funnel).where(Funnel.org_id == ctx.org_id, Funnel.id == args.funnelId)
        ).first()
        if not funnel:
            raise ValueError("Funnel not found")
        page = ctx.session.scalars(
            select(FunnelPage).where(FunnelPage.funnel_id == args.funnelId, FunnelPage.id == args.pageId)
        ).first()
        if not page:
            raise ValueError("Page not found")

        tokens = resolve_design_system_tokens(
            session=ctx.session,
            org_id=ctx.org_id,
            client_id=args.clientId,
            funnel=funnel,
            page=page,
        )

        brand_logo_public_id: str | None = None
        logo_alt: str | None = None
        if isinstance(tokens, dict):
            brand = tokens.get("brand")
            if isinstance(brand, dict):
                logo_value = brand.get("logoAssetPublicId")
                if isinstance(logo_value, str) and logo_value.strip():
                    brand_logo_public_id = logo_value.strip()
                alt_value = brand.get("logoAlt")
                if isinstance(alt_value, str) and alt_value.strip():
                    logo_alt = alt_value.strip()

        ui_details = {
            "designSystemTokens": tokens,
            "brandLogoAssetPublicId": brand_logo_public_id,
            "brandLogoAlt": logo_alt,
        }
        llm_output = json.dumps({"brandLogoAssetPublicId": brand_logo_public_id}, separators=(",", ":"))
        return ToolResult(llm_output=llm_output, ui_details=ui_details, attachments=[])


class ContextLoadBrandDocsArgs(BaseModel):
    model_config = ConfigDict(extra="forbid")

    orgId: str
    funnelId: str
    ideaWorkspaceId: Optional[str] = None


class ContextLoadBrandDocsTool(BaseTool[ContextLoadBrandDocsArgs]):
    name = "context.load_brand_docs"
    ArgsModel = ContextLoadBrandDocsArgs

    def run(self, *, ctx: ToolContext, args: ContextLoadBrandDocsArgs) -> ToolResult:
        if args.orgId != ctx.org_id:
            raise ValueError("orgId mismatch")

        funnel = ctx.session.scalars(
            select(Funnel).where(Funnel.org_id == ctx.org_id, Funnel.id == args.funnelId)
        ).first()
        if not funnel:
            raise ValueError("Funnel not found")
        if not funnel.product_id:
            raise ValueError("product_id is required to generate AI funnel drafts.")

        resolved_workspace_id = args.ideaWorkspaceId or f"client-{funnel.client_id}"
        ctx_repo = ClaudeContextFilesRepository(ctx.session)
        context_files = ctx_repo.list_for_generation_context(
            org_id=ctx.org_id,
            idea_workspace_id=resolved_workspace_id,
            client_id=str(funnel.client_id),
            product_id=str(funnel.product_id),
            campaign_id=str(funnel.campaign_id) if funnel.campaign_id else None,
        )

        documents = build_document_blocks(context_files)
        ui_details = {
            "ideaWorkspaceId": resolved_workspace_id,
            "contextFiles": [
                {
                    "id": str(getattr(rec, "id", "")),
                    "docKey": getattr(rec, "doc_key", None),
                    "docTitle": getattr(rec, "doc_title", None),
                    "claudeFileId": getattr(rec, "claude_file_id", None),
                    "status": getattr(rec, "status", None),
                }
                for rec in context_files
            ],
            "documentBlocks": documents,
        }
        llm_output = json.dumps(
            {"documents": [{"title": d.get("title"), "file_id": d.get("source", {}).get("file_id")} for d in documents]},
            separators=(",", ":"),
        )
        return ToolResult(llm_output=llm_output, ui_details=ui_details, attachments=[])


class DraftGeneratePageArgs(BaseModel):
    model_config = ConfigDict(extra="forbid")

    orgId: str
    funnelId: str
    pageId: str
    pageName: str = ""
    prompt: str
    messages: list[dict[str, str]] = Field(default_factory=list)
    model: Optional[str] = None
    temperature: float = 0.2
    maxTokens: Optional[int] = Field(default=None, gt=0)
    templateId: Optional[str] = None
    templateKind: Optional[str] = None
    templateMode: bool = False
    pageContext: list[dict[str, Any]] = Field(default_factory=list)
    basePuckData: Optional[dict[str, Any]] = None
    productContext: str
    attachmentSummaries: list[dict[str, Any]] = Field(default_factory=list)
    brandDocuments: list[dict[str, Any]] = Field(default_factory=list)
    copyPack: Optional[str] = None


class DraftGeneratePageTool(BaseTool[DraftGeneratePageArgs]):
    name = "draft.generate_page"
    ArgsModel = DraftGeneratePageArgs

    def run_stream(self, *, ctx: ToolContext, args: DraftGeneratePageArgs) -> Generator[dict[str, Any], None, ToolResult]:
        if args.orgId != ctx.org_id:
            raise ValueError("orgId mismatch")

        llm = LLMClient()
        model_id = args.model or llm.default_model
        max_tokens = funnel_ai._coerce_max_tokens(model_id, args.maxTokens)

        template_kind = args.templateKind
        template_mode = bool(args.templateMode)
        template_component_kind: str | None = None
        if template_mode and isinstance(args.basePuckData, dict):
            template_component_kind = funnel_ai._infer_template_component_kind(template_kind, args.basePuckData)

        # Layout guidance varies based on template mode.
        if not template_mode:
            structure_guidance = (
                "- Use Section as the top-level blocks in puckData.content (do not place bare Heading/Text directly at the root)\n"
                "- Use Columns inside Sections for two-column layouts (image + copy)\n\n"
            )
        elif template_component_kind == "sales-pdp":
            structure_guidance = (
                "- Use SalesPdpPage as the ONLY top-level block in puckData.content\n"
                "- Put all SalesPdp* sections inside SalesPdpPage.props.content (slot)\n"
                "- Do NOT add primitives like Section/Columns/Heading/Text/Spacer in template mode\n"
                "- Preserve the overall section order; update copy/images inside each section's props.config / props.copy / props.modals / props.theme\n\n"
            )
        elif template_component_kind == "pre-sales-listicle":
            structure_guidance = (
                "- Use PreSalesPage as the ONLY top-level block in puckData.content\n"
                "- Put all PreSales* sections inside PreSalesPage.props.content (slot)\n"
                "- Do NOT add primitives like Section/Columns/Heading/Text/Spacer in template mode\n"
                "- Preserve the overall section order; update copy/images inside each section's props.config / props.copy / props.theme\n\n"
            )
        else:
            structure_guidance = (
                "- Preserve the template's existing top-level structure in puckData.content.\n"
                "- Do not introduce new component types; only edit props fields.\n\n"
            )

        header_footer_guidance = (
            "Header/Footer guidance:\n"
            "- If the user requests a header: add a Section with props.purpose='header' as the FIRST item in puckData.content\n"
            "- If the user requests a footer: add a Section with props.purpose='footer' as the LAST item in puckData.content\n"
            "- Header should include brand + simple navigation (Buttons linking to internal pages when available)\n"
            "- Footer should include a brief disclaimer + secondary links (Buttons)\n\n"
            if not template_mode
            else ""
        )

        copy_pack_guidance = ""
        if isinstance(args.copyPack, str) and args.copyPack.strip():
            copy_pack_guidance = (
                "Copy pack (source of truth):\n"
                "- Use this copy as the default wording for headlines, claims, and offers.\n"
                "- Do not invent missing facts; keep health/medical claims conservative.\n"
                f"{args.copyPack.strip()}\n\n"
            )

        context_guidance = (
            "Context guidance:\n"
            "- Use the attached brand documents as the source of truth for brand voice, offer, and constraints.\n\n"
            if args.brandDocuments
            else ""
        )

        # Claude structured outputs: support brand docs and vision attachments (non-stream).
        #
        # We intentionally do NOT switch models: if brand docs/vision blocks are present, the caller
        # must already be using a Claude model. This keeps model selection explicit and avoids hidden
        # "fallback" behavior.
        is_claude_model = model_id.lower().startswith("claude")
        if args.brandDocuments and not is_claude_model:
            raise ValueError("brandDocuments require a Claude model (model must start with 'claude').")
        if args.attachmentSummaries and not is_claude_model:
            raise ValueError(
                "attachmentSummaries require a Claude vision-capable model (model must start with 'claude')."
            )

        attachment_summaries = args.attachmentSummaries
        attachment_blocks: list[dict[str, Any]] = []
        if args.attachmentSummaries:
            if not ctx.client_id:
                raise ValueError("client_id is required to load attachment blocks for Claude generation.")
            attachment_summaries, attachment_blocks = funnel_ai._build_attachment_blocks(
                session=ctx.session,
                org_id=ctx.org_id,
                client_id=ctx.client_id,
                attachments=args.attachmentSummaries,
            )

        attachment_guidance = _build_attachment_guidance(attachment_summaries)

        template_guidance = (
            f"Template guidance:\n- Template id: {args.templateId}\n"
            "- Do not introduce new component types not listed below.\n"
            "- Do not remove or rename existing template components in the current page puckData; only edit their props/config/copy fields.\n"
            if template_mode and args.templateId
            else ""
        )

        template_image_guidance = ""
        if template_mode:
            template_image_guidance = (
                "Template image prompts:\n"
                "- Add a `prompt` on every image object inside props.config/props.modals/props.copy that should be generated.\n"
                "- Do NOT add prompts to brand logos (logo objects). Keep logo assetPublicId intact.\n"
                "- Do NOT add prompts to testimonial images (objects with testimonialTemplate); those are rendered separately.\n"
                "- Leave the corresponding *AssetPublicId field empty so the backend can generate and fill it.\n"
                "- Placeholder /assets/ph-* images must be replaced with prompts or assetPublicId.\n"
                "- Prefer Unsplash for stock-appropriate imagery (lifestyle, generic product-in-use, backgrounds).\n"
                "- To use Unsplash, set imageSource='unsplash' on the image object and include a prompt.\n"
                "- Use AI generation only when stock imagery does not fit the need.\n"
                "- Icon prompts (iconAssetPublicId) must use this style template, replacing <subject> with the context item: "
                "\"High-quality flat design icon of <subject>. Minimalist vector style with subtle depth. Clean thick lines, "
                "soft pastel colors, flat lighting with a very subtle long shadow to add dimension. "
                "Full-bleed composition where the icon symbol occupies nearly the entire frame with minimal padding. "
                "Do not place the icon inside a badge, circle, tile, button, sticker, or any container shape. "
                "Ultra-sharp, high-resolution, high-fidelity vector rendering with crisp edges and clean color separation. "
                "Crisp vector graphics, dribbble aesthetic, professional UI asset. No text, no blur.\"\n"
                "- For icon prompts, set iconAlt/alt/label clearly so the backend can derive <subject> deterministically.\n"
                "- Brand color palette from design_system_tokens.cssVars is injected automatically before image generation.\n"
                "- Do not set referenceAssetPublicId unless you are using one of the attached images listed above.\n"
                "- If you want to base it on an attached image, set referenceAssetPublicId on that image object and include the prompt.\n\n"
            )
            if template_kind == "sales-pdp":
                template_image_guidance += (
                    "Sales PDP product imagery:\n"
                    "- Hero/gallery imagery must show the product clearly.\n"
                    "- Any section that calls out the product should include the product in the image.\n\n"
                )
            if template_kind == "pre-sales-listicle":
                template_image_guidance += (
                    "Pre-sales listicle imagery:\n"
                    "- Reason images should use a square (1:1) aspect ratio.\n"
                    "- If copy references the product, include the product in the image.\n\n"
                )

        template_config_guidance = ""
        if template_mode and template_component_kind == "sales-pdp":
            template_config_guidance = (
                "Sales PDP config requirements:\n"
                "- SalesPdpHeader.config MUST be: { logo: { alt:string, src?:string, assetPublicId?:string, href?:string }, nav: [{ label:string, href:string }], cta: { label:string, href:string } }\n"
                "- SalesPdpHero.config MUST be: { header: { ...same as SalesPdpHeader.config }, gallery: { watchInAction: { label:string }, slides: [{ alt:string, src?:string, assetPublicId?:string, thumbSrc?:string, thumbAssetPublicId?:string }], freeGifts: { icon:{ alt:string, src?:string, assetPublicId?:string }, title:string, body:string, ctaLabel:string } }, purchase: { faqPills: [{ label:string, answer:string }], title:string, benefits:[{ text:string }], size:{ title:string, helpLinkLabel:string, options:[{ id:string, label:string, sizeIn:string, sizeCm:string }], shippingDelayLabel:string }, color:{ title:string, options:[{ id:string, label:string, swatch?:string, swatchImageSrc?:string, swatchAssetPublicId?:string }], outOfStockTitle:string, outOfStockBody:string }, offer:{ title:string, helperText:string, seeWhyLabel:string, options:[{ id:string, title:string, image:{ alt:string, src?:string, assetPublicId?:string }, price:number, compareAt?:number, saveLabel?:string, productOfferId?:string } ] }, cta:{ labelTemplate:string, subBullets:string[], urgency:{ message:string, rows:[{ label:string, value:string, tone?:'muted'|'highlight' }] } }, outOfStock?:[{ sizeId:string, colorId:string }], shippingDelay?:[{ sizeId:string, colorId:string }] } }\n"
                "- SalesPdpHero.modals MUST be: { sizeChart: { title:string, sizes:[{ label:string, size:string, idealFor:string, weight:string }], note:string }, whyBundle: { title:string, body:string, quotes:[{ text:string, author:string }] }, freeGifts: { title:string, body:string } }\n"
                "- Checkout requirement: purchase size/color/offer option ids MUST match productContext.selected_offer.price_points[].option_values keys (sizeId/colorId/offerId). Do NOT invent ids.\n"
                "- SalesPdpMarquee.config MUST be: { items: string[], repeat?: number }\n"
                "- SalesPdpFaq.config MUST be: { title: string, items: [{ question: string, answer: string }] }\n"
                "- SalesPdpReviews.config MUST be: { id: string, data: object }\n"
                "- SalesPdpFooter.config MUST be: { logo: { alt:string, src?:string, assetPublicId?:string }, copyright: string }\n"
                "- SalesPdpReviewSlider.config MUST be: { title: string, body: string, hint: string, toggle: { auto: string, manual: string }, slides: [{ alt: string, src?: string, assetPublicId?: string }] }\n"
                "- Do NOT use legacy keys like headline/subheadline/trustBadges/ctaLabel/ctaLinkType/reviews inside SalesPdp* configs.\n\n"
            )
        elif template_mode and template_component_kind == "pre-sales-listicle":
            template_config_guidance = (
                "Pre-sales listicle config requirements:\n"
                "- PreSalesHero.config MUST be: { hero: { title: string, subtitle: string, media?: { type:'image', alt:string, src?:string, assetPublicId?:string } | { type:'video', srcMp4:string, poster?:string, alt?:string, assetPublicId?:string } }, badges: [] }\n"
                "- PreSalesHero.config.badges MUST always be an array (use [] when empty; never null).\n"
                "- PreSalesReasons.config MUST be an array of reasons: [{ number: number, title: string, body: string, image?: { alt:string, src?:string, assetPublicId?:string } }]\n"
                "- PreSalesMarquee.config MUST be an array of strings.\n"
                "- PreSalesPitch.config MUST be: { title: string, bullets: string[], image: { alt:string, src?:string, assetPublicId?:string }, cta?: { label: string, linkType?: 'external'|'funnelPage'|'nextPage', href?:string, targetPageId?:string } }\n"
                "- PreSalesReviews.config MUST be: { slides: [{ text: string, author: string, images: [{ alt:string, src?:string, assetPublicId?:string }] }], autoAdvanceMs?: number }\n"
                "- PreSalesFooter.config MUST be: { logo: { alt:string, src?:string, assetPublicId?:string } }\n"
                "- Do NOT use keys like headline/subheadline/ctaLabel/ctaLinkType/items/reasons/reviews/links/copyrightText inside PreSales* configs.\n\n"
            )

        if not template_mode:
            template_component = ""
        elif template_component_kind == "sales-pdp":
            template_component = (
                "11) SalesPdpPage: props { id, anchorId?, theme, themeJson?, content? }\n"
                "12) SalesPdpHeader: props { id, config, configJson? }\n"
                "13) SalesPdpHero: props { id, config, configJson?, modals?, modalsJson?, copy?, copyJson? }\n"
                "14) SalesPdpVideos: props { id, config, configJson? }\n"
                "15) SalesPdpMarquee: props { id, config, configJson? }\n"
                "16) SalesPdpStoryProblem: props { id, config, configJson? }\n"
                "17) SalesPdpStorySolution: props { id, config, configJson? }\n"
                "18) SalesPdpComparison: props { id, config, configJson? }\n"
                "19) SalesPdpGuarantee: props { id, config, configJson?, feedImages?, feedImagesJson? }\n"
                "20) SalesPdpFaq: props { id, config, configJson? }\n"
                "21) SalesPdpReviews: props { id, config, configJson? }\n"
                "22) SalesPdpReviewWall: props { id, config, configJson? }\n"
                "23) SalesPdpFooter: props { id, config, configJson? }\n"
                "24) SalesPdpReviewSlider: props { id, config, configJson? }\n"
            )
        elif template_component_kind == "pre-sales-listicle":
            template_component = (
                "11) PreSalesPage: props { id, anchorId?, theme, themeJson?, content? }\n"
                "12) PreSalesHero: props { id, config, configJson? }\n"
                "13) PreSalesReasons: props { id, config, configJson? }\n"
                "14) PreSalesReviews: props { id, config, configJson?, copy?, copyJson? }\n"
                "15) PreSalesMarquee: props { id, config, configJson? }\n"
                "16) PreSalesPitch: props { id, config, configJson? }\n"
                "17) PreSalesReviewWall: props { id, config, configJson?, copy?, copyJson? }\n"
                "18) PreSalesFooter: props { id, config, configJson? }\n"
                "19) PreSalesFloatingCta: props { id, config, configJson? }\n"
            )
        else:
            template_component = ""

        page_label = "sales page" if template_kind != "pre-sales-listicle" else "pre-sales listicle page"

        layout_guidance = ""
        if not template_mode:
            layout_guidance = (
                "Layout guidance:\n"
                "- Default to Section.layout='full' for most sections (do not place bare Heading/Text directly at the root)\n"
                "- Use Section.containerWidth='lg' for a modern website width (use 'xl' if you need more)\n"
                "- Alternate Section.variant between 'default' and 'muted' to create clear visual sections\n\n"
            )
        else:
            # In template mode we preserve the template layout and only update copy/config fields.
            layout_guidance = (
                "Layout guidance:\n"
                "- Preserve the template layout and section order.\n"
                "- Do NOT add new sections or new component types; only edit existing template component props.\n\n"
            )

        available_components_block = ""
        if template_mode and template_component:
            available_components_block = "Available template components (component types) and their props:\n" f"{template_component}\n"
        else:
            available_components_block = (
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
                "6) Image: props { id, prompt, alt, imageSource?, assetPublicId?, referenceAssetPublicId?, src?, radius? }\n"
                "   - imageSource: 'ai' (default) | 'unsplash'\n"
                "   - radius: 'none' | 'md' | 'lg'\n"
                "   - If imageSource='unsplash': include prompt and leave assetPublicId empty (no referenceAssetPublicId)\n"
                "   - If referenceAssetPublicId is set: include prompt and leave assetPublicId empty\n"
                "7) Button: props { id, label, variant?, size?, width?, align?, linkType?, targetPageId?, href? }\n"
                "   - variant: 'primary' | 'secondary'\n"
                "   - size: 'sm' | 'md' | 'lg'\n"
                "   - width: 'auto' | 'full'\n"
                "   - align: 'left' | 'center' | 'right'\n"
                "   - If linkType='funnelPage': include targetPageId\n"
                "   - If linkType='external': include href\n"
                "8) FeatureGrid: props { id, title?, columns?, features? }\n"
                "9) Testimonials: props { id, title?, testimonials? }\n"
                "10) FAQ: props { id, title?, items? }\n"
                f"{template_component}\n"
            )

        system_content = (
            f"You are generating content for a Puck editor {page_label}.\n\n"
            "You MUST output valid JSON only (no markdown, no code fences, no commentary).\n"
            "Do not wrap the output in ``` or any code fences.\n"
            "The response must start with '{' and end with '}' (no leading or trailing text).\n"
            "Use \\n for line breaks inside JSON string values (no raw newlines).\n"
            "Return exactly ONE JSON object with this shape:\n"
            '{ \"assistantMessage\": string, \"puckData\": string }\n'
            "puckData must be a JSON-encoded string for this object shape:\n"
            '{ \"root\": { \"props\": object }, \"content\": ComponentData[], \"zones\": object }\n\n'
            "puckData.content MUST be a non-empty array (include at least one top-level ComponentData item).\n\n"
            "Output the top-level keys in this exact order: assistantMessage, puckData.\n\n"
            "assistantMessage requirements:\n"
            "- Plain text (no markdown)\n"
            f"- Keep it under {funnel_ai._ASSISTANT_MESSAGE_MAX_CHARS} characters (short summary only; do not include full page copy)\n"
            "- Provide a short preview of the page (headings + main CTA only) so it looks good in a chat bubble\n"
            "- Include a medical safety disclaimer and avoid making medical claims\n\n"
            "Copy goals:\n"
            "- High-converting direct-response structure (clear promise, benefits, proof, objections/FAQ, repeated CTA)\n"
            "- Be specific and scannable (short paragraphs, bullets)\n"
            "- Use ethical persuasion; avoid fear-mongering\n\n"
            f"{layout_guidance}"
            f"{context_guidance}"
            f"{copy_pack_guidance}"
            f"{args.productContext}"
            f"{attachment_guidance}"
            f"{template_guidance}"
            f"{template_image_guidance}"
            f"{template_config_guidance}"
            "Structure guidance:\n"
            f"{structure_guidance}"
            f"{header_footer_guidance}"
            "ComponentData shape:\n"
            "- Every component must be an object with keys: type, props\n"
            "- props should include a string id (unique per component)\n\n"
            "- Do NOT double-encode JSON: only *Json fields (e.g., configJson) may contain JSON strings. props.config must be a JSON object/array, not a JSON-encoded string.\n\n"
            f"{available_components_block}"
            "Root props (optional):\n"
            "- root.props.title\n"
            "- root.props.description\n\n"
            "Internal funnel pages you can link to (targetPageId should be one of these ids):\n"
            f"{json.dumps(args.pageContext, ensure_ascii=False)}\n\n"
            "Current page puckData (may be null):\n"
            f"{json.dumps(args.basePuckData, ensure_ascii=False)}"
        )

        conversation: list[dict[str, str]] = []
        for msg in args.messages or []:
            role = msg.get("role")
            content = msg.get("content")
            if role in ("user", "assistant") and isinstance(content, str) and content.strip():
                conversation.append({"role": cast(Literal["user", "assistant"], role), "content": content.strip()})
        if args.prompt and args.prompt.strip():
            conversation.append({"role": "user", "content": args.prompt.strip()})
        if not conversation:
            conversation.append({"role": "user", "content": "Generate a simple funnel landing page."})

        base_prompt_parts = [system_content] + [f"{m['role'].upper()}: {m['content']}" for m in conversation]
        compiled_prompt = "\n\n".join(base_prompt_parts + ["Return JSON now."])

        allowed_types = _allowed_component_types(
            template_component_kind if template_mode else template_kind,
            template_mode=template_mode,
        )

        params = LLMGenerationParams(
            model=model_id,
            max_tokens=max_tokens,
            temperature=args.temperature,
            use_reasoning=True,
            use_web_search=False,
            response_format=funnel_ai._puck_response_format(),
        )

        trace_meta = {
            "runId": ctx.run_id,
            "toolCallId": ctx.tool_call_id,
            "toolName": ctx.tool_name,
            "toolSeq": ctx.tool_seq,
            "model": model_id,
            "temperature": args.temperature,
            "maxTokens": max_tokens,
            "templateMode": template_mode,
            "templateKind": template_kind,
            "templateComponentKind": template_component_kind,
        }

        def _trace_prompt(*, phase: str, prompt_text: str) -> str:
            sha256 = _sha256_text(prompt_text)
            _persist_agent_artifact(
                ctx=ctx,
                kind="llm.prompt",
                key=f"{ctx.tool_call_id}:{phase}",
                data_json={
                    **trace_meta,
                    "phase": phase,
                    "sha256": sha256,
                    "chars": len(prompt_text),
                    "preview": _text_preview(prompt_text),
                    "text": prompt_text,
                },
            )
            return sha256

        def _trace_output(*, phase: str, output_text: str, duration_ms: int | None) -> str:
            sha256 = _sha256_text(output_text)
            payload: dict[str, Any] = {
                **trace_meta,
                "phase": phase,
                "sha256": sha256,
                "chars": len(output_text),
                "preview": _text_preview(output_text),
                "text": output_text,
            }
            if duration_ms is not None:
                payload["durationMs"] = duration_ms
            _persist_agent_artifact(
                ctx=ctx,
                kind="llm.output",
                key=f"{ctx.tool_call_id}:{phase}",
                data_json=payload,
            )
            return sha256

        out = ""
        obj: dict[str, Any] | None = None
        final_model = model_id
        compiled_prompt_sha256 = _trace_prompt(phase="initial", prompt_text=compiled_prompt)
        raw_output_sha256: str | None = None

        def _claude_structured(prompt_text: str) -> tuple[dict[str, Any], str, int]:
            # Claude's global default max token budget in funnel_ai is intentionally huge (64k), but
            # page draft generations should not need that much. Large max_tokens budgets can cause
            # very long-running requests. Cap by default unless the caller explicitly overrides.
            default_claude_max = 20_000
            claude_max = args.maxTokens if args.maxTokens is not None else default_claude_max
            claude_max = min(claude_max, funnel_ai._CLAUDE_MAX_OUTPUT_TOKENS)
            user_content = [{"type": "text", "text": prompt_text}, *attachment_blocks, *args.brandDocuments]
            started = time.monotonic()
            response = call_claude_structured_message(
                model=model_id,
                system=None,
                user_content=user_content,
                output_schema=funnel_ai._puck_output_schema(),
                max_tokens=claude_max,
                temperature=args.temperature,
            )
            duration_ms = int((time.monotonic() - started) * 1000)
            parsed = response.get("parsed") if isinstance(response, dict) else None
            if not isinstance(parsed, dict):
                raise RuntimeError("Claude structured response returned no parsed JSON.")
            out_text = json.dumps(parsed, ensure_ascii=False)
            return parsed, out_text, duration_ms

        if is_claude_model:
            obj, out, duration_ms = _claude_structured(compiled_prompt)
            raw_output_sha256 = _trace_output(phase="initial", output_text=out, duration_ms=duration_ms)
        else:
            started = time.monotonic()
            extractor = funnel_ai._AssistantMessageJsonExtractor()
            raw_parts: list[str] = []
            for delta in llm.stream_text(compiled_prompt, params=params):
                raw_parts.append(delta)
                if delta:
                    yield {"type": "raw", "text": delta}
                assistant_delta = extractor.feed(delta)
                if assistant_delta:
                    yield {"type": "text", "text": assistant_delta}
            out = "".join(raw_parts)
            duration_ms = int((time.monotonic() - started) * 1000)
            raw_output_sha256 = _trace_output(phase="initial", output_text=out, duration_ms=duration_ms)

            try:
                obj = funnel_ai._extract_json_object(out)
            except Exception as exc:  # noqa: BLE001
                _persist_agent_artifact(
                    ctx=ctx,
                    kind="llm.error",
                    key=f"{ctx.tool_call_id}:repair_invalid_json",
                    data_json={
                        **trace_meta,
                        "phase": "repair_invalid_json",
                        "error": str(exc),
                        "outputSha256": raw_output_sha256,
                    },
                )
                yield {"type": "status", "status": "repairing"}
                repair_lines = [
                    "The previous response was invalid JSON. Regenerate from scratch.",
                    f"Error: {exc}",
                    f"assistantMessage must be under {funnel_ai._ASSISTANT_MESSAGE_MAX_CHARS} characters.",
                    "The response must start with '{' and end with '}' (no code fences).",
                ]
                if len(out) <= funnel_ai._REPAIR_PREVIOUS_RESPONSE_MAX_CHARS:
                    repair_lines.append(f"Previous response:\n{out}")
                repair_lines.append("Return corrected JSON only.")
                repair_prompt = "\n\n".join(base_prompt_parts + repair_lines)
                _trace_prompt(phase="repair_invalid_json", prompt_text=repair_prompt)
                started = time.monotonic()
                out = llm.generate_text(repair_prompt, params=params)
                duration_ms = int((time.monotonic() - started) * 1000)
                raw_output_sha256 = _trace_output(phase="repair_invalid_json", output_text=out, duration_ms=duration_ms)
                obj = funnel_ai._extract_json_object(out)

        if obj is None:
            raise RuntimeError("Model returned no parsable JSON response")

        assistant_message = funnel_ai._coerce_assistant_message(obj.get("assistantMessage") if isinstance(obj, dict) else None)

        puck_data_raw = funnel_ai._coerce_puck_data(obj.get("puckData") if isinstance(obj, dict) else None)
        puck_data = funnel_ai._sanitize_puck_data(puck_data_raw)
        puck_data["content"] = funnel_ai._sanitize_component_tree(puck_data.get("content"), allowed_types)
        zones = puck_data.get("zones")
        if isinstance(zones, dict):
            for key, value in list(zones.items()):
                zones[key] = funnel_ai._sanitize_component_tree(value, allowed_types)
        funnel_ai._ensure_block_ids(puck_data)

        if not puck_data.get("content"):
            yield {"type": "status", "status": "repairing_empty"}
            repair_prompt = "\n\n".join(
                base_prompt_parts
                + [
                    "Your previous response resulted in an empty page.",
                    "Return a complete page using the available component types listed above.",
                    f"assistantMessage must be under {funnel_ai._ASSISTANT_MESSAGE_MAX_CHARS} characters.",
                    "The response must start with '{' and end with '}' (no code fences).",
                    f"Previous response:\n{out}" if len(out) <= funnel_ai._REPAIR_PREVIOUS_RESPONSE_MAX_CHARS else "",
                    "Return corrected JSON only.",
                ]
            )
            if is_claude_model:
                _trace_prompt(phase="repair_empty_page", prompt_text=repair_prompt)
                obj, out, duration_ms = _claude_structured(repair_prompt)
                raw_output_sha256 = _trace_output(
                    phase="repair_empty_page",
                    output_text=out,
                    duration_ms=duration_ms,
                )
            else:
                _trace_prompt(phase="repair_empty_page", prompt_text=repair_prompt)
                started = time.monotonic()
                out = llm.generate_text(repair_prompt, params=params)
                duration_ms = int((time.monotonic() - started) * 1000)
                raw_output_sha256 = _trace_output(
                    phase="repair_empty_page",
                    output_text=out,
                    duration_ms=duration_ms,
                )
                obj = funnel_ai._extract_json_object(out)
            assistant_message = funnel_ai._coerce_assistant_message(obj.get("assistantMessage") if isinstance(obj, dict) else None)
            puck_data_raw = funnel_ai._coerce_puck_data(obj.get("puckData") if isinstance(obj, dict) else None)
            puck_data = funnel_ai._sanitize_puck_data(puck_data_raw)
            puck_data["content"] = funnel_ai._sanitize_component_tree(puck_data.get("content"), allowed_types)
            zones = puck_data.get("zones")
            if isinstance(zones, dict):
                for key, value in list(zones.items()):
                    zones[key] = funnel_ai._sanitize_component_tree(value, allowed_types)
            funnel_ai._ensure_block_ids(puck_data)

        # Header/footer request repair + deterministic injection (non-template only).
        wants_header, wants_footer = funnel_ai._prompt_wants_header_footer(args.prompt)
        if template_mode:
            wants_header = False
            wants_footer = False
        missing_header = wants_header and not funnel_ai._puck_has_section_purpose(puck_data, "header")
        missing_footer = wants_footer and not funnel_ai._puck_has_section_purpose(puck_data, "footer")
        if missing_header or missing_footer:
            yield {"type": "status", "status": "repairing_header_footer"}
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
            if is_claude_model:
                _trace_prompt(phase="repair_header_footer", prompt_text=repair_prompt)
                obj, out, duration_ms = _claude_structured(repair_prompt)
                raw_output_sha256 = _trace_output(
                    phase="repair_header_footer",
                    output_text=out,
                    duration_ms=duration_ms,
                )
            else:
                _trace_prompt(phase="repair_header_footer", prompt_text=repair_prompt)
                started = time.monotonic()
                out = llm.generate_text(repair_prompt, params=params)
                duration_ms = int((time.monotonic() - started) * 1000)
                raw_output_sha256 = _trace_output(
                    phase="repair_header_footer",
                    output_text=out,
                    duration_ms=duration_ms,
                )
                obj = funnel_ai._extract_json_object(out)
            assistant_message = funnel_ai._coerce_assistant_message(obj.get("assistantMessage") if isinstance(obj, dict) else None)
            puck_data_raw = funnel_ai._coerce_puck_data(obj.get("puckData") if isinstance(obj, dict) else None)
            puck_data = funnel_ai._sanitize_puck_data(puck_data_raw)
            puck_data["content"] = funnel_ai._sanitize_component_tree(puck_data.get("content"), allowed_types)
            zones = puck_data.get("zones")
            if isinstance(zones, dict):
                for key, value in list(zones.items()):
                    zones[key] = funnel_ai._sanitize_component_tree(value, allowed_types)
            funnel_ai._ensure_block_ids(puck_data)

        funnel_ai._inject_header_footer_if_missing(
            puck_data=puck_data,
            page_name=args.pageName,
            current_page_id=args.pageId,
            page_context=args.pageContext,
            wants_header=wants_header,
            wants_footer=wants_footer,
        )

        if not puck_data.get("content"):
            run_id = getattr(ctx, "run_id", None)
            tool_call_id = getattr(ctx, "tool_call_id", None)
            raw_puck_content = puck_data_raw.get("content") if isinstance(puck_data_raw, dict) else None
            raw_puck_content_count = len(raw_puck_content) if isinstance(raw_puck_content, list) else None
            sanitized_puck_content = puck_data.get("content")
            details = {
                "runId": run_id,
                "toolCallId": tool_call_id,
                "model": final_model,
                "templateMode": template_mode,
                "templateKind": template_kind,
                "templateComponentKind": template_component_kind,
                "compiledPromptSha256": compiled_prompt_sha256,
                "rawOutputSha256": raw_output_sha256,
                "rawPuckContentCount": raw_puck_content_count,
                "sanitizedPuckContentCount": len(sanitized_puck_content) if isinstance(sanitized_puck_content, list) else None,
                "allowedTypesCount": len(allowed_types),
            }
            raise RuntimeError(f"AI generation produced an empty page (no content). details={details}")

        ui_details = {
            "assistantMessage": assistant_message,
            "puckData": puck_data,
            "model": final_model,
            "attachmentSummaries": attachment_summaries,
            "compiledPromptSha256": compiled_prompt_sha256,
            "rawOutputSha256": raw_output_sha256,
        }
        llm_output = json.dumps({"assistantMessage": assistant_message, "model": final_model}, ensure_ascii=False)
        return ToolResult(llm_output=llm_output, ui_details=ui_details, attachments=[])


class DraftApplyOverridesArgs(BaseModel):
    model_config = ConfigDict(extra="forbid")

    orgId: str
    clientId: str
    funnelId: str
    pageId: str
    puckData: dict[str, Any]
    basePuckData: Optional[dict[str, Any]] = None
    templateKind: Optional[str] = None
    designSystemTokens: Optional[dict[str, Any]] = None
    brandLogoAssetPublicId: Optional[str] = None
    productId: str


class DraftApplyOverridesTool(BaseTool[DraftApplyOverridesArgs]):
    name = "draft.apply_overrides"
    ArgsModel = DraftApplyOverridesArgs

    def run(self, *, ctx: ToolContext, args: DraftApplyOverridesArgs) -> ToolResult:
        if args.orgId != ctx.org_id:
            raise ValueError("orgId mismatch")

        page = ctx.session.scalars(
            select(FunnelPage).where(FunnelPage.funnel_id == args.funnelId, FunnelPage.id == args.pageId)
        ).first()
        if not page:
            raise ValueError("Page not found")

        product = ctx.session.scalars(
            select(Product).where(Product.org_id == ctx.org_id, Product.client_id == args.clientId, Product.id == args.productId)
        ).first()
        if not product:
            raise ValueError("Product not found")

        base_puck_for_restore: dict[str, Any] | None = (
            args.basePuckData if isinstance(args.basePuckData, dict) else None
        )

        restored_sections = 0
        dropped_extra_sections = 0
        restored_testimonial_image_slots = 0
        checkout_purchase_ids_aligned = 0
        dropped_extra_section_summaries: list[dict[str, str]] = []
        if args.templateKind and base_puck_for_restore is not None:
            page_type: str | None = None
            if args.templateKind == "sales-pdp":
                page_type = "SalesPdpPage"
            elif args.templateKind == "pre-sales-listicle":
                page_type = "PreSalesPage"

            def _restore_pre_sales_review_image_slots(
                current_component: dict[str, Any], base_component: dict[str, Any]
            ) -> int:
                """
                Pre-sales testimonial media rendering requires 3 image slots per review slide.
                Restore missing/malformed slide image objects from the base template deterministically.
                """

                def _slides_for(component: dict[str, Any]) -> list[Any] | None:
                    comp_type = component.get("type")
                    props = component.get("props")
                    if not isinstance(props, dict):
                        return None
                    config = props.get("config")
                    if not isinstance(config, dict):
                        return None
                    if comp_type == "PreSalesReviews":
                        slides = config.get("slides")
                        return slides if isinstance(slides, list) else None
                    if comp_type == "PreSalesTemplate":
                        reviews = config.get("reviews")
                        if not isinstance(reviews, dict):
                            return None
                        slides = reviews.get("slides")
                        return slides if isinstance(slides, list) else None
                    return None

                cslides = _slides_for(current_component)
                bslides = _slides_for(base_component)
                if not isinstance(cslides, list) or not isinstance(bslides, list):
                    return 0

                restored_local = 0
                if len(cslides) < len(bslides):
                    for idx in range(len(cslides), len(bslides)):
                        base_slide = bslides[idx]
                        if not isinstance(base_slide, dict):
                            continue
                        cslides.append(deepcopy(base_slide))
                        base_images = base_slide.get("images")
                        if isinstance(base_images, list):
                            restored_local += min(3, len(base_images))

                for idx, base_slide in enumerate(bslides):
                    cur_slide = cslides[idx]
                    if not isinstance(base_slide, dict):
                        continue
                    if not isinstance(cur_slide, dict):
                        cslides[idx] = deepcopy(base_slide)
                        base_images = base_slide.get("images")
                        if isinstance(base_images, list):
                            restored_local += min(3, len(base_images))
                        continue

                    base_images = base_slide.get("images")
                    if not isinstance(base_images, list) or len(base_images) < 3:
                        continue

                    cur_images = cur_slide.get("images")
                    if not isinstance(cur_images, list):
                        cur_slide["images"] = deepcopy(base_images[:3])
                        restored_local += min(3, len(base_images))
                        continue

                    # Ensure the first 3 image slots exist and are valid objects.
                    for image_idx in range(3):
                        if image_idx >= len(base_images):
                            break
                        base_image = base_images[image_idx]
                        if not isinstance(base_image, dict):
                            continue
                        if image_idx >= len(cur_images):
                            cur_images.append(deepcopy(base_image))
                            restored_local += 1
                            continue
                        cur_image = cur_images[image_idx]
                        if not isinstance(cur_image, dict):
                            cur_images[image_idx] = deepcopy(base_image)
                            restored_local += 1
                            continue
                        alt = cur_image.get("alt")
                        if not isinstance(alt, str) or not alt.strip():
                            base_alt = base_image.get("alt")
                            if isinstance(base_alt, str) and base_alt.strip():
                                cur_image["alt"] = base_alt

                return restored_local

            def find_page(puck: dict[str, Any], type_name: str) -> Optional[dict[str, Any]]:
                content = puck.get("content")
                if not isinstance(content, list):
                    return None
                for item in content:
                    if isinstance(item, dict) and item.get("type") == type_name:
                        return item
                return None

            def _load_object_prop(
                props: dict[str, Any],
                *,
                object_key: str,
                json_key: str,
                label: str,
            ) -> tuple[dict[str, Any] | None, str | None]:
                raw_json = props.get(json_key)
                if isinstance(raw_json, str) and raw_json.strip():
                    try:
                        parsed = json.loads(raw_json)
                    except json.JSONDecodeError as exc:
                        raise ValueError(f"{label}.{json_key} must be valid JSON: {exc}") from exc
                    if not isinstance(parsed, dict):
                        raise ValueError(f"{label}.{json_key} must decode to a JSON object.")
                    return parsed, json_key
                value = props.get(object_key)
                if isinstance(value, dict):
                    return value, object_key
                return None, None

            def _persist_object_prop(
                props: dict[str, Any],
                *,
                source: str | None,
                object_key: str,
                json_key: str,
                value: dict[str, Any],
            ) -> None:
                if source == json_key:
                    props[json_key] = json.dumps(value, ensure_ascii=False)
                    return
                props[object_key] = value

            def _restore_sales_pdp_required_fields(candidate: dict[str, Any], base_child: dict[str, Any]) -> None:
                """
                Ensure template-required nested fields exist so the sales PDP renders correctly.
                We only fill missing pieces from the base template; we do not overwrite existing values.
                """

                if args.templateKind != "sales-pdp":
                    return
                if candidate.get("type") not in ("SalesPdpHero", "SalesPdpReviews"):
                    return
                cprops = candidate.get("props")
                bprops = base_child.get("props")
                if not isinstance(cprops, dict) or not isinstance(bprops, dict):
                    return

                if candidate.get("type") == "SalesPdpReviews":
                    base_cfg, _ = _load_object_prop(bprops, object_key="config", json_key="configJson", label="SalesPdpReviews")
                    if not isinstance(base_cfg, dict):
                        return
                    cur_cfg, cur_source = _load_object_prop(cprops, object_key="config", json_key="configJson", label="SalesPdpReviews")
                    if not isinstance(cur_cfg, dict):
                        cur_cfg = {}
                    if "id" not in cur_cfg and isinstance(base_cfg.get("id"), str):
                        cur_cfg["id"] = base_cfg["id"]
                    if "data" not in cur_cfg and isinstance(base_cfg.get("data"), dict):
                        cur_cfg["data"] = deepcopy(base_cfg["data"])
                    _persist_object_prop(cprops, source=cur_source, object_key="config", json_key="configJson", value=cur_cfg)
                    return

                # SalesPdpHero required fields: gallery.freeGifts + modals.
                base_cfg, _ = _load_object_prop(bprops, object_key="config", json_key="configJson", label="SalesPdpHero")
                cur_cfg, cur_cfg_source = _load_object_prop(cprops, object_key="config", json_key="configJson", label="SalesPdpHero")
                if not isinstance(base_cfg, dict) or not isinstance(cur_cfg, dict):
                    return

                base_gallery = base_cfg.get("gallery")
                cur_gallery = cur_cfg.get("gallery")
                if isinstance(base_gallery, dict):
                    if not isinstance(cur_gallery, dict):
                        cur_cfg["gallery"] = deepcopy(base_gallery)
                    else:
                        base_free = base_gallery.get("freeGifts")
                        cur_free = cur_gallery.get("freeGifts")
                        if isinstance(base_free, dict):
                            if not isinstance(cur_free, dict):
                                cur_gallery["freeGifts"] = deepcopy(base_free)
                            else:
                                # Fill missing/invalid keys.
                                if "icon" in base_free and not isinstance(cur_free.get("icon"), dict):
                                    cur_free["icon"] = deepcopy(base_free.get("icon"))
                                for key in ("title", "body", "ctaLabel"):
                                    if key in base_free and not isinstance(cur_free.get(key), str):
                                        cur_free[key] = base_free.get(key)

                _persist_object_prop(cprops, source=cur_cfg_source, object_key="config", json_key="configJson", value=cur_cfg)

                base_modals, _ = _load_object_prop(bprops, object_key="modals", json_key="modalsJson", label="SalesPdpHero")
                cur_modals, cur_modals_source = _load_object_prop(cprops, object_key="modals", json_key="modalsJson", label="SalesPdpHero")
                if isinstance(base_modals, dict):
                    if not isinstance(cur_modals, dict):
                        cur_modals = deepcopy(base_modals)
                    else:
                        for key in ("sizeChart", "whyBundle", "freeGifts"):
                            if key not in cur_modals and key in base_modals:
                                cur_modals[key] = deepcopy(base_modals[key])
                if isinstance(cur_modals, dict):
                    _persist_object_prop(
                        cprops,
                        source=cur_modals_source,
                        object_key="modals",
                        json_key="modalsJson",
                        value=cur_modals,
                    )

            def _coerce_pre_sales_hero_badges_to_list(component: dict[str, Any]) -> int:
                """
                The frontend expects PreSalesHero.config.badges to be an array.
                Some LLM outputs omit the key or set it null; coerce to [] deterministically.
                """

                if args.templateKind != "pre-sales-listicle":
                    return 0
                if component.get("type") != "PreSalesHero":
                    return 0
                props = component.get("props")
                if not isinstance(props, dict):
                    return 0
                cfg, cfg_source = _load_object_prop(
                    props,
                    object_key="config",
                    json_key="configJson",
                    label="PreSalesHero",
                )
                if not isinstance(cfg, dict):
                    return 0
                if isinstance(cfg.get("badges"), list):
                    return 0
                cfg["badges"] = []
                _persist_object_prop(
                    props,
                    source=cfg_source,
                    object_key="config",
                    json_key="configJson",
                    value=cfg,
                )
                return 1

            # Merge the current base page puckData with the latest template structure so new template
            # blocks (e.g. reviews/free gifts) are not lost when regenerating existing pages.
            template = get_funnel_template(args.templateKind)
            template_puck = template.puck_data if template else None
            if not isinstance(template_puck, dict):
                raise ValueError(f"Template {args.templateKind} puckData is missing or invalid.")
            base_puck_for_restore = deepcopy(base_puck_for_restore)
            upgraded_base_sections = 0
            dropped_upgraded_base_sections = 0

            if page_type:
                base_page = find_page(base_puck_for_restore, page_type)
                tmpl_page = find_page(template_puck, page_type)
                if tmpl_page is not None and base_page is None:
                    # If the stored base is missing the page root, reset to the template's page.
                    base_puck_for_restore["content"] = deepcopy(template_puck.get("content", []))
                    upgraded_base_sections = 1
                elif isinstance(base_page, dict) and isinstance(tmpl_page, dict):
                    base_props = base_page.get("props")
                    tmpl_props = tmpl_page.get("props")
                    if isinstance(base_props, dict) and isinstance(tmpl_props, dict):
                        tmpl_page_id = tmpl_props.get("id")
                        if isinstance(tmpl_page_id, str) and tmpl_page_id.strip():
                            base_props["id"] = tmpl_page_id
                        for key, value in tmpl_props.items():
                            if key == "content":
                                continue
                            if key not in base_props:
                                base_props[key] = deepcopy(value)

                        cur_children = base_props.get("content")
                        tmpl_children = tmpl_props.get("content")
                        if isinstance(cur_children, list) and isinstance(tmpl_children, list):
                            current_by_id: dict[str, dict[str, Any]] = {}
                            current_by_type: dict[str, list[dict[str, Any]]] = {}
                            for child in cur_children:
                                if not isinstance(child, dict):
                                    continue
                                ctype = child.get("type")
                                cprops = child.get("props")
                                cid = cprops.get("id") if isinstance(cprops, dict) else None
                                if isinstance(cid, str) and cid.strip() and cid not in current_by_id:
                                    current_by_id[cid] = child
                                if isinstance(ctype, str) and ctype:
                                    current_by_type.setdefault(ctype, []).append(child)

                            used_ids: set[str] = set()
                            merged: list[Any] = []
                            for tmpl_child in tmpl_children:
                                if not isinstance(tmpl_child, dict):
                                    merged.append(deepcopy(tmpl_child))
                                    continue
                                ttype = tmpl_child.get("type")
                                tprops = tmpl_child.get("props")
                                tid = tprops.get("id") if isinstance(tprops, dict) else None

                                candidate: dict[str, Any] | None = None
                                if isinstance(ttype, str) and ttype:
                                    if isinstance(tid, str) and tid.strip() and tid in current_by_id:
                                        by_id = current_by_id[tid]
                                        if isinstance(by_id, dict) and by_id.get("type") == ttype:
                                            candidate = by_id
                                    if candidate is None and current_by_type.get(ttype):
                                        candidate = current_by_type[ttype].pop(0)

                                if candidate is None:
                                    merged.append(deepcopy(tmpl_child))
                                    upgraded_base_sections += 1
                                    continue

                                cprops = candidate.get("props")
                                if isinstance(tid, str) and tid.strip() and isinstance(cprops, dict):
                                    cprops["id"] = tid
                                cid = cprops.get("id") if isinstance(cprops, dict) else None
                                if isinstance(cid, str) and cid.strip():
                                    used_ids.add(cid)

                                _restore_sales_pdp_required_fields(candidate, tmpl_child)
                                _coerce_pre_sales_hero_badges_to_list(candidate)

                                if args.templateKind == "pre-sales-listicle":
                                    restored_testimonial_image_slots += _restore_pre_sales_review_image_slots(
                                        candidate, tmpl_child
                                    )
                                merged.append(candidate)

                            for child in cur_children:
                                if not isinstance(child, dict):
                                    continue
                                cprops = child.get("props")
                                cid = cprops.get("id") if isinstance(cprops, dict) else None
                                if isinstance(cid, str) and cid.strip() and cid in used_ids:
                                    continue
                                dropped_upgraded_base_sections += 1

                            base_props["content"] = merged

            if page_type:
                cur_page = find_page(args.puckData, page_type)
                base_page = find_page(base_puck_for_restore, page_type)
                if base_page is not None and cur_page is None:
                    raise ValueError(f"Template page component {page_type} missing from generated puckData.")

                cur_props = cur_page.get("props") if isinstance(cur_page, dict) else None
                base_props = base_page.get("props") if isinstance(base_page, dict) else None
                if isinstance(cur_props, dict) and isinstance(base_props, dict):
                    base_page_id = base_props.get("id")
                    if isinstance(base_page_id, str) and base_page_id.strip():
                        cur_props["id"] = base_page_id

                    # Restore any missing page-level props (excluding the section slot).
                    for key, value in base_props.items():
                        if key == "content":
                            continue
                        if key not in cur_props:
                            cur_props[key] = deepcopy(value)

                    cur_children = cur_props.get("content")
                    base_children = base_props.get("content")
                    if isinstance(cur_children, list) and isinstance(base_children, list):
                        current_by_id: dict[str, dict[str, Any]] = {}
                        current_by_type: dict[str, list[dict[str, Any]]] = {}
                        for child in cur_children:
                            if not isinstance(child, dict):
                                continue
                            ctype = child.get("type")
                            cprops = child.get("props")
                            cid = cprops.get("id") if isinstance(cprops, dict) else None
                            if isinstance(cid, str) and cid.strip() and cid not in current_by_id:
                                current_by_id[cid] = child
                            if isinstance(ctype, str) and ctype:
                                current_by_type.setdefault(ctype, []).append(child)

                        used_ids: set[str] = set()
                        merged: list[Any] = []
                        for base_child in base_children:
                            if not isinstance(base_child, dict):
                                merged.append(deepcopy(base_child))
                                continue
                            btype = base_child.get("type")
                            bprops = base_child.get("props")
                            bid = bprops.get("id") if isinstance(bprops, dict) else None

                            candidate: dict[str, Any] | None = None
                            if isinstance(btype, str) and btype:
                                if isinstance(bid, str) and bid.strip() and bid in current_by_id:
                                    by_id = current_by_id[bid]
                                    if isinstance(by_id, dict) and by_id.get("type") == btype:
                                        candidate = by_id
                                if candidate is None and current_by_type.get(btype):
                                    candidate = current_by_type[btype].pop(0)

                            if candidate is None:
                                merged.append(deepcopy(base_child))
                                restored_sections += 1
                                continue

                            # Preserve template ids when we can match a base section.
                            cprops = candidate.get("props")
                            if isinstance(bid, str) and bid.strip() and isinstance(cprops, dict):
                                cprops["id"] = bid
                            cid = cprops.get("id") if isinstance(cprops, dict) else None
                            if isinstance(cid, str) and cid.strip():
                                used_ids.add(cid)

                            _restore_sales_pdp_required_fields(candidate, base_child)
                            _coerce_pre_sales_hero_badges_to_list(candidate)

                            if args.templateKind == "pre-sales-listicle":
                                restored_testimonial_image_slots += _restore_pre_sales_review_image_slots(
                                    candidate, base_child
                                )
                            merged.append(candidate)

                        # Drop any extra generated sections not present in the base template.
                        # Template mode should preserve structure; extra blocks are not allowed.
                        for child in cur_children:
                            if not isinstance(child, dict):
                                continue
                            cprops = child.get("props")
                            cid = cprops.get("id") if isinstance(cprops, dict) else None
                            if isinstance(cid, str) and cid.strip() and cid in used_ids:
                                continue
                            dropped_extra_sections += 1
                            if len(dropped_extra_section_summaries) < 10:
                                dropped_extra_section_summaries.append(
                                    {
                                        "type": str(child.get("type") or ""),
                                        "id": str(cid or ""),
                                    }
                                )

                        cur_props["content"] = merged

        config_contexts: list[funnel_ai._ConfigJsonContext] = []
        if args.templateKind:
            config_contexts = funnel_ai._collect_config_json_contexts_all(args.puckData)

        funnel_ai._apply_brand_logo_overrides_for_ai(
            session=ctx.session,
            org_id=ctx.org_id,
            client_id=args.clientId,
            puck_data=args.puckData,
            config_contexts=config_contexts,
            design_system_tokens=args.designSystemTokens,
        )

        funnel_ai._apply_product_image_overrides_for_ai(
            session=ctx.session,
            org_id=ctx.org_id,
            client_id=args.clientId,
            puck_data=args.puckData,
            config_contexts=config_contexts,
            template_kind=args.templateKind,
            product=product,
            brand_logo_public_id=args.brandLogoAssetPublicId,
        )
        if args.templateKind == "sales-pdp":
            funnel_ai._enforce_sales_pdp_guarantee_testimonial_only_images(
                puck_data=args.puckData,
                config_contexts=config_contexts,
            )
        funnel_ai._ensure_flat_vector_icon_prompts(
            puck_data=args.puckData,
            config_contexts=config_contexts,
            design_system_tokens=args.designSystemTokens if isinstance(args.designSystemTokens, dict) else None,
        )
        fallback_icon_puck = base_puck_for_restore if isinstance(base_puck_for_restore, dict) else None
        if args.templateKind == "pre-sales-listicle":
            funnel_ai._ensure_pre_sales_badge_icons(
                puck_data=args.puckData,
                config_contexts=config_contexts,
                fallback_puck_data=fallback_icon_puck,
            )
            funnel_ai._apply_icon_remix_overrides_for_ai(
                puck_data=args.puckData,
                config_contexts=config_contexts,
                fallback_puck_data=fallback_icon_puck,
                design_system_tokens=args.designSystemTokens if isinstance(args.designSystemTokens, dict) else None,
            )

        # Template pages often include image nodes inside config structures. The LLM occasionally deletes
        # src/iconSrc fields while leaving prompts empty, which makes image validation fail. Restore missing
        # non-placeholder src values from the base template puckData deterministically.
        restored = 0
        if base_puck_for_restore is not None:
            def set_src(target: dict[str, Any], *, asset_key: str, value: str) -> None:
                if asset_key == "iconAssetPublicId":
                    target["iconSrc"] = value
                elif asset_key == "posterAssetPublicId":
                    target["poster"] = value
                elif asset_key == "thumbAssetPublicId":
                    target["thumbSrc"] = value
                elif asset_key == "swatchAssetPublicId":
                    target["swatchImageSrc"] = value
                else:
                    target["src"] = value

            def restore_missing_src(current: Any, base: Any) -> int:
                # Restore src values only when the current node is missing src/prompt/assetPublicId and
                # the base node has a non-placeholder src. Use structural matching rather than absolute
                # JSON paths (LLM edits can reorder arrays, making path matching brittle).
                if isinstance(current, dict) and isinstance(base, dict):
                    if current.get("type") == "video" or funnel_ai._is_testimonial_image(current):
                        return 0

                    asset_key = funnel_ai._resolve_image_asset_key(current)
                    if asset_key:
                        if not current.get(asset_key):
                            prompt = current.get("prompt")
                            current_src = funnel_ai._get_image_src_for_asset_key(current, asset_key)
                            if not (isinstance(prompt, str) and prompt.strip()) and not (
                                isinstance(current_src, str) and current_src.strip()
                            ):
                                base_src = funnel_ai._get_image_src_for_asset_key(base, asset_key)
                                if isinstance(base_src, str) and base_src.strip() and not funnel_ai._is_placeholder_src(
                                    base_src
                                ):
                                    set_src(current, asset_key=asset_key, value=base_src)
                                    return 1 + sum(
                                        restore_missing_src(v, base.get(k)) for k, v in current.items() if k in base
                                    )

                    return sum(restore_missing_src(v, base.get(k)) for k, v in current.items() if k in base)

                if isinstance(current, list) and isinstance(base, list):
                    if not current or not base:
                        return 0

                    # Try to match objects by a stable key when possible (id/label/name/key),
                    # otherwise fall back to index-wise pairing.
                    match_field: str | None = None
                    for candidate in ("id", "label", "name", "key"):
                        if any(
                            isinstance(item, dict) and isinstance(item.get(candidate), str) and item.get(candidate).strip()
                            for item in current
                        ) and any(
                            isinstance(item, dict) and isinstance(item.get(candidate), str) and item.get(candidate).strip()
                            for item in base
                        ):
                            match_field = candidate
                            break

                    if match_field:
                        base_by: dict[str, Any] = {}
                        for item in base:
                            if not isinstance(item, dict):
                                continue
                            raw = item.get(match_field)
                            if isinstance(raw, str) and raw.strip() and raw.strip() not in base_by:
                                base_by[raw.strip()] = item

                        restored_local = 0
                        for item in current:
                            if not isinstance(item, dict):
                                continue
                            raw = item.get(match_field)
                            key = raw.strip() if isinstance(raw, str) else ""
                            if key and key in base_by:
                                restored_local += restore_missing_src(item, base_by[key])
                        if restored_local:
                            return restored_local

                    return sum(restore_missing_src(cur, base[idx]) for idx, cur in enumerate(current[: len(base)]))

                return 0

            restored = restore_missing_src(args.puckData, base_puck_for_restore)

        if args.templateKind == "sales-pdp":
            funnel = ctx.session.scalars(
                select(Funnel).where(Funnel.org_id == ctx.org_id, Funnel.id == args.funnelId)
            ).first()
            if not funnel:
                raise ValueError("Funnel not found")

            variants_query = select(ProductVariant).where(ProductVariant.product_id == product.id)
            if funnel.selected_offer_id:
                variants_query = variants_query.where(ProductVariant.offer_id == funnel.selected_offer_id)
            variants_query = variants_query.order_by(ProductVariant.price.asc(), ProductVariant.title.asc(), ProductVariant.id.asc())
            variants = list(ctx.session.scalars(variants_query).all())
            if not variants:
                raise ValueError(
                    "Checkout is not configured for this funnel product. No product variants were found."
                )

            def load_config(props: dict[str, Any], *, label: str) -> tuple[dict[str, Any], str]:
                raw = props.get("configJson")
                if isinstance(raw, str) and raw.strip():
                    try:
                        parsed = json.loads(raw)
                    except json.JSONDecodeError as exc:
                        raise ValueError(f"{label}.configJson must be valid JSON: {exc}") from exc
                    if not isinstance(parsed, dict):
                        raise ValueError(f"{label}.configJson must decode to a JSON object.")
                    return parsed, "configJson"
                cfg = props.get("config")
                if not isinstance(cfg, dict):
                    raise ValueError(f"{label} is missing config/configJson.")
                return cfg, "config"

            hero_props: dict[str, Any] | None = None
            for obj in funnel_ai.walk_json(args.puckData):
                if not isinstance(obj, dict) or obj.get("type") != "SalesPdpHero":
                    continue
                props = obj.get("props")
                if isinstance(props, dict):
                    hero_props = props
                    break
            if hero_props is None:
                raise ValueError("Checkout validation failed: SalesPdpHero block is missing from puckData.")

            hero_cfg, hero_cfg_source = load_config(hero_props, label="SalesPdpHero")
            purchase = hero_cfg.get("purchase")
            if not isinstance(purchase, dict):
                raise ValueError("Checkout validation failed: SalesPdpHero.config.purchase must be an object.")

            variant_inputs: list[dict[str, Any]] = []
            for variant in variants:
                variant_inputs.append(
                    {
                        "title": variant.title,
                        "amount_cents": variant.price,
                        "option_values": variant.option_values,
                    }
                )
            if funnel_ai._align_sales_pdp_purchase_options_to_variants(
                purchase=purchase,
                variants=variant_inputs,
            ):
                checkout_purchase_ids_aligned += 1
                if hero_cfg_source == "configJson":
                    hero_props["configJson"] = json.dumps(hero_cfg, ensure_ascii=False)
                else:
                    hero_props["config"] = hero_cfg

            def ids_from(options_path: list[str], *, label: str) -> list[str]:
                node: Any = purchase
                for key in options_path:
                    if not isinstance(node, dict):
                        raise ValueError(f"Checkout validation failed: {label} must be an object.")
                    node = node.get(key)
                if not isinstance(node, list) or not node:
                    raise ValueError(f"Checkout validation failed: {label} must be a non-empty list.")
                ids: list[str] = []
                for item in node:
                    if isinstance(item, dict) and isinstance(item.get("id"), str) and item["id"].strip():
                        ids.append(item["id"].strip())
                if not ids:
                    raise ValueError(f"Checkout validation failed: {label} contains no valid id values.")
                return ids

            size_ids = ids_from(["size", "options"], label="SalesPdpHero.purchase.size.options")
            color_ids = ids_from(["color", "options"], label="SalesPdpHero.purchase.color.options")
            offer_ids = ids_from(["offer", "options"], label="SalesPdpHero.purchase.offer.options")

            valid_sizes: set[str] = set()
            valid_colors: set[str] = set()
            valid_offers: set[str] = set()
            valid_selections: dict[tuple[str, str, str], str] = {}
            for variant in variants:
                option_values = variant.option_values
                if not isinstance(option_values, dict):
                    raise ValueError(
                        "Checkout is not configured for this funnel product. "
                        "Every product variant must include option_values (sizeId/colorId/offerId)."
                    )
                size_id = option_values.get("sizeId")
                color_id = option_values.get("colorId")
                offer_id = option_values.get("offerId")
                if not all(isinstance(v, str) and v.strip() for v in (size_id, color_id, offer_id)):
                    raise ValueError(
                        "Checkout is not configured for this funnel product. "
                        "Every product variant option_values must include non-empty sizeId/colorId/offerId strings."
                    )
                key = (size_id.strip(), color_id.strip(), offer_id.strip())
                if key in valid_selections:
                    raise ValueError(
                        "Checkout is not configured for this funnel product. "
                        "Duplicate variant option_values detected for selection="
                        + json.dumps({"sizeId": key[0], "colorId": key[1], "offerId": key[2]}, separators=(",", ":"))
                    )
                valid_selections[key] = str(variant.id)
                valid_sizes.add(key[0])
                valid_colors.add(key[1])
                valid_offers.add(key[2])

            invalid_size_ids = sorted({v for v in size_ids if v not in valid_sizes})
            invalid_color_ids = sorted({v for v in color_ids if v not in valid_colors})
            invalid_offer_ids = sorted({v for v in offer_ids if v not in valid_offers})
            if invalid_size_ids or invalid_color_ids or invalid_offer_ids:
                details: list[str] = []
                if invalid_size_ids:
                    details.append(
                        "sizeIds not present in product variants: " + ", ".join(invalid_size_ids)
                    )
                if invalid_color_ids:
                    details.append(
                        "colorIds not present in product variants: " + ", ".join(invalid_color_ids)
                    )
                if invalid_offer_ids:
                    details.append(
                        "offerIds not present in product variants: " + ", ".join(invalid_offer_ids)
                    )
                raise ValueError(
                    "Checkout validation failed: SalesPdpHero.purchase option ids do not match configured product variants. "
                    + "; ".join(details)
                )

            missing_combos: list[str] = []
            for size_id in size_ids:
                for color_id in color_ids:
                    for offer_id in offer_ids:
                        if (size_id, color_id, offer_id) not in valid_selections:
                            if len(missing_combos) < 12:
                                missing_combos.append(
                                    json.dumps(
                                        {"sizeId": size_id, "colorId": color_id, "offerId": offer_id},
                                        separators=(",", ":"),
                                    )
                                )
            if missing_combos:
                raise ValueError(
                    "Checkout validation failed: SalesPdpHero.purchase options include selections that do not map to any product variant. "
                    "Missing variants for selections: "
                    + ", ".join(missing_combos)
                )

        root_props = args.puckData.get("root", {}).get("props") if isinstance(args.puckData.get("root"), dict) else None
        if isinstance(root_props, dict):
            title = root_props.get("title")
            if not isinstance(title, str) or not title.strip():
                root_props["title"] = page.name
            desc = root_props.get("description")
            if not isinstance(desc, str):
                root_props["description"] = ""

        funnel_ai._sync_config_json_contexts(config_contexts)

        applied = ["brand_logo", "product_images", "icon_prompts"]
        if args.templateKind == "pre-sales-listicle":
            applied.extend(["pre_sales_badge_icons", "icon_remix"])
        if checkout_purchase_ids_aligned:
            applied.append("checkout_purchase_ids")
        if restored_sections:
            applied.append("restore_base_sections")
        if dropped_extra_sections:
            applied.append("drop_extra_sections")
        if restored_testimonial_image_slots:
            applied.append("restore_testimonial_image_slots")
        if restored:
            applied.append("restore_base_images")
        ui_details = {
            "puckData": args.puckData,
            "applied": applied,
            "restoredSectionCount": restored_sections,
            "droppedExtraSectionCount": dropped_extra_sections,
            "droppedExtraSectionSummaries": dropped_extra_section_summaries,
            "restoredTestimonialImageSlotCount": restored_testimonial_image_slots,
            "restoredImageCount": restored,
        }
        llm_output = json.dumps({"applied": ui_details["applied"]}, separators=(",", ":"))
        return ToolResult(llm_output=llm_output, ui_details=ui_details, attachments=[])


class DraftValidateArgs(BaseModel):
    model_config = ConfigDict(extra="forbid")

    orgId: str
    puckData: dict[str, Any]
    allowedTypes: list[str] = Field(default_factory=list)
    requiredTypes: list[str] = Field(default_factory=list)
    templateKind: Optional[str] = None
    pageIdSet: list[str] = Field(default_factory=list)
    validateTemplateImages: bool = False


class DraftValidateTool(BaseTool[DraftValidateArgs]):
    name = "draft.validate"
    ArgsModel = DraftValidateArgs

    def run(self, *, ctx: ToolContext, args: DraftValidateArgs) -> ToolResult:
        if args.orgId != ctx.org_id:
            raise ValueError("orgId mismatch")

        errors: list[str] = []
        warnings: list[str] = []

        # Template-specific config validation to prevent drafts that crash the frontend at runtime.
        if args.templateKind == "pre-sales-listicle":
            try:
                funnel_ai._validate_pre_sales_listicle_component_configs(args.puckData)
            except Exception as exc:  # noqa: BLE001
                errors.append(str(exc))
        if args.templateKind == "sales-pdp":
            try:
                funnel_ai._validate_sales_pdp_component_configs(args.puckData)
            except Exception as exc:  # noqa: BLE001
                errors.append(str(exc))

        allowed_set = set(args.allowedTypes or [])
        if allowed_set:
            unknown: set[str] = set()
            for obj in funnel_ai.walk_json(args.puckData):
                if not isinstance(obj, dict):
                    continue
                t = obj.get("type")
                # Only treat nodes that look like Puck components (type + props dict) as component types.
                props = obj.get("props")
                if isinstance(t, str) and t and isinstance(props, dict) and t not in allowed_set:
                    unknown.add(t)
            if unknown:
                errors.append(f"Unknown component types present: {', '.join(sorted(unknown))}")

        if args.requiredTypes:
            counts = funnel_ai._count_component_types(args.puckData)
            missing = [t for t in args.requiredTypes if counts.get(t, 0) == 0]
            if missing:
                errors.append(
                    "Required template components missing from puckData: " + ", ".join(sorted(missing))
                )

        # Internal links must resolve to valid page ids.
        if args.pageIdSet:
            page_ids = set(args.pageIdSet)
            for link in extract_internal_links(args.puckData):
                if link.to_page_id not in page_ids:
                    errors.append(f"Invalid internal link targetPageId: {link.to_page_id}")

        # Template image slots must have prompts/assets before image generation.
        if args.validateTemplateImages and args.templateKind:
            config_contexts = funnel_ai._collect_config_json_contexts_all(args.puckData)
            try:
                funnel_ai._validate_required_template_images(
                    puck_data=args.puckData,
                    config_contexts=config_contexts,
                )
            except Exception as exc:  # noqa: BLE001
                errors.append(str(exc))

        ok = not errors
        ui_details = {"ok": ok, "errors": errors, "warnings": warnings}
        llm_output = json.dumps(ui_details, separators=(",", ":"))
        return ToolResult(llm_output=llm_output, ui_details=ui_details, attachments=[])


class ImagesPlanArgs(BaseModel):
    model_config = ConfigDict(extra="forbid")

    orgId: str
    puckData: dict[str, Any]
    templateMode: bool = False
    templateKind: Optional[str] = None


class ImagesPlanTool(BaseTool[ImagesPlanArgs]):
    name = "images.plan"
    ArgsModel = ImagesPlanArgs

    def run(self, *, ctx: ToolContext, args: ImagesPlanArgs) -> ToolResult:
        if args.orgId != ctx.org_id:
            raise ValueError("orgId mismatch")
        config_contexts = funnel_ai._collect_config_json_contexts_all(args.puckData) if args.templateMode else []
        plans = funnel_ai._collect_image_plans(puck_data=args.puckData, config_contexts=config_contexts)
        if args.templateMode:
            plans = funnel_ai._ensure_unsplash_usage(
                plans,
                puck_data=args.puckData,
                config_contexts=config_contexts,
            )
        funnel_ai._sync_config_json_contexts(config_contexts)
        ui_details = {"imagePlans": plans, "puckData": args.puckData}
        llm_output = json.dumps({"imagePlanCount": len(plans)}, separators=(",", ":"))
        return ToolResult(llm_output=llm_output, ui_details=ui_details, attachments=[])


class ImagesGenerateArgs(BaseModel):
    model_config = ConfigDict(extra="forbid")

    orgId: str
    clientId: str
    funnelId: str
    productId: Optional[str] = None
    puckData: dict[str, Any]
    # Deprecated: kept for request compatibility. Generation now uses all required image targets
    # (up to funnel_ai._MAX_PAGE_IMAGE_GENERATIONS).
    maxImages: int = 3


class ImagesGenerateTool(BaseTool[ImagesGenerateArgs]):
    name = "images.generate"
    ArgsModel = ImagesGenerateArgs

    def run(self, *, ctx: ToolContext, args: ImagesGenerateArgs) -> ToolResult:
        if args.orgId != ctx.org_id:
            raise ValueError("orgId mismatch")

        generated_images: list[dict[str, Any]] = []
        config_contexts = funnel_ai._collect_config_json_contexts_all(args.puckData)
        image_plans = funnel_ai._collect_image_plans(puck_data=args.puckData, config_contexts=config_contexts)
        max_images = funnel_ai._resolve_image_generation_count(
            puck_data=args.puckData,
            image_plans=image_plans,
        )
        if max_images == 0:
            ui_details = {"generatedImages": [], "puckData": args.puckData, "maxImages": 0}
            return ToolResult(llm_output=json.dumps({"generated": 0, "maxImages": 0}), ui_details=ui_details, attachments=[])

        try:
            _, generated_images = funnel_ai._fill_ai_images(
                session=ctx.session,
                org_id=ctx.org_id,
                client_id=args.clientId,
                puck_data=args.puckData,
                max_images=max_images,
                funnel_id=args.funnelId,
                product_id=args.productId,
            )
        except Exception as exc:  # noqa: BLE001
            generated_images = [{"error": str(exc)}]

        ui_details = {"generatedImages": generated_images, "puckData": args.puckData, "maxImages": max_images}
        llm_output = json.dumps({"generated": len(generated_images), "maxImages": max_images}, separators=(",", ":"))
        return ToolResult(llm_output=llm_output, ui_details=ui_details, attachments=[])


class DraftPersistVersionArgs(BaseModel):
    model_config = ConfigDict(extra="forbid")

    orgId: str
    userId: str
    funnelId: str
    pageId: str
    prompt: str
    messages: list[dict[str, str]] = Field(default_factory=list)
    puckData: dict[str, Any]
    assistantMessage: str
    model: str
    temperature: float
    ideaWorkspaceId: Optional[str] = None
    templateId: Optional[str] = None
    attachmentSummaries: list[dict[str, Any]] = Field(default_factory=list)
    imagePlans: list[dict[str, Any]] = Field(default_factory=list)
    generatedImages: list[dict[str, Any]] = Field(default_factory=list)
    agentRunId: Optional[str] = None


class DraftPersistVersionTool(BaseTool[DraftPersistVersionArgs]):
    name = "draft.persist_version"
    ArgsModel = DraftPersistVersionArgs

    def run(self, *, ctx: ToolContext, args: DraftPersistVersionArgs) -> ToolResult:
        if args.orgId != ctx.org_id:
            raise ValueError("orgId mismatch")
        if args.userId != ctx.user_id:
            raise ValueError("userId mismatch")

        # Ensure page exists and belongs to funnel.
        page = ctx.session.scalars(
            select(FunnelPage).where(FunnelPage.funnel_id == args.funnelId, FunnelPage.id == args.pageId)
        ).first()
        if not page:
            raise ValueError("Page not found")

        page.review_status = FunnelPageReviewStatusEnum.review

        ai_metadata: dict[str, Any] = {
            "prompt": args.prompt,
            "messages": args.messages,
            "model": args.model,
            "temperature": args.temperature,
            "generatedAt": datetime.now(timezone.utc).isoformat(),
            "generatedImages": args.generatedImages,
            "imagePlans": args.imagePlans,
            "requestedImageCount": len(args.imagePlans),
            "appliedImageGenerationCap": funnel_ai._MAX_PAGE_IMAGE_GENERATIONS,
            "actorUserId": args.userId,
            "ideaWorkspaceId": args.ideaWorkspaceId,
            "templateId": args.templateId,
        }
        if args.agentRunId:
            ai_metadata["agentRunId"] = args.agentRunId
        if args.attachmentSummaries:
            ai_metadata["attachedAssets"] = args.attachmentSummaries

        version = FunnelPageVersion(
            page_id=page.id,
            status=FunnelPageVersionStatusEnum.draft,
            puck_data=args.puckData,
            source=FunnelPageVersionSourceEnum.ai,
            created_at=datetime.now(timezone.utc),
            ai_metadata=ai_metadata,
        )
        ctx.session.add(version)
        ctx.session.commit()
        ctx.session.refresh(version)

        ui_details = {"draftVersionId": str(version.id)}
        llm_output = json.dumps(ui_details, separators=(",", ":"))
        return ToolResult(llm_output=llm_output, ui_details=ui_details, attachments=[])


class TestimonialsGenerateAndApplyArgs(BaseModel):
    model_config = ConfigDict(extra="forbid")

    orgId: str
    userId: str
    funnelId: str
    pageId: str
    draftVersionId: Optional[str] = None
    currentPuckData: Optional[dict[str, Any]] = None
    templateId: Optional[str] = None
    ideaWorkspaceId: Optional[str] = None
    model: Optional[str] = None
    temperature: float = 0.3
    maxTokens: Optional[int] = None
    synthetic: bool = True
    agentRunId: Optional[str] = None


class TestimonialsGenerateAndApplyTool(BaseTool[TestimonialsGenerateAndApplyArgs]):
    name = "testimonials.generate_and_apply"
    ArgsModel = TestimonialsGenerateAndApplyArgs

    def run(self, *, ctx: ToolContext, args: TestimonialsGenerateAndApplyArgs) -> ToolResult:
        if args.orgId != ctx.org_id:
            raise ValueError("orgId mismatch")
        if args.userId != ctx.user_id:
            raise ValueError("userId mismatch")

        version, puck_data, generated = generate_funnel_page_testimonials(
            session=ctx.session,
            org_id=ctx.org_id,
            user_id=args.userId,
            funnel_id=args.funnelId,
            page_id=args.pageId,
            draft_version_id=args.draftVersionId,
            current_puck_data=args.currentPuckData,
            template_id=args.templateId,
            idea_workspace_id=args.ideaWorkspaceId,
            model=args.model,
            temperature=args.temperature,
            max_tokens=args.maxTokens,
            synthetic=args.synthetic,
        )

        # Attach agentRunId for traceability if requested.
        if args.agentRunId:
            if not isinstance(version.ai_metadata, dict):
                version.ai_metadata = {}
            version.ai_metadata["agentRunId"] = args.agentRunId
            ctx.session.add(version)
            ctx.session.commit()
            ctx.session.refresh(version)

        ui_details = {
            "draftVersionId": str(version.id),
            "puckData": puck_data,
            "generatedTestimonials": generated,
        }
        llm_output = json.dumps({"draftVersionId": str(version.id)}, separators=(",", ":"))
        return ToolResult(llm_output=llm_output, ui_details=ui_details, attachments=[])


class PublishValidateReadyArgs(BaseModel):
    model_config = ConfigDict(extra="forbid")

    orgId: str
    funnelId: str


class PublishValidateReadyTool(BaseTool[PublishValidateReadyArgs]):
    name = "publish.validate_ready"
    ArgsModel = PublishValidateReadyArgs

    def run(self, *, ctx: ToolContext, args: PublishValidateReadyArgs) -> ToolResult:
        if args.orgId != ctx.org_id:
            raise ValueError("orgId mismatch")

        funnel = ctx.session.scalars(
            select(Funnel).where(Funnel.org_id == ctx.org_id, Funnel.id == args.funnelId)
        ).first()
        if not funnel:
            raise ValueError("Funnel not found")

        pages = list(
            ctx.session.scalars(
                select(FunnelPage)
                .where(FunnelPage.funnel_id == args.funnelId)
                .order_by(FunnelPage.ordering.asc(), FunnelPage.created_at.asc())
            ).all()
        )
        page_id_set = {str(p.id) for p in pages}

        errors: list[str] = []
        warnings: list[str] = []
        pages_missing_version: list[dict[str, Any]] = []
        synthetic_pages: list[dict[str, Any]] = []
        broken_links: list[dict[str, Any]] = []

        if not pages:
            errors.append("Funnel has no pages.")

        if funnel.entry_page_id and str(funnel.entry_page_id) not in page_id_set:
            errors.append("Entry page does not belong to funnel.")
        if not funnel.entry_page_id:
            errors.append("Entry page not set.")

        for page in pages:
            draft = ctx.session.scalars(
                select(FunnelPageVersion)
                .where(
                    FunnelPageVersion.page_id == page.id,
                    FunnelPageVersion.status == FunnelPageVersionStatusEnum.draft,
                )
                .order_by(FunnelPageVersion.created_at.desc(), FunnelPageVersion.id.desc())
            ).first()
            approved = ctx.session.scalars(
                select(FunnelPageVersion)
                .where(
                    FunnelPageVersion.page_id == page.id,
                    FunnelPageVersion.status == FunnelPageVersionStatusEnum.approved,
                )
                .order_by(FunnelPageVersion.created_at.desc(), FunnelPageVersion.id.desc())
            ).first()
            version = draft or approved
            if not version:
                pages_missing_version.append({"pageId": str(page.id), "pageName": page.name})
                continue

            md = version.ai_metadata if isinstance(version.ai_metadata, dict) else {}
            is_synth = bool(md.get("kind") == "testimonial_generation" and md.get("synthetic") is True)
            prov = md.get("testimonialsProvenance")
            if isinstance(prov, dict) and prov.get("source") == "synthetic":
                is_synth = True
            if is_synth:
                synthetic_pages.append({"pageId": str(page.id), "pageName": page.name, "versionId": str(version.id)})

            for link in extract_internal_links(version.puck_data):
                if link.to_page_id not in page_id_set:
                    broken_links.append(
                        {
                            "fromPageId": str(page.id),
                            "fromPageName": page.name,
                            "toPageId": link.to_page_id,
                            "label": link.label,
                            "kind": link.kind,
                        }
                    )

            if page.next_page_id:
                next_id = str(page.next_page_id)
                if next_id == str(page.id):
                    broken_links.append(
                        {
                            "fromPageId": str(page.id),
                            "fromPageName": page.name,
                            "toPageId": next_id,
                            "kind": "auto",
                            "label": "Next page cannot reference itself",
                        }
                    )
                elif next_id not in page_id_set:
                    broken_links.append(
                        {
                            "fromPageId": str(page.id),
                            "fromPageName": page.name,
                            "toPageId": next_id,
                            "kind": "auto",
                            "label": "Next page does not belong to funnel",
                        }
                    )

        if pages_missing_version:
            errors.append(f"{len(pages_missing_version)} page(s) have no saved version.")
        if broken_links:
            errors.append(f"{len(broken_links)} broken internal link(s) detected.")
        if (
            settings.ENVIRONMENT.lower() in {"prod", "production"}
            and not settings.ALLOW_SYNTHETIC_TESTIMONIALS_IN_PRODUCTION
            and synthetic_pages
        ):
            errors.append(f"{len(synthetic_pages)} page(s) contain synthetic testimonials (blocked in production).")

        ok = not errors
        ui_details = {
            "ok": ok,
            "errors": errors,
            "warnings": warnings,
            "pagesMissingVersion": pages_missing_version,
            "pagesWithSyntheticTestimonials": synthetic_pages,
            "brokenInternalLinks": broken_links,
        }
        llm_output = json.dumps({"ok": ok}, separators=(",", ":"))
        return ToolResult(llm_output=llm_output, ui_details=ui_details, attachments=[])


class PublishExecuteArgs(BaseModel):
    model_config = ConfigDict(extra="forbid")

    orgId: str
    userId: str
    funnelId: str


class PublishExecuteTool(BaseTool[PublishExecuteArgs]):
    name = "publish.execute"
    ArgsModel = PublishExecuteArgs

    def run(self, *, ctx: ToolContext, args: PublishExecuteArgs) -> ToolResult:
        if args.orgId != ctx.org_id:
            raise ValueError("orgId mismatch")
        if args.userId != ctx.user_id:
            raise ValueError("userId mismatch")

        publication = publish_funnel(session=ctx.session, org_id=ctx.org_id, user_id=args.userId, funnel_id=args.funnelId)
        ui_details = {"publicationId": str(publication.id)}
        llm_output = json.dumps(ui_details, separators=(",", ":"))
        return ToolResult(llm_output=llm_output, ui_details=ui_details, attachments=[])
