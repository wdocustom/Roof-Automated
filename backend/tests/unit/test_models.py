"""Tests for data model enums and schema integrity."""

from app.models.project import ProjectStatus, ProjectType
from app.models.rate_card import MaterialCategory, LaborTaskType, RoofComplexity
from app.models.message import MessageDirection, MessageChannel
from app.models.consent import ConsentStatus


class TestProjectEnums:
    def test_status_pipeline_order(self):
        """Verify the full project lifecycle pipeline exists."""
        expected = [
            "lead", "onboarded", "estimated", "contract_sent", "contract_signed",
            "scheduled", "in_progress", "qc_review", "completed", "invoiced",
            "paid", "cancelled",
        ]
        actual = [s.value for s in ProjectStatus]
        assert actual == expected

    def test_project_types_cover_core_services(self):
        """Verify we cover roof, siding, and gutters."""
        types = {t.value for t in ProjectType}
        assert "roof_replacement" in types
        assert "siding_install" in types
        assert "gutters" in types


class TestRateCardEnums:
    def test_material_categories_comprehensive(self):
        """Verify material categories cover standard roofing/siding materials."""
        cats = {c.value for c in MaterialCategory}
        required = {"shingles", "underlayment", "flashing", "siding_vinyl", "trim", "gutters"}
        assert required.issubset(cats)

    def test_labor_tasks_cover_full_job(self):
        """Verify labor tasks span tear-off to cleanup."""
        tasks = {t.value for t in LaborTaskType}
        assert "tear_off" in tasks
        assert "cleanup" in tasks

    def test_roof_complexity_levels(self):
        """Verify complexity levels for waste factor calculation."""
        levels = [c.value for c in RoofComplexity]
        assert levels == ["simple", "moderate", "complex", "very_complex"]


class TestConsentEnums:
    def test_consent_statuses(self):
        """Verify TCPA consent states."""
        statuses = {s.value for s in ConsentStatus}
        assert statuses == {"opted_in", "opted_out", "pending"}
