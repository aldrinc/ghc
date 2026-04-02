from uuid import uuid4

import pytest

from app.config import settings
from app.db.models import SiteImport
from app.db.repositories.sites_runtime import SitesRuntimeRepository
from app.services.site_import_archive import rebuild_imported_template_puck_data
from app.services.site_templates import normalize_medusa_one_product_puck_data


@pytest.fixture(autouse=True)
def enable_llm_imported_section_translation(monkeypatch):
    monkeypatch.setattr(settings, "SITE_IMPORT_LLM_SOURCE_SECTION_TRANSLATION_ENABLED", True, raising=False)


def _imported_page_puck_data() -> dict:
    return {
        "root": {
            "props": {
                "title": "Imported source page",
                "description": "Imported runtime source",
            }
        },
        "content": [
            {
                "type": "ImportedPage",
                "props": {
                    "id": "imported-page-1",
                    "pageName": "Imported source page",
                    "pageType": "product_detail",
                    "renderMode": "source",
                    "sharedRuntimeSource": """
const GlobalHeader = () => (
  <header data-section-id="global-header">
    <a href="#shop">SHOP NOW</a>
    <a href="/">OMNI</a>
  </header>
);
const HeroSection = () => (
  <section data-section-id="hero-section">
    <span>SPRING SALE</span>
    <h1>Creatine For Body & Mind</h1>
    <p>Clinically dosed creatine gummies for strength, recovery, and focus.</p>
  </section>
);
const UsVsThem = () => {
  const rows = [
    { feature: "3g Creatine Monohydrate", omni: true, other: false, powder: true },
    { feature: "Travel Friendly", omni: true, other: true, powder: false },
  ];
  return (
    <section data-section-id="us-vs-them">
      <h2>Why Choose OMNI?</h2>
      <div>Benefits</div>
      <div>OMNI Gummies</div>
      <div>Creatine Powders</div>
      <div>Other Gummies</div>
      {rows.map((row) => (
        <div key={row.feature}>{row.feature}</div>
      ))}
    </section>
  );
};
const AnyLastQuestions = () => {
  const faqs = [
    { question: "How many gummies should I take daily?", answer: "We recommend taking 3-5 gummies daily." },
    { question: "Do I need to load creatine?", answer: "No, a loading phase is not necessary." },
  ];
  return <section data-section-id="any-last-questions">{faqs.length}</section>;
};
const ProductPurchaseSection = () => <section data-section-id="product-purchase-section">ADD TO CART -</section>;
const App = () => null;
globalThis.__mosImportedRuntimeComponents = { GlobalHeader, HeroSection, UsVsThem, AnyLastQuestions, ProductPurchaseSection, App };
const ImportedSection = App;
""",
                    "content": [
                        {
                            "type": "ImportedSection",
                            "props": {
                                "id": "imported-section-1",
                                "content": [
                                    {
                                        "type": "ImportedRuntimeSection",
                                        "props": {
                                            "id": "imported-runtime-1",
                                            "sectionLabel": "Imported source page",
                                            "componentName": "ProductPurchaseSection",
                                            "textOverrides": [],
                                            "imageOverrides": [],
                                            "buttonOverrides": [
                                                {
                                                    "key": "button-1",
                                                    "label": "Button 1",
                                                    "originalText": "ADD TO CART -",
                                                    "text": "ADD TO CART -",
                                                    "href": "",
                                                }
                                            ],
                                        },
                                    }
                                ],
                                "surface": "source",
                                "renderMode": "source",
                                "sectionKey": "productpurchasesection",
                                "displayName": "Imported source page",
                                "sectionType": "bundle_selector",
                                "sourceSectionId": "product-purchase-section",
                                "semanticTagsText": "bundle_selector, purchase, offers",
                            },
                        }
                    ],
                },
            }
        ],
        "zones": {},
    }


def _normalized_imported_sections() -> list[dict]:
    return [
        {
            "id": "global-header",
            "displayName": "Global Header",
            "sectionKey": "global-header",
            "sectionType": "generic_content",
            "semanticTags": ["header", "navigation"],
            "componentName": "GlobalHeader",
            "keyText": ["SHOP NOW", "OMNI", "#shop"],
            "parsedData": {
                "links": [
                    {"href": "#shop", "label": "SHOP NOW"},
                    {"href": "/", "label": "OMNI"},
                ],
                "buttonActions": [
                    {
                        "label": "SHOP NOW",
                        "href": "#shop",
                    }
                ],
            },
        },
        {
            "id": "hero-section",
            "displayName": "Hero Section",
            "sectionKey": "hero-section",
            "sectionType": "hero",
            "semanticTags": ["hero", "headline", "intro"],
            "componentName": "HeroSection",
            "keyText": [
                "SPRING SALE",
                "Creatine For Body & Mind",
                "Clinically dosed creatine gummies for strength, recovery, and focus.",
            ],
            "parsedData": {
                "badges": ["SPRING SALE"],
                "title": "Creatine For Body & Mind",
                "body": "Clinically dosed creatine gummies for strength, recovery, and focus.",
            },
        },
        {
            "id": "us-vs-them",
            "displayName": "Why Choose OMNI?",
            "sectionKey": "us-vs-them",
            "sectionType": "comparison_table",
            "semanticTags": ["comparison_table", "comparison"],
            "componentName": "UsVsThem",
            "keyText": [
                "Why Choose OMNI?",
                "3g Creatine Monohydrate",
                "Travel Friendly",
            ],
            "parsedData": {
                "title": "Why Choose OMNI?",
                "comparisons": [
                    {"feature": "3g Creatine Monohydrate", "omni": True, "other": False, "powder": True},
                    {"feature": "Travel Friendly", "omni": True, "other": True, "powder": False},
                ],
            },
        },
        {
            "id": "any-last-questions",
            "displayName": "Any Last Questions?",
            "sectionKey": "any-last-questions",
            "sectionType": "faq",
            "semanticTags": ["faq", "accordion"],
            "componentName": "AnyLastQuestions",
            "keyText": [
                "Any Last Questions?",
                "How many gummies should I take daily?",
            ],
            "parsedData": {
                "title": "Any Last Questions?",
                "body": "Everything you need to know before ordering.",
                "faqs": [
                    {
                        "question": "How many gummies should I take daily?",
                        "answer": "We recommend taking 3-5 gummies daily.",
                    },
                    {
                        "question": "Do I need to load creatine?",
                        "answer": "No, a loading phase is not necessary.",
                    },
                ],
            },
        },
        {
            "id": "product-purchase-section",
            "displayName": "Product Purchase Section",
            "sectionKey": "product-purchase-section",
            "sectionType": "bundle_selector",
            "semanticTags": ["bundle_selector", "purchase", "offers"],
            "componentName": "ProductPurchaseSection",
            "keyText": [
                "OMNI Creatine Gummy",
                "Choose flavor and bundle size.",
                "ADD TO CART -",
            ],
            "parsedData": {
                "title": "OMNI Creatine Gummy",
                "body": "Choose flavor and bundle size.",
                "buttonActions": [
                    {
                        "label": "ADD TO CART -",
                        "href": "",
                    }
                ],
                "tiers": [],
            },
        },
    ]


def _create_product(api_client, *, client_id: str, title: str) -> str:
    response = api_client.post(
        "/products",
        json={"clientId": client_id, "title": title},
    )
    assert response.status_code == 201, response.text
    return response.json()["id"]


def _create_variant(
    api_client,
    *,
    product_id: str,
    title: str,
    price: int,
    provider: str,
    external_price_id: str,
) -> str:
    response = api_client.post(
        f"/products/{product_id}/variants",
        json={
            "title": title,
            "price": price,
            "currency": "usd",
            "provider": provider,
            "externalPriceId": external_price_id,
        },
    )
    assert response.status_code == 201, response.text
    return response.json()["id"]


def test_rebuild_imported_template_puck_data_defaults_to_legacy_source_slots(monkeypatch):
    monkeypatch.setattr(settings, "SITE_IMPORT_LLM_SOURCE_SECTION_TRANSLATION_ENABLED", False, raising=False)

    def _unexpected_translate(**kwargs):
        raise AssertionError("LLM translation should not run when the source-section flag is disabled.")

    monkeypatch.setattr("app.services.site_import_archive.translate_imported_source_section", _unexpected_translate)

    puck_data = rebuild_imported_template_puck_data(
        title="Imported source page",
        description="Imported runtime source",
        page_type="product_detail",
        theme_candidate={},
        normalized_sections=_normalized_imported_sections(),
        runtime_source=_imported_page_puck_data()["content"][0]["props"]["sharedRuntimeSource"],
        head_assets={},
    )

    section_by_source_id = {
        section["props"]["sourceSectionId"]: section
        for section in puck_data["content"][0]["props"]["content"]
    }
    header_block = section_by_source_id["global-header"]["props"]["content"][0]["props"]
    assert header_block["textSlots"][0]["originalText"] == "OMNI"
    assert header_block["buttonSlots"][0]["originalText"] == "SHOP NOW"
    assert header_block["imageSlots"][0]["originalText"] == "OMNI"

    comparison_texts = {
        item["originalText"]
        for item in section_by_source_id["us-vs-them"]["props"]["content"][0]["props"]["textSlots"]
    }
    assert "Omni" in comparison_texts
    assert "Other" in comparison_texts
    assert "Powder" in comparison_texts
    assert "3g Creatine Monohydrate" in comparison_texts

    faq_texts = {
        item["originalText"]
        for item in section_by_source_id["any-last-questions"]["props"]["content"][0]["props"]["textSlots"]
    }
    assert "How many gummies should I take daily?" in faq_texts
    assert "We recommend taking 3-5 gummies daily." in faq_texts


@pytest.fixture(autouse=True)
def mock_imported_source_section_translation(monkeypatch):
    translations = {
        "global-header": {
            "blockType": "ImportedHeaderSection",
            "textSlots": [
                {"label": "Logo text", "originalText": "OMNI", "text": ""},
                {"label": "Link label 1", "originalText": "SHOP NOW", "text": ""},
            ],
            "buttonSlots": [
                {"label": "Button 1", "originalText": "SHOP NOW", "text": "", "href": "#shop"},
            ],
            "imageSlots": [
                {"label": "Logo image", "originalSrc": "", "originalText": "OMNI", "src": "", "alt": ""},
            ],
        },
        "hero-section": {
            "blockType": "ImportedHeroSection",
            "textSlots": [
                {"label": "Badge 1", "originalText": "SPRING SALE", "text": "SPRING SALE"},
                {
                    "label": "Headline",
                    "originalText": "Creatine For Body & Mind",
                    "text": "Creatine For Body & Mind",
                },
                {
                    "label": "Body copy",
                    "originalText": "Clinically dosed creatine gummies for strength, recovery, and focus.",
                    "text": "Clinically dosed creatine gummies for strength, recovery, and focus.",
                },
            ],
            "buttonSlots": [],
            "imageSlots": [],
        },
        "us-vs-them": {
            "blockType": "ImportedComparisonSection",
            "textSlots": [
                {
                    "label": "Column header 1",
                    "originalText": "Benefits",
                    "text": "",
                },
                {
                    "label": "Column header 2",
                    "originalText": "OMNI Gummies",
                    "text": "",
                },
                {
                    "label": "Column header 3",
                    "originalText": "Creatine Powders",
                    "text": "",
                },
                {
                    "label": "Column header 4",
                    "originalText": "Other Gummies",
                    "text": "",
                },
                {
                    "label": "Comparison row 1 feature",
                    "originalText": "3g Creatine Monohydrate",
                    "text": "",
                },
                {
                    "label": "Comparison row 2 feature",
                    "originalText": "Travel Friendly",
                    "text": "",
                },
            ],
            "buttonSlots": [],
            "imageSlots": [],
        },
        "any-last-questions": {
            "blockType": "ImportedFaqSection",
            "textSlots": [
                {
                    "label": "FAQ 1 question",
                    "originalText": "How many gummies should I take daily?",
                    "text": "How many gummies should I take daily?",
                },
                {
                    "label": "FAQ 1 answer",
                    "originalText": "We recommend taking 3-5 gummies daily.",
                    "text": "We recommend taking 3-5 gummies daily.",
                },
                {
                    "label": "FAQ 2 question",
                    "originalText": "Do I need to load creatine?",
                    "text": "Do I need to load creatine?",
                },
                {
                    "label": "FAQ 2 answer",
                    "originalText": "No, a loading phase is not necessary.",
                    "text": "No, a loading phase is not necessary.",
                },
            ],
            "buttonSlots": [],
            "imageSlots": [],
        },
    }

    def _mock_translate(**kwargs):
        section_id = kwargs["section_id"]
        if section_id not in translations:
            raise RuntimeError(f"Missing test translation for section_id={section_id}")
        return translations[section_id]

    monkeypatch.setattr("app.services.site_import_archive.translate_imported_source_section", _mock_translate)


def test_create_template_from_imported_site_and_instantiate_preserves_page_content(
    api_client,
    db_session,
    seed_data,
):
    client = seed_data["client"]
    runtime_repo = SitesRuntimeRepository(db_session)

    source_site = runtime_repo.create_site(
        org_id=str(client.org_id),
        client_id=str(client.id),
        name="OMNI Creatine Gummy",
        description="Imported OMNI page",
        site_type="ecommerce",
        site_family="sales-pdp",
        commerce_provider=None,
        route_slug="omni-creatine-gummy",
        theme_binding_mode="standalone",
    )

    source_page = runtime_repo.create_page(
        site_id=str(source_site.id),
        name="OMNI Creatine Gummy",
        slug="product-detail",
        page_type="product_detail",
        page_role="product_detail",
        ordering=0,
        adapted_puck_data=_imported_page_puck_data(),
    )
    runtime_repo.create_page_version(
        page_id=str(source_page.id),
        puck_data=_imported_page_puck_data(),
        provenance={"source_type": "test"},
        status="approved",
        source_type="site_import",
        source_id="test-import",
    )
    source_site.entry_page_id = str(source_page.id)

    site_import = SiteImport(
        id=str(uuid4()),
        org_id=client.org_id,
        client_id=client.id,
        source_url="archive://omni.zip",
        source_hostname="archive",
        input_mode="archive",
        status="completed",
        title="OMNI Creatine Gummy",
        suggested_template_family="imported-template",
        resolved_site_family="imported-template",
        resolved_page_type="product_detail",
        normalized_sections=_normalized_imported_sections(),
        saved_site_id=str(source_site.id),
    )
    db_session.add(site_import)
    db_session.flush()

    source_site.site_import_id = str(site_import.id)
    db_session.add(source_site)
    db_session.commit()

    create_template_response = api_client.post(
        f"/sites/{source_site.id}/create-template?clientId={client.id}",
        json={
            "name": "OMNI One Product Store",
            "description": "Workspace starter sourced from the imported Omni page",
        },
    )
    assert create_template_response.status_code == 201, create_template_response.text
    template_payload = create_template_response.json()
    assert template_payload["family"] == "imported-template"
    assert template_payload["pageCount"] == 17
    assert template_payload["commerceProvider"] == "medusa"

    product_id = _create_product(
        api_client,
        client_id=str(client.id),
        title="Ember: Brain Clarity Protocol",
    )
    _create_variant(
        api_client,
        product_id=product_id,
        title="Ember: Brain Clarity Protocol",
        price=4000,
        provider="medusa",
        external_price_id="variant_ember_test",
    )

    instantiate_response = api_client.post(
        f"/site-templates/{template_payload['id']}/instantiate",
        json={
            "clientId": str(client.id),
            "productId": product_id,
            "name": "OMNI One Product Instance",
            "description": "Instantiated from saved site template",
        },
    )
    assert instantiate_response.status_code == 201, instantiate_response.text
    instantiated_site_id = instantiate_response.json()["siteId"]

    instantiated_site_response = api_client.get(
        f"/sites/{instantiated_site_id}?clientId={client.id}"
    )
    assert instantiated_site_response.status_code == 200, instantiated_site_response.text
    instantiated_site = instantiated_site_response.json()
    assert instantiated_site["siteFamily"] == "imported-template"
    assert instantiated_site["commerceProvider"] == "medusa"
    assert len(instantiated_site["pages"]) == 17
    home_page = next(page for page in instantiated_site["pages"] if page["pageType"] == "home")
    assert home_page["slug"] == "home"
    assert any(page["pageType"] == "checkout" for page in instantiated_site["pages"])
    assert any(page["pageType"] == "contact_support" for page in instantiated_site["pages"])

    page_id = home_page["id"]
    page_response = api_client.get(
        f"/sites/{instantiated_site_id}/pages/{page_id}?clientId={client.id}"
    )
    assert page_response.status_code == 200, page_response.text
    page_payload = page_response.json()
    approved_puck_data = page_payload["latestApproved"]["puckData"]
    assert approved_puck_data["root"]["props"]["title"] == "Imported source page"
    assert approved_puck_data["content"][0]["type"] == "ImportedPage"
    assert approved_puck_data["content"][0]["props"]["renderMode"] == "source"

    section_by_source_id = {
        section["props"]["sourceSectionId"]: section
        for section in approved_puck_data["content"][0]["props"]["content"]
    }
    assert section_by_source_id["global-header"]["props"]["content"][0]["type"] == "ImportedHeaderSection"
    assert section_by_source_id["hero-section"]["props"]["content"][0]["type"] == "ImportedHeroSection"
    assert (
        section_by_source_id["product-purchase-section"]["props"]["content"][0]["type"]
        == "ImportedRuntimeSection"
    )
    header_block = section_by_source_id["global-header"]["props"]["content"][0]["props"]
    assert header_block["textSlots"][0]["originalText"] == "OMNI"
    assert header_block["textSlots"][0]["text"] == "OMNI"
    assert header_block["buttonSlots"][0]["text"] == "SHOP NOW"
    assert header_block["buttonSlots"][0]["href"] == "#product-purchase-section"
    assert header_block["imageSlots"][0]["label"] == "Logo image"
    assert header_block["imageSlots"][0]["originalText"] == "OMNI"
    assert header_block["imageSlots"][0]["alt"] == "OMNI"
    comparison_block = section_by_source_id["us-vs-them"]["props"]["content"][0]["props"]
    comparison_texts = {item["originalText"] for item in comparison_block["textSlots"]}
    comparison_values = {item["text"] for item in comparison_block["textSlots"]}
    assert "Benefits" in comparison_texts
    assert "OMNI Gummies" in comparison_texts
    assert "Creatine Powders" in comparison_texts
    assert "Other Gummies" in comparison_texts
    assert "3g Creatine Monohydrate" in comparison_texts
    assert "Travel Friendly" in comparison_texts
    assert "Benefits" in comparison_values
    assert "OMNI Gummies" in comparison_values
    faq_block = section_by_source_id["any-last-questions"]["props"]["content"][0]["props"]
    faq_texts = {item["originalText"] for item in faq_block["textSlots"]}
    assert "How many gummies should I take daily?" in faq_texts
    assert "We recommend taking 3-5 gummies daily." in faq_texts

    button_override = (
        section_by_source_id["product-purchase-section"]["props"]["content"][0]["props"]["buttonOverrides"][0]
    )
    purchase_block = section_by_source_id["product-purchase-section"]["props"]["content"][0]["props"]
    purchase_texts = {item["text"] for item in purchase_block["textOverrides"]}
    shared_runtime_source = approved_puck_data["content"][0]["props"]["sharedRuntimeSource"]
    assert "Ember: Brain Clarity Protocol" in purchase_texts
    assert "selectedVariantId" in shared_runtime_source
    assert 'ADD TO CART - {selectedVariant?.priceLabel || ""}' in shared_runtime_source
    assert 'priceLabel: "$40"' in shared_runtime_source
    assert button_override["text"] == "BUY NOW -"
    assert button_override["action"] == "medusa_buy_now"
    assert button_override["selectionStrategy"] == "omni_selected_tier"
    assert button_override["replaceCart"] is True
    assert purchase_block["sectionTargetId"] == "product-purchase-section"


def test_normalize_medusa_one_product_puck_data_rewrites_post_copy_cta_links():
    puck_data = _imported_page_puck_data()
    imported_page = puck_data["content"][0]["props"]
    purchase_button = imported_page["content"][0]["props"]["content"][0]["props"]["buttonOverrides"][0]
    purchase_button["action"] = "medusa_buy_now"
    imported_page["content"].insert(
        0,
        {
            "type": "ImportedSection",
            "props": {
                "sourceSectionId": "global-header",
                "displayName": "Global Header",
                "content": [
                    {
                        "type": "ImportedHeaderSection",
                        "props": {
                            "buttonSlots": [
                                {"text": "Get Your Handbook", "href": ""},
                                {"text": "Contact Support", "href": "#contact"},
                                {"text": "Log In", "href": "#login"},
                                {"text": "Home", "href": "/"},
                            ],
                        },
                    }
                ],
            },
        },
    )

    normalized = normalize_medusa_one_product_puck_data(puck_data)
    header_buttons = normalized["content"][0]["props"]["content"][0]["props"]["content"][0]["props"]["buttonSlots"]
    purchase_props = normalized["content"][0]["props"]["content"][1]["props"]["content"][0]["props"]

    assert header_buttons[0]["href"] == "#product-purchase-section"
    assert header_buttons[1]["href"] == "policies/contact-support"
    assert header_buttons[2]["href"] == "account"
    assert header_buttons[3]["href"] == "/"
    assert purchase_props["sectionTargetId"] == "product-purchase-section"
    assert purchase_props["buttonOverrides"][0]["href"] == ""
