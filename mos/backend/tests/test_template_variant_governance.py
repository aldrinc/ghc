"""Tests for template variant governance service."""

import pytest

from app.services.template_variant_governance import (
    AssetReference,
    AssetValidationError,
    GovernanceError,
    PuckDataStructureResult,
    StyleAuditResult,
    append_provenance_event,
    build_approval_provenance,
    build_convert_provenance,
    build_derive_provenance,
    compute_governance_report,
    extract_asset_references,
    make_provenance_event,
    validate_assets,
    validate_family_blocks,
    validate_puck_data_structure,
    validate_provenance_fields,
    validate_token_presence,
)


class TestExtractAssetReferences:
    """Tests for extracting asset references from puckData."""

    def test_extract_no_references(self):
        """Test puckData with no asset references."""
        puck_data = {
            "content": [
                {
                    "type": "SalesPdpPage",
                    "props": {
                        "content": [
                            {
                                "type": "SalesPdpHero",
                                "props": {
                                    "id": "hero_001",
                                    "config": {"title": "Test"},
                                },
                            }
                        ]
                    },
                }
            ]
        }

        references = extract_asset_references(puck_data)
        assert references == []

    def test_extract_asset_public_id(self):
        """Test extracting assetPublicId references."""
        puck_data = {
            "content": [
                {
                    "type": "SalesPdpPage",
                    "props": {
                        "content": [
                            {
                                "type": "SalesPdpHero",
                                "props": {
                                    "id": "hero_001",
                                    "config": {
                                        "gallery": {
                                            "slides": [
                                                {"assetPublicId": "asset-123"},
                                                {"assetPublicId": "asset-456"},
                                            ]
                                        }
                                    },
                                },
                            }
                        ]
                    },
                }
            ]
        }

        references = extract_asset_references(puck_data)
        assert len(references) == 2
        assert references[0].public_id == "asset-123"
        assert references[1].public_id == "asset-456"
        assert references[0].block_type == "SalesPdpHero"
        assert references[0].block_id == "hero_001"

    def test_extract_reference_asset_public_id(self):
        """Test extracting referenceAssetPublicId references."""
        puck_data = {
            "content": [
                {
                    "type": "SalesPdpPage",
                    "props": {
                        "content": [
                            {
                                "type": "SalesPdpReviewWall",
                                "props": {
                                    "id": "reviews_001",
                                    "config": {
                                        "tiles": [
                                            {"referenceAssetPublicId": "review-img-1"},
                                            {"referenceAssetPublicId": "review-img-2"},
                                        ]
                                    },
                                },
                            }
                        ]
                    },
                }
            ]
        }

        references = extract_asset_references(puck_data)
        assert len(references) == 2
        assert references[0].public_id == "review-img-1"
        assert references[1].public_id == "review-img-2"

    def test_extract_icon_asset_public_id(self):
        """Test extracting iconAssetPublicId references."""
        puck_data = {
            "content": [
                {
                    "type": "SalesPdpPage",
                    "props": {
                        "content": [
                            {
                                "type": "SalesPdpMarquee",
                                "props": {
                                    "id": "marquee_001",
                                    "config": {
                                        "items": [
                                            {"iconAssetPublicId": "icon-1"},
                                        ]
                                    },
                                },
                            }
                        ]
                    },
                }
            ]
        }

        references = extract_asset_references(puck_data)
        assert len(references) == 1
        assert references[0].public_id == "icon-1"

    def test_extract_poster_asset_public_id(self):
        """Test extracting posterAssetPublicId references."""
        puck_data = {
            "content": [
                {
                    "type": "SalesPdpPage",
                    "props": {
                        "content": [
                            {
                                "type": "SalesPdpHero",
                                "props": {
                                    "id": "hero_001",
                                    "config": {
                                        "gallery": {
                                            "slides": [
                                                {"posterAssetPublicId": "poster-1"},
                                            ]
                                        }
                                    },
                                },
                            }
                        ]
                    },
                }
            ]
        }

        references = extract_asset_references(puck_data)
        assert len(references) == 1
        assert references[0].public_id == "poster-1"

    def test_extract_multiple_reference_types(self):
        """Test extracting multiple types of asset references."""
        puck_data = {
            "content": [
                {
                    "type": "SalesPdpPage",
                    "props": {
                        "content": [
                            {
                                "type": "SalesPdpHero",
                                "props": {
                                    "id": "hero_001",
                                    "config": {
                                        "gallery": {
                                            "slides": [
                                                {"assetPublicId": "img-1"},
                                                {"posterAssetPublicId": "poster-1"},
                                            ]
                                        }
                                    },
                                },
                            },
                            {
                                "type": "SalesPdpMarquee",
                                "props": {
                                    "id": "marquee_001",
                                    "config": {
                                        "items": [
                                            {"iconAssetPublicId": "icon-1"},
                                        ]
                                    },
                                },
                            },
                        ]
                    },
                }
            ]
        }

        references = extract_asset_references(puck_data)
        assert len(references) == 3
        public_ids = {r.public_id for r in references}
        assert "img-1" in public_ids
        assert "poster-1" in public_ids
        assert "icon-1" in public_ids

    def test_extract_empty_string_ignored(self):
        """Test that empty string asset references are ignored."""
        puck_data = {
            "content": [
                {
                    "type": "SalesPdpPage",
                    "props": {
                        "content": [
                            {
                                "type": "SalesPdpHero",
                                "props": {
                                    "id": "hero_001",
                                    "config": {
                                        "gallery": {
                                            "slides": [
                                                {"assetPublicId": ""},
                                                {"assetPublicId": "valid-asset"},
                                            ]
                                        }
                                    },
                                },
                            }
                        ]
                    },
                }
            ]
        }

        references = extract_asset_references(puck_data)
        assert len(references) == 1
        assert references[0].public_id == "valid-asset"


class TestProvenanceEventHelpers:
    """Tests for provenance event helper functions."""

    def test_make_provenance_event(self):
        """Test creating a provenance event."""
        event = make_provenance_event(
            "convert",
            actor="user-123",
            metadata={"family": "sales-pdp"},
        )

        assert event["event_type"] == "convert"
        assert event["actor"] == "user-123"
        assert event["metadata"]["family"] == "sales-pdp"
        assert "timestamp" in event

    def test_make_provenance_event_minimal(self):
        """Test creating a provenance event with minimal args."""
        event = make_provenance_event("derive")

        assert event["event_type"] == "derive"
        assert event["actor"] is None
        assert event["metadata"] == {}
        assert "timestamp" in event

    def test_append_provenance_event(self):
        """Test appending an event to provenance."""
        provenance = {
            "source_type": "site_import",
            "source_url": "https://example.com",
        }

        updated = append_provenance_event(
            provenance,
            "convert",
            actor="user-123",
            metadata={"family": "sales-pdp"},
        )

        assert "events" in updated
        assert len(updated["events"]) == 1
        assert updated["events"][0]["event_type"] == "convert"
        assert updated["source_type"] == "site_import"

    def test_append_provenance_event_creates_events_list(self):
        """Test that events list is created if missing."""
        provenance = {"source_type": "site_import"}
        updated = append_provenance_event(provenance, "convert")

        assert "events" in updated
        assert isinstance(updated["events"], list)

    def test_append_provenance_event_preserves_existing_events(self):
        """Test that existing events are preserved."""
        provenance = {
            "source_type": "site_import",
            "events": [{"event_type": "convert", "timestamp": "2024-01-01"}],
        }

        updated = append_provenance_event(provenance, "derive")

        assert len(updated["events"]) == 2
        assert updated["events"][0]["event_type"] == "convert"
        assert updated["events"][1]["event_type"] == "derive"

    def test_build_convert_provenance(self):
        """Test building convert provenance."""
        synthesis = {
            "target_family": "sales-pdp",
            "target_page_type": "product_detail",
            "block_coverage": {"total_sections": 5},
        }

        provenance = build_convert_provenance(
            source_url="https://example.com",
            source_hostname="example.com",
            imported_at="2024-01-01T00:00:00Z",
            page_type_hint="product",
            synthesis=synthesis,
            actor="user-123",
        )

        assert provenance["source_type"] == "site_import"
        assert provenance["source_url"] == "https://example.com"
        assert provenance["source_hostname"] == "example.com"
        assert "events" in provenance
        assert provenance["events"][0]["event_type"] == "convert"

    def test_build_derive_provenance(self):
        """Test building derive provenance."""
        synthesized_puck_data = {"content": []}

        provenance = build_derive_provenance(
            parent_variant_id="parent-123",
            parent_variant_name="Parent Variant",
            mutation_preset_id="headline_hierarchy",
            mutation_preset_label="Headline Hierarchy",
            synthesized_puck_data=synthesized_puck_data,
            actor="user-123",
        )

        assert provenance["source_type"] == "variant_mutation"
        assert provenance["parent_variant_id"] == "parent-123"
        assert provenance["mutation_preset_id"] == "headline_hierarchy"
        assert "events" in provenance
        assert provenance["events"][0]["event_type"] == "derive"

    def test_build_derive_provenance_preserves_original_source(self):
        """Test that derive provenance preserves original source info."""
        original = {
            "source_type": "site_import",
            "source_url": "https://original.com",
            "synthesis": {"block_coverage": {"total_sections": 5}},
        }

        provenance = build_derive_provenance(
            parent_variant_id="parent-123",
            parent_variant_name="Parent",
            mutation_preset_id="headline_hierarchy",
            mutation_preset_label="Headline Hierarchy",
            synthesized_puck_data={},
            original_provenance=original,
        )

        assert provenance["original_source_type"] == "site_import"
        assert provenance["original_source_url"] == "https://original.com"
        assert provenance["synthesis"]["block_coverage"]["total_sections"] == 5

    def test_build_derive_provenance_preserves_earliest_original_source_for_chained_derives(self):
        """Chained derivations should keep the earliest original source metadata."""
        original = {
            "source_type": "variant_mutation",
            "source_url": "https://derived.example.com",
            "original_source_type": "site_import",
            "original_source_url": "https://original.com",
            "events": [{"event_type": "convert", "timestamp": "2024-01-01T00:00:00Z"}],
        }

        provenance = build_derive_provenance(
            parent_variant_id="parent-456",
            parent_variant_name="Derived Parent",
            mutation_preset_id="cta_emphasis",
            mutation_preset_label="CTA Emphasis",
            synthesized_puck_data={},
            original_provenance=original,
        )

        assert provenance["original_source_type"] == "site_import"
        assert provenance["original_source_url"] == "https://original.com"

    def test_build_approval_provenance(self):
        """Test building approval provenance."""
        provenance = {
            "source_type": "site_import",
            "events": [{"event_type": "convert", "timestamp": "2024-01-01"}],
        }

        updated = build_approval_provenance(
            provenance=provenance,
            actor="user-123",
        )

        assert len(updated["events"]) == 2
        assert updated["events"][1]["event_type"] == "approve"
        assert updated["events"][1]["actor"] == "user-123"


class TestValidatePuckDataStructure:
    """Tests for puckData structure validation."""

    def test_validate_valid_puck_data(self):
        """Test validating valid puckData."""
        puck_data = {
            "content": [
                {
                    "type": "SalesPdpPage",
                    "props": {"content": [{"type": "SalesPdpHero", "props": {"id": "hero_001"}}]},
                }
            ]
        }

        result = validate_puck_data_structure(puck_data)
        assert result.valid is True
        assert len(result.errors) == 0

    def test_validate_missing_content(self):
        """Test validating puckData without content."""
        puck_data = {"other": "data"}

        result = validate_puck_data_structure(puck_data)
        assert result.valid is False
        assert "missing required 'content' field" in result.errors[0]

    def test_validate_empty_content(self):
        """Test validating puckData with empty content."""
        puck_data = {"content": []}

        result = validate_puck_data_structure(puck_data)
        assert result.valid is True  # Empty is valid, just a warning
        assert len(result.warnings) > 0

    def test_validate_content_not_list(self):
        """Test validating puckData with non-list content."""
        puck_data = {"content": "not a list"}

        result = validate_puck_data_structure(puck_data)
        assert result.valid is False
        assert "must be a list" in result.errors[0]

    def test_validate_no_page_block(self):
        """Test validating puckData without Page block."""
        puck_data = {"content": [{"type": "SalesPdpHero", "props": {"id": "hero_001"}}]}

        result = validate_puck_data_structure(puck_data)
        assert result.valid is True  # No Page block is a warning, not error
        assert len(result.warnings) > 0

    def test_validate_none_puck_data(self):
        """Test validating None puckData."""
        result = validate_puck_data_structure(None)
        assert result.valid is False
        assert "No synthesized puckData" in result.errors[0]


class TestValidateAssets:
    """Tests for asset validation."""

    def test_validate_assets_empty_list(self):
        """Test validating empty asset list."""

        class MockAssetsRepo:
            pass

        results = validate_assets([], MockAssetsRepo(), "org-123")
        assert results == []

    def test_validate_assets_not_found(self):
        """Test validating asset that doesn't exist."""

        class MockAssetsRepo:
            def get_by_public_id(self, org_id, public_id, client_id=None):
                return None

        references = [
            AssetReference(
                public_id="missing-asset",
                field_path=["config", "src"],
                block_type="SalesPdpHero",
                block_id="hero_001",
            )
        ]

        results = validate_assets(references, MockAssetsRepo(), "org-123")
        assert len(results) == 1
        assert results[0].status == "not_found"
        assert results[0].public_id == "missing-asset"

    def test_validate_assets_approved(self):
        """Test validating approved asset."""
        from app.db.enums import AssetStatusEnum

        class MockAsset:
            def __init__(self, id, status):
                self.id = id
                self.status = status

        class MockAssetsRepo:
            def get_by_public_id(self, org_id, public_id, client_id=None):
                return MockAsset("asset-123", AssetStatusEnum.approved)

        references = [
            AssetReference(
                public_id="approved-asset",
                field_path=["config", "src"],
                block_type="SalesPdpHero",
                block_id="hero_001",
            )
        ]

        results = validate_assets(references, MockAssetsRepo(), "org-123")
        assert len(results) == 1
        assert results[0].status == "approved"
        assert results[0].asset_id == "asset-123"

    def test_validate_assets_qa_passed(self):
        """Test validating qa_passed asset (also acceptable for publish)."""
        from app.db.enums import AssetStatusEnum

        class MockAsset:
            def __init__(self, id, status):
                self.id = id
                self.status = status

        class MockAssetsRepo:
            def get_by_public_id(self, org_id, public_id, client_id=None):
                return MockAsset("asset-123", AssetStatusEnum.qa_passed)

        references = [
            AssetReference(
                public_id="qa-asset",
                field_path=["config", "src"],
                block_type="SalesPdpHero",
                block_id="hero_001",
            )
        ]

        results = validate_assets(references, MockAssetsRepo(), "org-123")
        assert len(results) == 1
        assert results[0].status == "approved"

    def test_validate_assets_rejected(self):
        """Test validating rejected asset."""
        from app.db.enums import AssetStatusEnum

        class MockAsset:
            def __init__(self, id, status):
                self.id = id
                self.status = status

        class MockAssetsRepo:
            def get_by_public_id(self, org_id, public_id, client_id=None):
                return MockAsset("asset-123", AssetStatusEnum.rejected)

        references = [
            AssetReference(
                public_id="rejected-asset",
                field_path=["config", "src"],
                block_type="SalesPdpHero",
                block_id="hero_001",
            )
        ]

        results = validate_assets(references, MockAssetsRepo(), "org-123")
        assert len(results) == 1
        assert results[0].status == "rejected"

    def test_validate_assets_pending(self):
        """Test validating pending asset."""
        from app.db.enums import AssetStatusEnum

        class MockAsset:
            def __init__(self, id, status):
                self.id = id
                self.status = status

        class MockAssetsRepo:
            def get_by_public_id(self, org_id, public_id, client_id=None):
                return MockAsset("asset-123", AssetStatusEnum.draft)

        references = [
            AssetReference(
                public_id="pending-asset",
                field_path=["config", "src"],
                block_type="SalesPdpHero",
                block_id="hero_001",
            )
        ]

        results = validate_assets(references, MockAssetsRepo(), "org-123")
        assert len(results) == 1
        assert results[0].status == "pending"


class TestComputeGovernanceReport:
    """Tests for computing governance reports."""

    def test_compute_report_no_puck_data(self):
        """Test computing report with no puckData."""

        class MockAssetsRepo:
            pass

        # Provide valid provenance with source_type
        provenance = {
            "source_type": "site_import",
            "source_url": "https://example.com",
            "events": [],
        }

        report = compute_governance_report(
            variant_id="variant-123",
            synthesized_puck_data=None,
            style_preset_id=None,
            style_preset_tokens=None,
            style_preset_name=None,
            provenance=provenance,
            assets_repo=MockAssetsRepo(),
            org_id="org-123",
            client_id="client-123",
        )

        assert report.variant_id == "variant-123"
        assert report.ready_for_publish is False
        assert len(report.blockers) > 0
        # Should have puckData blocker
        blocker_texts = " ".join(report.blockers)
        assert "No synthesized puckData" in blocker_texts

    def test_compute_report_valid_puck_data_no_assets(self):
        """Test computing report with valid puckData and no assets."""

        class MockAssetsRepo:
            pass

        puck_data = {
            "content": [
                {
                    "type": "SalesPdpPage",
                    "props": {
                        "content": [
                            {
                                "type": "SalesPdpHero",
                                "props": {"id": "hero_001", "config": {"title": "Test"}},
                            }
                        ]
                    },
                }
            ]
        }

        # Provide valid style preset tokens
        style_preset_tokens = {
            "palette": {"primary": "#000000", "background": "#FFFFFF"},
            "fonts": {"heading": "Arial", "body": "sans-serif"},
            "spacing": {"density": "comfortable"},
            "cta": {"style": "solid"},
        }

        # Provide valid provenance with source_type
        provenance = {
            "source_type": "site_import",
            "source_url": "https://example.com",
            "events": [],
        }

        report = compute_governance_report(
            variant_id="variant-123",
            synthesized_puck_data=puck_data,
            style_preset_id="preset-123",
            style_preset_tokens=style_preset_tokens,
            style_preset_name="Test Style",
            provenance=provenance,
            assets_repo=MockAssetsRepo(),
            org_id="org-123",
            client_id="client-123",
        )

        assert report.variant_id == "variant-123"
        # No assets referenced and valid style preset, so should be ready
        assert report.ready_for_publish is True
        assert len(report.blockers) == 0

    def test_compute_report_with_missing_assets(self):
        """Test computing report with missing assets."""

        class MockAssetsRepo:
            def get_by_public_id(self, org_id, public_id, client_id=None):
                return None

        puck_data = {
            "content": [
                {
                    "type": "SalesPdpPage",
                    "props": {
                        "content": [
                            {
                                "type": "SalesPdpHero",
                                "props": {
                                    "id": "hero_001",
                                    "config": {
                                        "gallery": {"slides": [{"assetPublicId": "missing-asset"}]}
                                    },
                                },
                            }
                        ]
                    },
                }
            ]
        }

        # Provide valid style preset tokens
        style_preset_tokens = {
            "palette": {"primary": "#000000", "background": "#FFFFFF"},
            "fonts": {"heading": "Arial", "body": "sans-serif"},
            "spacing": {"density": "comfortable"},
            "cta": {"style": "solid"},
        }

        # Provide valid provenance with source_type
        provenance = {
            "source_type": "site_import",
            "source_url": "https://example.com",
            "events": [],
        }

        report = compute_governance_report(
            variant_id="variant-123",
            synthesized_puck_data=puck_data,
            style_preset_id="preset-123",
            style_preset_tokens=style_preset_tokens,
            style_preset_name="Test Style",
            provenance=provenance,
            assets_repo=MockAssetsRepo(),
            org_id="org-123",
            client_id="client-123",
        )

        assert report.ready_for_publish is False
        assert len(report.blockers) > 0
        assert "not found" in report.blockers[0]

    def test_compute_report_reference_asset_blocks_even_when_approved(self):
        """referenceAssetPublicId must always block publish until replaced."""

        from app.db.enums import AssetStatusEnum

        class MockAsset:
            def __init__(self, id, status):
                self.id = id
                self.status = status

        class MockAssetsRepo:
            def get_by_public_id(self, org_id, public_id, client_id=None):
                return MockAsset("asset-123", AssetStatusEnum.approved)

        puck_data = {
            "content": [
                {
                    "type": "SalesPdpPage",
                    "props": {
                        "content": [
                            {
                                "type": "SalesPdpReviewWall",
                                "props": {
                                    "id": "reviews_001",
                                    "config": {"tiles": [{"referenceAssetPublicId": "ref-asset"}]},
                                },
                            }
                        ]
                    },
                }
            ]
        }

        style_preset_tokens = {
            "palette": {"primary": "#000000", "background": "#FFFFFF"},
            "fonts": {"heading": "Arial", "body": "sans-serif"},
            "spacing": {"density": "comfortable"},
            "cta": {"style": "solid"},
        }

        report = compute_governance_report(
            variant_id="variant-123",
            synthesized_puck_data=puck_data,
            style_preset_id="preset-123",
            style_preset_tokens=style_preset_tokens,
            style_preset_name="Test Style",
            provenance={"source_type": "site_import", "source_url": "https://example.com"},
            assets_repo=MockAssetsRepo(),
            org_id="org-123",
            client_id="client-123",
        )

        assert report.ready_for_publish is False
        assert any("referenceAssetPublicId" in blocker for blocker in report.blockers)

    def test_compute_report_with_provenance_events(self):
        """Test computing report includes provenance events."""

        class MockAssetsRepo:
            pass

        provenance = {
            "source_type": "site_import",
            "source_url": "https://example.com",
            "events": [
                {"event_type": "convert", "timestamp": "2024-01-01T00:00:00Z", "actor": "user-1"},
                {"event_type": "derive", "timestamp": "2024-01-02T00:00:00Z", "actor": "user-2"},
            ],
        }

        puck_data = {
            "content": [
                {
                    "type": "SalesPdpPage",
                    "props": {"content": []},
                }
            ]
        }

        # Provide valid style preset tokens
        style_preset_tokens = {
            "palette": {"primary": "#000000", "background": "#FFFFFF"},
            "fonts": {"heading": "Arial", "body": "sans-serif"},
            "spacing": {"density": "comfortable"},
            "cta": {"style": "solid"},
        }

        report = compute_governance_report(
            variant_id="variant-123",
            synthesized_puck_data=puck_data,
            style_preset_id="preset-123",
            style_preset_tokens=style_preset_tokens,
            style_preset_name="Test Style",
            provenance=provenance,
            assets_repo=MockAssetsRepo(),
            org_id="org-123",
            client_id="client-123",
        )

        assert len(report.provenance_events) == 2
        assert report.provenance_events[0]["event_type"] == "convert"
        assert report.provenance_events[1]["event_type"] == "derive"

    def test_compute_report_with_style_preset_tokens(self):
        """Test computing report with style preset tokens."""

        class MockAssetsRepo:
            pass

        puck_data = {
            "content": [
                {
                    "type": "SalesPdpPage",
                    "props": {"content": []},
                }
            ]
        }

        # Valid tokens
        style_preset_tokens = {
            "palette": {"primary": "#000000", "background": "#FFFFFF"},
            "fonts": {"heading": "Arial", "body": "sans-serif"},
            "spacing": {"density": "comfortable"},
            "cta": {"style": "solid"},
        }

        # Provide valid provenance with source_type
        provenance = {
            "source_type": "site_import",
            "source_url": "https://example.com",
            "events": [],
        }

        report = compute_governance_report(
            variant_id="variant-123",
            synthesized_puck_data=puck_data,
            style_preset_id="preset-123",
            style_preset_tokens=style_preset_tokens,
            style_preset_name="My Style",
            provenance=provenance,
            assets_repo=MockAssetsRepo(),
            org_id="org-123",
            client_id="client-123",
        )

        assert report.style_audit is not None
        assert report.style_audit.preset_id == "preset-123"
        assert report.style_audit.preset_name == "My Style"
        assert report.style_audit.passed is True

    def test_compute_report_with_invalid_style_preset_tokens(self):
        """Test computing report with invalid style preset tokens."""

        class MockAssetsRepo:
            pass

        puck_data = {
            "content": [
                {
                    "type": "SalesPdpPage",
                    "props": {"content": []},
                }
            ]
        }

        # Note: Empty tokens dict will be materialized with defaults from base template,
        # so it will pass validation. This test verifies the style audit runs correctly.
        style_preset_tokens = {}

        # Provide valid provenance with source_type
        provenance = {
            "source_type": "site_import",
            "source_url": "https://example.com",
            "events": [],
        }

        report = compute_governance_report(
            variant_id="variant-123",
            synthesized_puck_data=puck_data,
            style_preset_id="preset-123",
            style_preset_tokens=style_preset_tokens,
            style_preset_name="My Style",
            provenance=provenance,
            assets_repo=MockAssetsRepo(),
            org_id="org-123",
            client_id="client-123",
        )

        assert report.style_audit is not None
        # Empty tokens get materialized with defaults, so they pass
        assert report.style_audit.passed is True


class TestValidateProvenanceFields:
    """Tests for provenance field validation."""

    def test_validate_provenance_missing_source_type(self):
        """Test that missing source_type is an error."""
        provenance = {"source_url": "https://example.com"}
        errors = validate_provenance_fields(provenance)
        assert len(errors) == 1
        assert "source_type" in errors[0]

    def test_validate_provenance_missing_source_url_for_import(self):
        """Test that missing source_url for import is an error."""
        provenance = {"source_type": "site_import"}
        errors = validate_provenance_fields(provenance)
        assert len(errors) == 1
        assert "source_url" in errors[0]

    def test_validate_provenance_missing_parent_for_mutation(self):
        """Test that missing parent_variant_id for mutation is an error."""
        provenance = {"source_type": "variant_mutation"}
        errors = validate_provenance_fields(provenance)
        assert len(errors) == 1
        assert "parent_variant_id" in errors[0]

    def test_validate_provenance_valid_import(self):
        """Test that valid import provenance passes."""
        provenance = {
            "source_type": "site_import",
            "source_url": "https://example.com",
            "events": [],
        }
        errors = validate_provenance_fields(provenance)
        assert len(errors) == 0

    def test_validate_provenance_valid_mutation(self):
        """Test that valid mutation provenance passes."""
        provenance = {
            "source_type": "variant_mutation",
            "parent_variant_id": "parent-123",
            "original_source_url": "https://original.com",
            "events": [],
        }
        errors = validate_provenance_fields(provenance)
        assert len(errors) == 0

    def test_validate_provenance_none(self):
        """Test that None provenance is an error."""
        errors = validate_provenance_fields(None)
        assert len(errors) == 1
        assert "missing required provenance" in errors[0].lower()


class TestValidateTokenPresence:
    """Tests for token presence validation."""

    def test_validate_tokens_valid(self):
        """Test that valid tokens pass."""
        tokens = {
            "palette": {"primary": "#000"},
            "fonts": {"heading": "Arial"},
        }
        errors = validate_token_presence(tokens)
        assert len(errors) == 0

    def test_validate_tokens_missing_palette(self):
        """Test that missing palette is an error."""
        tokens = {"fonts": {"heading": "Arial"}}
        errors = validate_token_presence(tokens)
        assert len(errors) == 1
        assert "palette" in errors[0]

    def test_validate_tokens_missing_fonts(self):
        """Test that missing fonts is an error."""
        tokens = {"palette": {"primary": "#000"}}
        errors = validate_token_presence(tokens)
        assert len(errors) == 1
        assert "fonts" in errors[0]

    def test_validate_tokens_empty_palette(self):
        """Test that empty palette is an error."""
        tokens = {"palette": {}, "fonts": {"heading": "Arial"}}
        errors = validate_token_presence(tokens)
        assert len(errors) == 1
        assert "palette" in errors[0]

    def test_validate_tokens_none(self):
        """Test that None tokens is an error."""
        errors = validate_token_presence(None)
        assert len(errors) == 1
        assert "required" in errors[0].lower()


class TestValidateFamilyBlocks:
    """Tests for family-aligned block validation."""

    def test_validate_family_blocks_sales_pdp_missing_hero(self):
        """Test that missing SalesPdpHero is an error for sales-pdp."""
        puck_data = {
            "content": [
                {
                    "type": "SalesPdpPage",
                    "props": {
                        "content": [{"type": "SalesPdpMarquee", "props": {"id": "marquee_001"}}]
                    },
                }
            ]
        }
        errors, warnings = validate_family_blocks(puck_data, "sales-pdp")
        assert len(errors) == 1
        assert "SalesPdpHero" in errors[0]

    def test_validate_family_blocks_sales_pdp_valid(self):
        """Test that valid sales-pdp puckData passes."""
        puck_data = {
            "content": [
                {
                    "type": "SalesPdpPage",
                    "props": {
                        "content": [
                            {"type": "SalesPdpHero", "props": {"id": "hero_001"}},
                            {"type": "SalesPdpFooter", "props": {"id": "footer_001"}},
                        ]
                    },
                }
            ]
        }
        errors, warnings = validate_family_blocks(puck_data, "sales-pdp")
        assert len(errors) == 0

    def test_validate_family_blocks_presales_missing_hero(self):
        """Test that missing PreSalesHero is an error for pre-sales-listicle."""
        puck_data = {
            "content": [
                {
                    "type": "PreSalesPage",
                    "props": {"content": []},
                }
            ]
        }
        errors, warnings = validate_family_blocks(puck_data, "pre-sales-listicle")
        assert len(errors) == 1
        assert "PreSalesHero" in errors[0]

    def test_validate_family_blocks_unknown_family(self):
        """Test that unknown family has no specific block requirements."""
        puck_data = {"content": []}
        errors, warnings = validate_family_blocks(puck_data, "unknown-family")
        assert len(errors) == 0

    def test_validate_family_blocks_none_puck_data(self):
        """Test that None puckData has no errors."""
        errors, warnings = validate_family_blocks(None, "sales-pdp")
        assert len(errors) == 0
