"""Tests for the Estimate Engine."""

import pytest

from app.services.estimate_engine import (
    EstimateLineItem,
    EstimateResult,
    format_estimate_for_sms,
)


class TestEstimateLineItem:
    def test_subtotal_without_waste(self):
        item = EstimateLineItem(
            category="shingles",
            description="3-Tab Shingles",
            quantity=17.0,  # 17 squares
            unit="square",
            unit_cost=95.0,
        )
        assert item.subtotal == 17.0 * 95.0

    def test_subtotal_with_waste(self):
        item = EstimateLineItem(
            category="shingles",
            description="3-Tab Shingles",
            quantity=17.0,
            unit="square",
            unit_cost=95.0,
            waste_pct=15.0,
        )
        expected = 17.0 * 1.15 * 95.0
        assert item.subtotal == round(expected, 2)


class TestEstimateResult:
    def test_calculate_totals(self):
        estimate = EstimateResult(
            project_type="roof_replacement",
            total_sqft=1700,
            roof_complexity="moderate",
            materials=[
                EstimateLineItem("shingles", "Shingles", 17, "square", 95.0, 15.0),
                EstimateLineItem("underlayment", "Felt", 17, "roll", 45.0, 10.0),
            ],
            labor=[
                EstimateLineItem("tear_off", "Tear-off", 17, "per_square", 75.0),
                EstimateLineItem("install", "Install", 17, "per_square", 120.0),
            ],
            permit_fees=250.0,
            markup_pct=20.0,
        )

        estimate.calculate_totals(variance_pct=15.0)

        assert estimate.materials_total > 0
        assert estimate.labor_total > 0
        assert estimate.subtotal == round(
            estimate.materials_total + estimate.labor_total + 250.0, 2
        )
        assert estimate.total_low < estimate.total_high
        assert estimate.total_low > 0

    def test_zero_sqft_produces_zero_estimate(self):
        estimate = EstimateResult(
            project_type="roof_replacement",
            total_sqft=0,
            roof_complexity="simple",
        )
        estimate.calculate_totals()
        assert estimate.total_low == 0
        assert estimate.total_high == 0


class TestFormatEstimateForSMS:
    def test_format_includes_range(self):
        estimate = EstimateResult(
            project_type="roof_replacement",
            total_sqft=1700,
            roof_complexity="moderate",
            materials_total=2500,
            labor_total=3000,
            permit_fees=250,
            total_low=5800,
            total_high=7800,
            disclaimers=["This is a preliminary estimate."],
        )

        text = format_estimate_for_sms(estimate)
        assert "$5,800" in text
        assert "$7,800" in text
        assert "preliminary" in text.lower()

    def test_format_includes_human_review_note(self):
        estimate = EstimateResult(
            project_type="roof_replacement",
            total_sqft=3000,
            roof_complexity="complex",
            total_low=12000,
            total_high=16000,
            disclaimers=["Preliminary."],
            requires_human_review=True,
        )

        text = format_estimate_for_sms(estimate)
        assert "team member" in text.lower() or "review" in text.lower()
