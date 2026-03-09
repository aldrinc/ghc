from __future__ import annotations

from app.temporal.activities.strategy_v2_activities import (
    _VOC_AGENT01_COMPETITIVE_OVERLAP_SCHEMA,
    _VOC_AGENT01_OBSERVATION_SHEET_SCHEMA,
    _VOC_AGENT01_TREND_LIFECYCLE_SCHEMA,
    _normalize_agent00_handoff_output,
    _normalize_habitat_observations,
)


def _schema_default(field_schema: dict[str, object]) -> object:
    enum_values = field_schema.get("enum")
    if isinstance(enum_values, list) and enum_values:
        for value in enum_values:
            if value != "CANNOT_DETERMINE":
                return value
        return enum_values[0]
    field_type = field_schema.get("type")
    if field_type == "integer":
        return 0
    if field_type == "number":
        return 0
    if field_type == "array":
        return []
    if field_type == "object":
        return {}
    return "VALUE"


def _build_observation_sheet() -> dict[str, object]:
    properties = _VOC_AGENT01_OBSERVATION_SHEET_SCHEMA["properties"]
    required = _VOC_AGENT01_OBSERVATION_SHEET_SCHEMA["required"]
    assert isinstance(properties, dict)
    assert isinstance(required, list)
    return {
        field_name: _schema_default(properties[field_name])  # type: ignore[index]
        for field_name in required
    }


def _build_schema_object(schema: dict[str, object]) -> dict[str, object]:
    properties = schema["properties"]
    required = schema["required"]
    assert isinstance(properties, dict)
    assert isinstance(required, list)
    return {
        field_name: _schema_default(properties[field_name])  # type: ignore[index]
        for field_name in required
    }


def test_normalize_habitat_observations_derives_missing_mining_gate_reason() -> None:
    row = {
        "habitat_name": "reddit.com/r/herbalism",
        "habitat_type": "Reddit",
        "url_pattern": "https://www.reddit.com/r/herbalism/",
        "source_file": "practicaltools_apify-reddit-api_test.json",
        "items_in_file": 10,
        "data_quality": "MAJOR_ISSUES",
        "observation_sheet": _build_observation_sheet(),
        "language_samples": [],
        "video_extension": None,
        "competitive_overlap": _build_schema_object(_VOC_AGENT01_COMPETITIVE_OVERLAP_SCHEMA),
        "trend_lifecycle": _build_schema_object(_VOC_AGENT01_TREND_LIFECYCLE_SCHEMA),
        "mining_gate": {
            "status": "PASS",
            "failed_fields": [],
            # reason intentionally omitted to verify deterministic derivation.
        },
        "rank_score": 0,
        "estimated_yield": 0,
        "evidence_refs": ["/apify_output/raw_scraped_data/text_habitats/test.json::item[0]"],
    }

    normalized = _normalize_habitat_observations([row])

    assert len(normalized) == 1
    assert normalized[0]["mining_gate"]["reason"] == "Hard gate passed: all mining risk observables satisfied."


def test_normalize_habitat_observations_preserves_unknown_video_numeric_fields_as_null() -> None:
    row = {
        "habitat_name": "tiktok.com/@brand",
        "habitat_type": "Social_Video",
        "url_pattern": "https://www.tiktok.com/@brand",
        "source_file": "clockworks_tiktok-scraper_brand.json",
        "items_in_file": 24,
        "data_quality": "CLEAN",
        "observation_sheet": _build_observation_sheet(),
        "language_samples": [],
        "video_extension": {
            "video_count_scraped": "CANNOT_DETERMINE",
            "median_view_count": "CANNOT_DETERMINE",
            "viral_videos_found": "CANNOT_DETERMINE",
            "viral_video_count": "CANNOT_DETERMINE",
            "comment_sections_active": "Y",
            "comment_avg_length": "MEDIUM",
            "hook_formats_identifiable": "Y",
            "creator_diversity": "FEW",
            "contains_testimonial_language": "N",
            "contains_objection_language": "N",
            "contains_purchase_intent": "N",
        },
        "competitive_overlap": _build_schema_object(_VOC_AGENT01_COMPETITIVE_OVERLAP_SCHEMA),
        "trend_lifecycle": _build_schema_object(_VOC_AGENT01_TREND_LIFECYCLE_SCHEMA),
        "mining_gate": {
            "status": "PASS",
            "failed_fields": [],
            "reason": "Hard gate passed with available social-video evidence.",
        },
        "rank_score": 0,
        "estimated_yield": 0,
        "evidence_refs": ["/apify_output/raw_scraped_data/social_video/test.json::item[0]"],
    }

    normalized = _normalize_habitat_observations([row])

    assert len(normalized) == 1
    assert normalized[0]["video_count_scraped"] is None
    assert normalized[0]["median_view_count"] is None
    assert normalized[0]["viral_video_count"] is None


def test_normalize_habitat_observations_allows_nullable_video_numeric_fields_as_json_null() -> None:
    row = {
        "habitat_name": "social video habitat",
        "habitat_type": "Social_Video",
        "url_pattern": "https://www.tiktok.com/@brand",
        "source_file": "social_video_habitat.json",
        "items_in_file": 200,
        "data_quality": "CLEAN",
        "observation_sheet": _build_observation_sheet(),
        "language_samples": [],
        "video_extension": {
            "video_count_scraped": 200,
            "median_view_count": None,
            "viral_videos_found": "CANNOT_DETERMINE",
            "viral_video_count": None,
            "comment_sections_active": "CANNOT_DETERMINE",
            "comment_avg_length": "SHORT",
            "hook_formats_identifiable": "Y",
            "creator_diversity": "SINGLE",
            "contains_testimonial_language": "N",
            "contains_objection_language": "Y",
            "contains_purchase_intent": "Y",
        },
        "competitive_overlap": _build_schema_object(_VOC_AGENT01_COMPETITIVE_OVERLAP_SCHEMA),
        "trend_lifecycle": _build_schema_object(_VOC_AGENT01_TREND_LIFECYCLE_SCHEMA),
        "mining_gate": {
            "status": "PASS",
            "failed_fields": [],
            "reason": "Hard gate passed with available social-video evidence.",
        },
        "rank_score": 14,
        "estimated_yield": 0,
        "evidence_refs": ["/apify_output/raw_scraped_data/social_video/test.json::item[0]"],
    }

    normalized = _normalize_habitat_observations([row])

    assert len(normalized) == 1
    assert normalized[0]["video_count_scraped"] == 200
    assert normalized[0]["median_view_count"] is None
    assert normalized[0]["viral_video_count"] is None
    assert normalized[0]["comment_avg_length"] == "SHORT"
    assert normalized[0]["creator_diversity"] == "SINGLE"


def test_normalize_agent00_handoff_output_includes_target_id_and_config_id() -> None:
    raw_output = {
        "product_classification": {
            "buyer_behavior": "HIGH_TRUST",
        },
        "habitat_targets": [
            {
                "target_id": "HT-001",
                "habitat_name": "reddit.com/r/herbalism",
                "habitat_category": "Reddit",
                "apify_config_id": "T1-001",
                "manual_queries": [],
            },
            {
                "target_id": "HT-002",
                "habitat_name": "Goodreads herbal handbook reviews (discovery)",
                "habitat_category": "Review Sites",
                "apify_config_id": "T2-001",
                "manual_queries": ['"homeopathic first aid kit" site:goodreads.com herbal'],
            },
        ],
        "apify_configs": {
            "tier1_direct": [
                {
                    "config_id": "T1-001",
                    "actor_id": "practicaltools/apify-reddit-api",
                    "input": {
                        "startUrls": [{"url": "https://www.reddit.com/r/herbalism/"}],
                    },
                    "metadata": {
                        "target_id": "HT-001",
                    },
                }
            ],
            "tier2_discovery": [
                {
                    "config_id": "T2-001",
                    "actor_id": "apify/google-search-scraper",
                    "input": {
                        "queries": '"homeopathic first aid kit" site:goodreads.com herbal',
                    },
                    "metadata": {
                        "target_id": "HT-002",
                    },
                }
            ],
        },
    }

    normalized = _normalize_agent00_handoff_output(raw_output)
    habitats = normalized["strategy_habitats"]

    assert len(habitats) == 2
    by_config_id = {row["apify_config_id"]: row for row in habitats}

    assert by_config_id["T1-001"]["target_id"] == "HT-001"
    assert by_config_id["T1-001"]["url_pattern"] == "https://www.reddit.com/r/herbalism/"
    assert by_config_id["T2-001"]["target_id"] == "HT-002"
    assert by_config_id["T2-001"]["url_pattern"] == 'search://"homeopathic first aid kit" site:goodreads.com herbal'
