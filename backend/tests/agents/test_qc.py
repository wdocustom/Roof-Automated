"""Tests for the Progress & QC Agent."""

from unittest.mock import AsyncMock, patch

import pytest

from app.agents.graphs.progress_qc import (
    QCState,
    _get_expected_work,
    build_qc_graph,
)
from app.integrations.llm.router import LLMResponse


class TestExpectedWork:
    def test_tearoff_expectations(self):
        result = _get_expected_work("Tear-off Complete", None)
        assert "removed" in result.lower()
        assert "deck" in result.lower()

    def test_shingles_expectations(self):
        result = _get_expected_work("Shingles Installed", None)
        assert "shingle" in result.lower()
        assert "nailing" in result.lower()

    def test_final_walkthrough(self):
        result = _get_expected_work("Final Walkthrough", None)
        assert "complete" in result.lower()

    def test_unknown_milestone(self):
        result = _get_expected_work("Custom Milestone XYZ", None)
        assert "Custom Milestone XYZ" in result


class TestQCGraph:
    def test_graph_builds(self):
        graph = build_qc_graph()
        compiled = graph.compile()
        assert compiled is not None

    def test_graph_has_expected_nodes(self):
        graph = build_qc_graph()
        expected = {"load_milestone", "analyze_photos", "assess_quality", "handle_result", "notify"}
        assert expected.issubset(set(graph.nodes.keys()))


class TestQCAssessment:
    @pytest.mark.asyncio
    async def test_conservative_on_no_photos(self):
        """QC should flag for review when no photos are available."""
        from app.agents.graphs.progress_qc import analyze_photos

        state: QCState = {
            "company_id": "test-co",
            "project_id": "test-project",
            "trigger": {},
            "milestone_id": "m1",
            "milestone_name": "Tear-off Complete",
            "milestone_requires_photo": True,
            "milestone_requires_human_signoff": False,
            "expected_work": "Deck clear",
            "photo_urls": [],  # No photos
            "photo_analyses": [],
            "qc_passed": False,
            "issues_found": [],
            "confidence": 0.0,
            "recommendation": "",
            "qc_report": {},
            "actions": [],
            "events_to_emit": [],
            "messages_to_send": [],
            "customer_phone": "",
            "crew_lead_phone": "",
            "owner_phone": "",
            "from_phone": "",
        }

        result = await analyze_photos(state)
        assert result["confidence"] == 0.0
        assert len(result["issues_found"]) > 0
