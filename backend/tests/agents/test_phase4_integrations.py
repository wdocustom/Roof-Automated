"""Tests for Phase 4: Deep Physical-World Integrations.

Covers:
  - EagleView/Hover measurement parsing and provider selection
  - Drone survey request logic and report parsing
  - Supplier price feed parsing and threshold logic
  - Advanced vision QC summary aggregation
  - Customer preview scope generation
  - Change order and measurement event types
  - Measurement service project updates
"""

from unittest.mock import AsyncMock, patch

import pytest

from app.agents.events import EventType
from app.integrations.drone.client import (
    DroneService,
    DroneSurveyRequest,
    SurveyPriority,
    SurveyStatus,
    should_request_drone_survey,
)
from app.integrations.eagleview.client import (
    EagleViewProvider,
    HoverProvider,
    MeasurementOrderStatus,
    MeasurementService,
    MeasurementSource,
    PropertyMeasurement,
    RoofFacet,
    _mock_eagleview_measurement,
)
from app.integrations.supplier.price_feed import (
    PriceUpdate,
    SupplierName,
    SupplierPriceFeed,
)


# ---------------------------------------------------------------------------
# EagleView / Hover
# ---------------------------------------------------------------------------

class TestEagleViewProvider:
    @pytest.mark.asyncio
    async def test_parse_report_extracts_facets(self):
        provider = EagleViewProvider()
        report = {
            "address": "123 Oak St",
            "report_id": "ev-001",
            "roof": {
                "total_area_sqft": 2000,
                "predominant_pitch": "6/12",
                "steepest_pitch": "8/12",
                "facets": [
                    {"id": "f1", "area_sqft": 800, "pitch": "6/12", "pitch_degrees": 26.6},
                    {"id": "f2", "area_sqft": 700, "pitch": "6/12", "pitch_degrees": 26.6},
                    {"id": "f3", "area_sqft": 500, "pitch": "8/12", "pitch_degrees": 33.7},
                ],
                "ridge_length_ft": 42,
                "valley_length_ft": 20,
                "eave_length_ft": 155,
            },
            "structure": {"stories": 2, "height_ft": 22},
        }
        m = await provider.parse_report(report)
        assert m.total_roof_sqft == 2000
        assert m.total_roof_squares == 20.0
        assert m.num_facets == 3
        assert len(m.roof_facets) == 3
        assert m.predominant_pitch == "6/12"
        assert m.confidence == 0.98
        assert m.source == MeasurementSource.EAGLEVIEW

    @pytest.mark.asyncio
    async def test_order_report_without_api_key_returns_mock(self):
        provider = EagleViewProvider(api_key="", api_secret="")
        order = await provider.order_report("123 Main St", project_id="p-1")
        assert order.order_id == "mock-ev-order"
        assert order.status == MeasurementOrderStatus.PENDING

    def test_mock_measurement_is_realistic(self):
        m = _mock_eagleview_measurement("456 Elm St")
        assert m.total_roof_sqft == 1850.0
        assert m.num_facets == 4
        assert len(m.roof_facets) == 4
        assert m.ridge_length_ft > 0
        assert m.eave_length_ft > 0


class TestHoverProvider:
    @pytest.mark.asyncio
    async def test_parse_report(self):
        provider = HoverProvider()
        report = {
            "address": "789 Pine St",
            "job_id": "hover-001",
            "measurements": {
                "roof_area_sqft": 1600,
                "roof_pitch": "5/12",
                "exterior_wall_area_sqft": 1800,
                "perimeter_ft": 160,
                "stories": 1,
            },
        }
        m = await provider.parse_report(report)
        assert m.total_roof_sqft == 1600
        assert m.total_roof_squares == 16.0
        assert m.siding_sqft == 1800
        assert m.confidence == 0.95
        assert m.source == MeasurementSource.HOVER


class TestMeasurementService:
    @pytest.mark.asyncio
    async def test_falls_back_to_mock_when_unconfigured(self):
        service = MeasurementService()
        m = await service.get_best_measurement("100 Test Dr")
        assert m.total_roof_sqft > 0
        assert m.source == MeasurementSource.EAGLEVIEW  # Mock returns EagleView


# ---------------------------------------------------------------------------
# Drone Survey
# ---------------------------------------------------------------------------

class TestDroneSurvey:
    def test_should_request_for_very_complex_roof(self):
        assert should_request_drone_survey("very_complex", 2000) is True

    def test_should_request_for_large_property(self):
        assert should_request_drone_survey("moderate", 4500) is True

    def test_should_not_request_if_eagleview_exists(self):
        assert should_request_drone_survey("very_complex", 5000, has_eagleview=True) is False

    def test_should_not_request_for_simple_small_roof(self):
        assert should_request_drone_survey("simple", 1500) is False

    def test_should_request_for_3_stories(self):
        assert should_request_drone_survey("moderate", 2000, stories=3) is True

    @pytest.mark.asyncio
    async def test_request_survey_without_config_returns_mock(self):
        service = DroneService()
        req = await service.request_survey("123 Main St", project_id="p-1")
        assert req.request_id.startswith("mock-drone-")
        assert req.status == SurveyStatus.REQUESTED

    @pytest.mark.asyncio
    async def test_parse_survey_report(self):
        service = DroneService()
        report = {
            "survey_id": "drone-001",
            "address": "123 Main St",
            "measurements": {
                "total_roof_sqft": 2200,
                "predominant_pitch": "7/12",
                "facets": [
                    {"id": "d1", "area_sqft": 1100, "pitch": "7/12", "pitch_degrees": 30.3},
                    {"id": "d2", "area_sqft": 1100, "pitch": "7/12", "pitch_degrees": 30.3},
                ],
                "ridge_length_ft": 50,
                "eave_length_ft": 170,
            },
            "imagery": {"orthomosaic_url": "https://example.com/ortho.tif"},
        }
        m = await service.parse_survey_report(report)
        assert m.total_roof_sqft == 2200
        assert m.num_facets == 2
        assert m.confidence == 0.96
        assert m.source == MeasurementSource.DRONE
        assert m.report_url == "https://example.com/ortho.tif"


# ---------------------------------------------------------------------------
# Supplier Price Feed
# ---------------------------------------------------------------------------

class TestSupplierPriceFeed:
    def test_parse_webhook_update(self):
        feed = SupplierPriceFeed()
        payload = {
            "price_changes": [
                {
                    "sku": "SH-3TAB-30Y",
                    "name": "3-Tab 30yr Shingles",
                    "category": "shingles",
                    "previous_cost": 30.00,
                    "new_cost": 31.50,
                    "unit_type": "bundle",
                    "effective_date": "2026-04-01",
                },
                {
                    "sku": "UL-SYNTH-10",
                    "name": "Synthetic Underlayment",
                    "category": "underlayment",
                    "previous_cost": 45.00,
                    "new_cost": 52.00,
                    "unit_type": "roll",
                    "effective_date": "2026-04-01",
                },
            ]
        }
        updates = feed.parse_webhook_update(SupplierName.ABC_SUPPLY, payload)
        assert len(updates) == 2
        assert updates[0].unit_cost == 31.50
        assert updates[0].change_pct == 5.0  # 5% increase
        assert updates[1].change_pct == pytest.approx(15.6, abs=0.1)  # >10% flagged

    def test_auto_update_threshold(self):
        feed = SupplierPriceFeed()
        assert feed.AUTO_UPDATE_THRESHOLD_PCT == 10.0


# ---------------------------------------------------------------------------
# Event Types for Phase 4
# ---------------------------------------------------------------------------

class TestPhase4EventTypes:
    def test_change_order_events_exist(self):
        assert EventType.CHANGE_ORDER_REQUESTED.value == "change_order_requested"
        assert EventType.CHANGE_ORDER_APPROVED.value == "change_order_approved"
        assert EventType.CHANGE_ORDER_REJECTED.value == "change_order_rejected"

    def test_measurement_events_exist(self):
        assert EventType.MEASUREMENT_ORDERED.value == "measurement_ordered"
        assert EventType.MEASUREMENT_RECEIVED.value == "measurement_received"
        assert EventType.DRONE_SURVEY_REQUESTED.value == "drone_survey_requested"
        assert EventType.DRONE_SURVEY_COMPLETED.value == "drone_survey_completed"

    def test_supplier_events_exist(self):
        assert EventType.PRICE_UPDATE_APPLIED.value == "price_update_applied"
        assert EventType.PRICE_UPDATE_FLAGGED.value == "price_update_flagged"


# ---------------------------------------------------------------------------
# Preview / Scope
# ---------------------------------------------------------------------------

class TestPreviewScope:
    def test_scope_items_for_roof(self):
        from app.agents.tools.preview import _build_scope_items

        measurement = {
            "ridge_length_ft": 45,
            "flashing_length_ft": 28,
            "drip_edge_length_ft": 212,
        }
        items = _build_scope_items(measurement, "roof_replacement")
        assert any("shingles" in i.lower() for i in items)
        assert any("ridge vent" in i.lower() for i in items)
        assert any("flashing" in i.lower() for i in items)
        assert any("drip edge" in i.lower() for i in items)
        assert any("debris" in i.lower() or "cleanup" in i.lower() or "clean up" in i.lower() for i in items)

    def test_scope_items_for_siding(self):
        from app.agents.tools.preview import _build_scope_items

        items = _build_scope_items({}, "siding_install")
        assert any("siding" in i.lower() for i in items)
        assert any("trim" in i.lower() for i in items)

    def test_format_preview_sms(self):
        from app.agents.tools.preview import _format_preview_sms

        measurement = {
            "total_roof_sqft": 1850,
            "num_facets": 4,
            "predominant_pitch": "6/12",
        }
        sms = _format_preview_sms(measurement, "roof_replacement", "Great property!")
        assert "1,850" in sms
        assert "6/12" in sms
        assert "4" in sms


# ---------------------------------------------------------------------------
# Vision QC Summary
# ---------------------------------------------------------------------------

class TestVisionQCSummary:
    @pytest.mark.asyncio
    async def test_qc_summary_no_photos(self):
        from app.agents.tools.vision_qc import generate_qc_summary

        result = await generate_qc_summary.ainvoke({
            "photo_analyses": [],
            "milestone_name": "Tear-off Complete",
        })
        assert result["overall_grade"] == "incomplete"
        assert len(result["issues"]) > 0

    @pytest.mark.asyncio
    async def test_qc_summary_all_approved(self):
        from app.agents.tools.vision_qc import generate_qc_summary

        analyses = [
            {"spec_match_score": 0.9, "recommendation": "approve", "issues": "none"},
            {"spec_match_score": 0.85, "recommendation": "approve", "issues": "none"},
        ]

        with patch("app.agents.tools.vision_qc.llm_router") as mock:
            mock.complete = AsyncMock(
                return_value=type("R", (), {"content": "Great work on the tear-off."})()
            )
            result = await generate_qc_summary.ainvoke({
                "photo_analyses": analyses,
                "milestone_name": "Tear-off Complete",
            })
            assert result["overall_grade"] == "pass"
            assert result["avg_score"] >= 0.8
            assert result["photo_count"] == 2

    @pytest.mark.asyncio
    async def test_qc_summary_with_rejection(self):
        from app.agents.tools.vision_qc import generate_qc_summary

        analyses = [
            {"spec_match_score": 0.3, "recommendation": "reject", "issues": "Missing flashing at valley"},
            {"spec_match_score": 0.8, "recommendation": "approve", "issues": "none"},
        ]

        with patch("app.agents.tools.vision_qc.llm_router") as mock:
            mock.complete = AsyncMock(
                return_value=type("R", (), {"content": "Issues found during QC."})()
            )
            result = await generate_qc_summary.ainvoke({
                "photo_analyses": analyses,
                "milestone_name": "Shingles Installed",
            })
            assert result["overall_grade"] == "fail"
            assert "Missing flashing at valley" in result["issues"]
