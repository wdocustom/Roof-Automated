"""Tests for the Orchestrator/Supervisor Agent."""

from unittest.mock import AsyncMock, patch

import pytest

from app.agents.events import EventType
from app.agents.graphs.orchestrator import (
    OrchestratorState,
    build_orchestrator_graph,
    decide_next_action,
)
from app.integrations.llm.router import LLMResponse


def _make_state(**overrides) -> OrchestratorState:
    base: OrchestratorState = {
        "company_id": "test-co",
        "project_id": "test-project",
        "trigger_event": {},
        "trigger_type": "",
        "project_status": "in_progress",
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
    base.update(overrides)
    return base


class TestOrchestratorRouting:
    @pytest.mark.asyncio
    async def test_routes_weather_to_execution(self):
        mock_response = LLMResponse(
            content="AGENT: execution\nREASONING: Weather alert needs scheduling review\nCONFIDENCE: 0.95\nNEEDS_ESCALATION: no",
            model="test",
            input_tokens=100,
            output_tokens=20,
            latency_ms=200,
        )

        with patch("app.agents.graphs.orchestrator.llm_router") as mock_router:
            mock_router.complete = AsyncMock(return_value=mock_response)

            state = _make_state(
                trigger_event={"event_type": EventType.WEATHER_ALERT.value, "data": {"alert": "thunderstorm warning"}},
                trigger_type=EventType.WEATHER_ALERT.value,
            )

            result = await decide_next_action(state)
            assert result["next_agent"] == "execution"
            assert not result["needs_human_escalation"]

    @pytest.mark.asyncio
    async def test_routes_photo_upload_to_qc(self):
        mock_response = LLMResponse(
            content="AGENT: qc\nREASONING: Crew uploaded progress photos, need QC review\nCONFIDENCE: 0.9\nNEEDS_ESCALATION: no",
            model="test",
            input_tokens=100,
            output_tokens=20,
            latency_ms=200,
        )

        with patch("app.agents.graphs.orchestrator.llm_router") as mock_router:
            mock_router.complete = AsyncMock(return_value=mock_response)

            state = _make_state(
                trigger_event={"event_type": EventType.MILESTONE_PHOTO_UPLOADED.value},
                trigger_type=EventType.MILESTONE_PHOTO_UPLOADED.value,
            )

            result = await decide_next_action(state)
            assert result["next_agent"] == "qc"

    @pytest.mark.asyncio
    async def test_routes_payment_to_payment_agent(self):
        mock_response = LLMResponse(
            content="AGENT: payment\nREASONING: Milestone approved, trigger invoice\nCONFIDENCE: 0.95\nNEEDS_ESCALATION: no",
            model="test",
            input_tokens=100,
            output_tokens=20,
            latency_ms=200,
        )

        with patch("app.agents.graphs.orchestrator.llm_router") as mock_router:
            mock_router.complete = AsyncMock(return_value=mock_response)

            state = _make_state(
                trigger_event={"event_type": EventType.MILESTONE_HUMAN_APPROVED.value},
                trigger_type=EventType.MILESTONE_HUMAN_APPROVED.value,
            )

            result = await decide_next_action(state)
            assert result["next_agent"] == "payment"

    @pytest.mark.asyncio
    async def test_escalates_on_low_confidence(self):
        mock_response = LLMResponse(
            content="AGENT: escalate\nREASONING: Complex insurance claim, need human judgment\nCONFIDENCE: 0.3\nNEEDS_ESCALATION: yes",
            model="test",
            input_tokens=100,
            output_tokens=20,
            latency_ms=200,
        )

        with patch("app.agents.graphs.orchestrator.llm_router") as mock_router:
            mock_router.complete = AsyncMock(return_value=mock_response)

            state = _make_state(
                trigger_event={"event_type": "insurance_claim", "data": {"carrier": "State Farm"}},
                trigger_type="insurance_claim",
            )

            result = await decide_next_action(state)
            assert result["needs_human_escalation"]


class TestOrchestratorGraph:
    def test_graph_builds(self):
        graph = build_orchestrator_graph()
        compiled = graph.compile()
        assert compiled is not None

    def test_graph_has_expected_nodes(self):
        graph = build_orchestrator_graph()
        expected = {"load_state", "decide", "dispatch", "escalate"}
        assert expected.issubset(set(graph.nodes.keys()))
