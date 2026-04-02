from app.services.site_import_archive import (
    _extract_translation_text_anchors,
    _sanitize_translated_source_backed_section,
    backfill_imported_runtime_override_slots,
    refresh_imported_page_copy_slots,
)


def _find_runtime_block(puck_data: dict, component_name: str) -> dict:
    sections = puck_data["content"][0]["props"]["content"]
    for section in sections:
        for block in section["props"]["content"]:
            if block["type"] == "ImportedRuntimeSection" and block["props"].get("componentName") == component_name:
                return block
    raise AssertionError(f"Runtime block {component_name} not found")


def test_backfill_imported_runtime_override_slots_exposes_hidden_section_copy():
    runtime_source = """
const UsVsThem = () => {
  const comparisons = [
    { feature: "3g Creatine Monohydrate", omni: true, powder: true, other: false },
    { feature: "No Chalky Texture", omni: true, powder: false, other: true },
  ];
  return (
    <section data-section-id="comparison">
      <h2>Why Choose OMNI?</h2>
      <div>TOP CHOICE</div>
      <div>OMNI Gummies</div>
      <div>Creatine Powders</div>
      <div>Other Gummies</div>
    </section>
  );
};

const ResultsStartWithEvidence = () => {
  const stats = [
    { percent: "77%", description: "Improvement After 4 Weeks" },
    { percent: "700+", description: "peer-reviewed clinical trials" },
  ];
  return (
    <section data-section-id="results">
      <h2>Results Start With Evidence</h2>
      <button>GET STARTED</button>
    </section>
  );
};

const AnyLastQuestions = () => {
  const faqs = [
    { question: "How many gummies should I take daily?", answer: "Take 3-5 gummies daily." },
  ];
  return (
    <section data-section-id="faq">
      <h2>Any Last Questions?</h2>
    </section>
  );
};

const App = () => (
  <main>
    <UsVsThem />
    <ResultsStartWithEvidence />
    <AnyLastQuestions />
  </main>
);
"""
    puck_data = {
        "root": {"props": {"title": "Test"}},
        "content": [
            {
                "type": "ImportedPage",
                "props": {
                    "id": "page",
                    "pageName": "Test",
                    "renderMode": "draft",
                    "sharedRuntimeSource": runtime_source,
                    "sharedHeadAssets": {},
                    "content": [
                        {
                            "type": "ImportedSection",
                            "props": {
                                "displayName": "Why Choose OMNI?",
                                "sourceSectionId": "comparison",
                                "sectionKey": "comparison",
                                "sectionType": "comparison_table",
                                "content": [
                                    {
                                        "type": "ImportedRuntimeSection",
                                        "props": {
                                            "componentName": "UsVsThem",
                                            "textOverrides": [
                                                {
                                                    "key": "text-1",
                                                    "label": "Headline",
                                                    "originalText": "Why Choose OMNI?",
                                                    "text": "Why Choose OMNI?",
                                                }
                                            ],
                                            "buttonOverrides": [],
                                            "imageOverrides": [],
                                        },
                                    }
                                ],
                            },
                        },
                        {
                            "type": "ImportedSection",
                            "props": {
                                "displayName": "Results Start With Evidence",
                                "sourceSectionId": "results",
                                "sectionKey": "results",
                                "sectionType": "generic_content",
                                "content": [
                                    {
                                        "type": "ImportedRuntimeSection",
                                        "props": {
                                            "componentName": "ResultsStartWithEvidence",
                                            "textOverrides": [],
                                            "buttonOverrides": [],
                                            "imageOverrides": [],
                                        },
                                    }
                                ],
                            },
                        },
                        {
                            "type": "ImportedSection",
                            "props": {
                                "displayName": "Any Last Questions?",
                                "sourceSectionId": "faq",
                                "sectionKey": "faq",
                                "sectionType": "faq",
                                "content": [
                                    {
                                        "type": "ImportedRuntimeSection",
                                        "props": {
                                            "componentName": "AnyLastQuestions",
                                            "textOverrides": [],
                                            "buttonOverrides": [],
                                            "imageOverrides": [],
                                        },
                                    }
                                ],
                            },
                        },
                    ],
                },
            }
        ],
        "zones": {},
    }

    enriched = backfill_imported_runtime_override_slots(puck_data)
    comparison_block = _find_runtime_block(enriched, "UsVsThem")
    comparison_texts = {
        item["originalText"] for item in comparison_block["props"]["textOverrides"]
    }
    assert "OMNI Gummies" in comparison_texts
    assert "Creatine Powders" in comparison_texts
    assert "Other Gummies" in comparison_texts
    assert "3g Creatine Monohydrate" in comparison_texts

    results_block = _find_runtime_block(enriched, "ResultsStartWithEvidence")
    results_texts = {
        item["originalText"] for item in results_block["props"]["textOverrides"]
    }
    assert "77%" in results_texts
    assert "Improvement After 4 Weeks" in results_texts
    assert "700+" in results_texts
    assert "peer-reviewed clinical trials" in results_texts
    results_buttons = {
        item["originalText"] for item in results_block["props"]["buttonOverrides"]
    }
    assert "GET STARTED" in results_buttons

    faq_block = _find_runtime_block(enriched, "AnyLastQuestions")
    faq_texts = {
        item["originalText"] for item in faq_block["props"]["textOverrides"]
    }
    assert "How many gummies should I take daily?" in faq_texts
    assert "Take 3-5 gummies daily." in faq_texts


def test_extract_translation_text_anchors_include_badges_quotes_and_chart_labels():
    section_source = """
const ResultsStartWithEvidence = () => {
  const chartData = [
    { label: "Endurance", omni: 85, placebo: 30 },
    { label: "Strength", omni: 92, placebo: 45 },
  ];
  return (
    <section data-section-id="results">
      <div><span>#1 TASTING CREATINE</span></div>
      <p>"OMNI Creatine provides a clinical dose of highly bioavailable creatine monohydrate in a format that people actually enjoy taking. It eliminates the digestive issues often associated with powders while delivering the proven cognitive and physical benefits."</p>
      <p>Neuroscientist</p>
      <div className="flex text-primary">debug</div>
    </section>
  );
};
"""

    anchors = _extract_translation_text_anchors(section_source=section_source)

    assert "#1 TASTING CREATINE" in anchors
    assert "Endurance" in anchors
    assert "Strength" in anchors
    assert (
        '"OMNI Creatine provides a clinical dose of highly bioavailable creatine monohydrate in a format that '
        "people actually enjoy taking. It eliminates the digestive issues often associated with powders while "
        'delivering the proven cognitive and physical benefits."'
    ) in anchors
    assert "Neuroscientist" in anchors
    assert "flex text-primary" not in anchors


def test_sanitize_translated_source_backed_section_splits_composite_text_anchors():
    translation = {
        "blockType": "ImportedHeroSection",
        "textSlots": [
            {
                "label": "Proof text",
                "originalText": "4.8 Rating | 35,000+ Orders Delivered",
                "text": "4.8 Rating | 35,000+ Orders Delivered",
            }
        ],
        "buttonSlots": [],
        "imageSlots": [],
    }

    sanitized = _sanitize_translated_source_backed_section(
        translation=translation,
        available_text_anchors=[
            "4.8 Rating | 35,000+",
            "Orders Delivered",
        ],
        available_button_anchors=[],
        available_image_anchors=[],
    )

    assert sanitized["textSlots"] == [
        {
            "label": "Proof text part 1 of 2",
            "originalText": "4.8 Rating | 35,000+",
            "text": "4.8 Rating | 35,000+",
        },
        {
            "label": "Proof text part 2 of 2",
            "originalText": "Orders Delivered",
            "text": "Orders Delivered",
        },
    ]


def test_backfill_imported_runtime_override_slots_keeps_purchase_copy_clean():
    runtime_source = """
const ProductPurchaseSection = () => {
  return (
    <section data-section-id="product-purchase-section">
      <h2>OMNI Creatine Gummy</h2>
      <div className="flex text-primary">debug</div>
      <button>Watermelon</button>
      <button>Peach</button>
      <button>ADD TO CART -</button>
    </section>
  );
};

const App = () => (
  <main>
    <ProductPurchaseSection />
  </main>
);
"""
    puck_data = {
        "root": {"props": {"title": "Test"}},
        "content": [
            {
                "type": "ImportedPage",
                "props": {
                    "id": "page",
                    "pageName": "Test",
                    "renderMode": "draft",
                    "sharedRuntimeSource": runtime_source,
                    "sharedHeadAssets": {},
                    "content": [
                        {
                            "type": "ImportedSection",
                            "props": {
                                "displayName": "OMNI Creatine Gummy",
                                "sourceSectionId": "product-purchase-section",
                                "sectionKey": "product-purchase-section",
                                "sectionType": "bundle_selector",
                                "content": [
                                    {
                                        "type": "ImportedRuntimeSection",
                                        "props": {
                                            "componentName": "ProductPurchaseSection",
                                            "textOverrides": [],
                                            "buttonOverrides": [],
                                            "imageOverrides": [],
                                        },
                                    }
                                ],
                            },
                        }
                    ],
                },
            }
        ],
        "zones": {},
    }

    enriched = backfill_imported_runtime_override_slots(puck_data)
    purchase_block = _find_runtime_block(enriched, "ProductPurchaseSection")
    purchase_texts = {
        item["originalText"] for item in purchase_block["props"]["textOverrides"]
    }
    purchase_buttons = {
        item["originalText"] for item in purchase_block["props"]["buttonOverrides"]
    }

    assert "OMNI Creatine Gummy" in purchase_texts
    assert "flex text-primary" not in purchase_texts
    assert "Watermelon" in purchase_buttons
    assert "Peach" in purchase_buttons
    assert "ADD TO CART -" in purchase_buttons


def test_refresh_imported_page_copy_slots_preserves_existing_translated_values(monkeypatch):
    runtime_source = """
const OptimizeYourRoutine = () => {
  return (
    <section data-section-id="optimize-your-routine">
      <div><span>#1 TASTING CREATINE</span></div>
      <h2>Optimize Your Routine</h2>
      <p>Creatine supports how your cells create and reuse energy.</p>
    </section>
  );
};

const App = () => (
  <main>
    <OptimizeYourRoutine />
  </main>
);
"""
    puck_data = {
        "root": {"props": {"title": "Test"}},
        "content": [
            {
                "type": "ImportedPage",
                "props": {
                    "id": "page",
                    "pageName": "Test",
                    "renderMode": "draft",
                    "sharedRuntimeSource": runtime_source,
                    "sharedHeadAssets": {},
                    "content": [
                        {
                            "type": "ImportedSection",
                            "props": {
                                "displayName": "Optimize Your Routine",
                                "sourceSectionId": "optimize-your-routine",
                                "sectionKey": "optimize-your-routine",
                                "sectionType": "feature_stack",
                                "content": [
                                    {
                                        "type": "ImportedFeatureSection",
                                        "props": {
                                            "id": "feature-block",
                                            "sectionLabel": "Optimize Your Routine",
                                            "componentName": "OptimizeYourRoutine",
                                            "textSlots": [
                                                {
                                                    "label": "Headline",
                                                    "originalText": "Optimize Your Routine",
                                                    "text": "Use Herbs With More Confidence",
                                                }
                                            ],
                                            "buttonSlots": [],
                                            "imageSlots": [],
                                        },
                                    }
                                ],
                            },
                        }
                    ],
                },
            }
        ],
        "zones": {},
    }

    def _mock_translate(**kwargs):
        assert "#1 TASTING CREATINE" in kwargs["available_text_anchors"]
        return {
            "blockType": "ImportedFeatureSection",
            "textSlots": [
                {
                    "label": "Badge",
                    "originalText": "#1 TASTING CREATINE",
                    "text": "#1 TASTING CREATINE",
                },
                {
                    "label": "Headline",
                    "originalText": "Optimize Your Routine",
                    "text": "Optimize Your Routine",
                },
            ],
            "buttonSlots": [],
            "imageSlots": [],
        }

    monkeypatch.setattr("app.services.site_import_archive.translate_imported_source_section", _mock_translate)

    refreshed = refresh_imported_page_copy_slots(puck_data)
    feature_block = refreshed["content"][0]["props"]["content"][0]["props"]["content"][0]
    text_slots = feature_block["props"]["textSlots"]

    assert text_slots[0]["originalText"] == "#1 TASTING CREATINE"
    assert text_slots[0]["text"] == "#1 TASTING CREATINE"
    assert text_slots[1]["originalText"] == "Optimize Your Routine"
    assert text_slots[1]["text"] == "Use Herbs With More Confidence"
