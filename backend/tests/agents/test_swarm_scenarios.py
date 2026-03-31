"""Multi-agent swarm scenario tests — end-to-end simulation.

These tests verify that the agent swarm handles realistic multi-step
scenarios correctly. Each scenario involves multiple agents collaborating.
"""

from unittest.mock import AsyncMock, patch

import pytest

from app.agents.events import EventType
from app.agents.graphs.orchestrator import OrchestratorState, decide_next_action
from app.agents.graphs.progress_qc import _get_expected_work
from app.agents.graphs.project_execution import evaluate_schedule
from app.integrations.llm.router import LLMResponse
from app.integrations.weather.client import _is_workable_day

# ---------------------------------------------------------------------------
# Scenario 1: Weather delay + customer notification
# ---------------------------------------------------------------------------


class TestWeatherDelayScenario:
    """Simulate: Storm forecast → execution reschedules → customer notified."""

    @pytest.mark.asyncio
    async def test_orchestrator_routes_weather_to_execution(self):
        mock_response = LLMResponse(
            content="AGENT: execution\nREASONING: Weather alert requires schedule review\nCONFIDENCE: 0.95\nNEEDS_ESCALATION: no",
            model="test",
            input_tokens=100,
            output_tokens=20,
            latency_ms=200,
        )

        with patch("app.agents.graphs.orchestrator.llm_router") as mock:
            mock.complete = AsyncMock(return_value=mock_response)

            state: OrchestratorState = {
                "company_id": "co-1",
                "project_id": "p-1",
                "trigger_event": {
                    "event_type": EventType.WEATHER_ALERT.value,
                    "data": {"alert": "thunderstorm"},
                },
                "trigger_type": EventType.WEATHER_ALERT.value,
                "project_status": "scheduled",
                "project_type": "roof_replacement",
                "milestones": [],
                "recent_events": [],
                "next_agent": "",
                "agent_input": {},
                "decision_reasoning": "",
                "confidence": 0.0,
                "actions_taken": [],
                "events_emitted": [],
                "needs_human_escalation": False,
                "escalation_reason": "",
            }
            result = await decide_next_action(state)
            assert result["next_agent"] == "execution"

    @pytest.mark.asyncio
    async def test_execution_proposes_reschedule_on_rain(self):
        state = {
            "weather_safe": False,
            "weather_alerts": [{"alert_type": "thunderstorm", "severity": "warning"}],
            "forecast": [
                {"date": "2026-04-01", "is_workable": False, "conditions": "Thunderstorm"},
                {"date": "2026-04-02", "is_workable": False, "conditions": "Rain"},
                {"date": "2026-04-03", "is_workable": True, "conditions": "Clear"},
            ],
            "scheduled_start": "2026-04-01T08:00:00Z",
        }
        result = await evaluate_schedule(state)
        assert result["proposed_date"] == "2026-04-03"
        assert "unsafe" in result["reschedule_reason"].lower()


# ---------------------------------------------------------------------------
# Scenario 2: QC photo analysis + human sign-off
# ---------------------------------------------------------------------------


class TestQCSignoffScenario:
    """Simulate: Crew uploads photos → QC analyzes → flags for human → approved."""

    def test_milestone_expectations_are_specific(self):
        """QC should have specific expectations for each standard milestone."""
        tearoff = _get_expected_work("Tear-off Complete", None)
        assert "deck" in tearoff.lower()
        assert "debris" in tearoff.lower() or "nails" in tearoff.lower()

        shingles = _get_expected_work("Shingles Installed", None)
        assert "shingle" in shingles.lower()
        assert "flashing" in shingles.lower()

    @pytest.mark.asyncio
    async def test_orchestrator_routes_photos_to_qc(self):
        mock_response = LLMResponse(
            content="AGENT: qc\nREASONING: Progress photos need quality review\nCONFIDENCE: 0.92\nNEEDS_ESCALATION: no",
            model="test",
            input_tokens=100,
            output_tokens=20,
            latency_ms=200,
        )

        with patch("app.agents.graphs.orchestrator.llm_router") as mock:
            mock.complete = AsyncMock(return_value=mock_response)

            state: OrchestratorState = {
                "company_id": "co-1",
                "project_id": "p-1",
                "trigger_event": {
                    "event_type": EventType.MILESTONE_PHOTO_UPLOADED.value,
                    "data": {"photos": 3},
                },
                "trigger_type": EventType.MILESTONE_PHOTO_UPLOADED.value,
                "project_status": "in_progress",
                "project_type": "roof_replacement",
                "milestones": [{"name": "Tear-off Complete", "status": "in_progress"}],
                "recent_events": [],
                "next_agent": "",
                "agent_input": {},
                "decision_reasoning": "",
                "confidence": 0.0,
                "actions_taken": [],
                "events_emitted": [],
                "needs_human_escalation": False,
                "escalation_reason": "",
            }
            result = await decide_next_action(state)
            assert result["next_agent"] == "qc"


# ---------------------------------------------------------------------------
# Scenario 3: Milestone complete → payment trigger
# ---------------------------------------------------------------------------


class TestMilestonePaymentScenario:
    """Simulate: Milestone approved → payment agent sends invoice."""

    @pytest.mark.asyncio
    async def test_orchestrator_routes_approval_to_payment(self):
        mock_response = LLMResponse(
            content="AGENT: payment\nREASONING: Milestone approved, generate invoice\nCONFIDENCE: 0.95\nNEEDS_ESCALATION: no",
            model="test",
            input_tokens=100,
            output_tokens=20,
            latency_ms=200,
        )

        with patch("app.agents.graphs.orchestrator.llm_router") as mock:
            mock.complete = AsyncMock(return_value=mock_response)

            state: OrchestratorState = {
                "company_id": "co-1",
                "project_id": "p-1",
                "trigger_event": {
                    "event_type": EventType.MILESTONE_HUMAN_APPROVED.value,
                    "data": {"milestone": "Shingles Installed"},
                },
                "trigger_type": EventType.MILESTONE_HUMAN_APPROVED.value,
                "project_status": "in_progress",
                "project_type": "roof_replacement",
                "milestones": [
                    {"name": "Tear-off Complete", "status": "approved"},
                    {"name": "Shingles Installed", "status": "approved"},
                ],
                "recent_events": [],
                "next_agent": "",
                "agent_input": {},
                "decision_reasoning": "",
                "confidence": 0.0,
                "actions_taken": [],
                "events_emitted": [],
                "needs_human_escalation": False,
                "escalation_reason": "",
            }
            result = await decide_next_action(state)
            assert result["next_agent"] == "payment"


# ---------------------------------------------------------------------------
# Scenario 4: Concurrent issues (weather + material delay)
# ---------------------------------------------------------------------------


class TestConcurrentIssuesScenario:
    """Test that the system handles multiple simultaneous issues correctly."""

    def test_workability_wind_threshold(self):
        """High winds should prevent work even on clear days."""
        assert _is_workable_day(precip_chance=5, wind_speed=30, temp_high=75, temp_low=55) is False

    def test_workability_temperature_threshold(self):
        """Extreme cold should prevent work (shingles become brittle)."""
        assert _is_workable_day(precip_chance=5, wind_speed=5, temp_high=40, temp_low=30) is False

    def test_workability_ideal_conditions(self):
        """Ideal spring day should be workable."""
        assert _is_workable_day(precip_chance=10, wind_speed=8, temp_high=72, temp_low=55) is True

    def test_workability_borderline_rain(self):
        """40% rain chance is the cutoff — 41% should not be workable."""
        assert _is_workable_day(precip_chance=41, wind_speed=8, temp_high=72, temp_low=55) is False
        assert _is_workable_day(precip_chance=40, wind_speed=8, temp_high=72, temp_low=55) is True


# ---------------------------------------------------------------------------
# Scenario 5: Complex escalation
# ---------------------------------------------------------------------------


class TestEscalationScenario:
    """Test that the orchestrator properly escalates ambiguous situations."""

    @pytest.mark.asyncio
    async def test_insurance_claim_escalated(self):
        mock_response = LLMResponse(
            content="AGENT: escalate\nREASONING: Insurance claim processing requires human judgment\nCONFIDENCE: 0.3\nNEEDS_ESCALATION: yes",
            model="test",
            input_tokens=100,
            output_tokens=20,
            latency_ms=200,
        )

        with patch("app.agents.graphs.orchestrator.llm_router") as mock:
            mock.complete = AsyncMock(return_value=mock_response)

            state: OrchestratorState = {
                "company_id": "co-1",
                "project_id": "p-1",
                "trigger_event": {
                    "event_type": "insurance_claim",
                    "data": {"carrier": "State Farm", "claim_amount": 15000},
                },
                "trigger_type": "insurance_claim",
                "project_status": "estimated",
                "project_type": "roof_replacement",
                "milestones": [],
                "recent_events": [],
                "next_agent": "",
                "agent_input": {},
                "decision_reasoning": "",
                "confidence": 0.0,
                "actions_taken": [],
                "events_emitted": [],
                "needs_human_escalation": False,
                "escalation_reason": "",
            }
            result = await decide_next_action(state)
            assert result["needs_human_escalation"]
            assert result["confidence"] < 0.5
