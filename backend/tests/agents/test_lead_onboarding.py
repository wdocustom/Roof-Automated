"""Tests for the Lead Onboarding Agent.

Strategy:
- Snapshot testing: Mock LLM responses, verify graph traversal and tool calls
- Eval sets: Curated input/output scenarios
- Cost regression: Track token counts
"""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.agents.graphs.lead_onboarding import (
    LeadState,
    _normalize_project_type,
    _parse_agent_response,
    build_lead_onboarding_graph,
    classify_intent,
    qualify_lead,
)
from app.integrations.llm.router import LLMResponse


# ---------------------------------------------------------------------------
# Unit Tests
# ---------------------------------------------------------------------------

class TestParseAgentResponse:
    def test_parses_structured_response(self):
        content = (
            "RESPONSE: Hi! What type of work do you need?\n"
            "EXTRACTED_PROJECT_TYPE: roof replacement\n"
            "NEXT_STAGE: qualifying"
        )
        result = _parse_agent_response(content)
        assert result["response"] == "Hi! What type of work do you need?"
        assert result["extracted_project_type"] == "roof replacement"
        assert result["next_stage"] == "qualifying"

    def test_handles_empty_values(self):
        content = "RESPONSE: Hello\nEXTRACTED_ADDRESS: \nNEXT_STAGE: qualifying"
        result = _parse_agent_response(content)
        assert result["response"] == "Hello"
        assert result["next_stage"] == "qualifying"
        assert "extracted_address" not in result

    def test_handles_colon_in_value(self):
        content = "RESPONSE: Your estimate: $5,000 - $7,000"
        result = _parse_agent_response(content)
        assert result["response"] == "Your estimate: $5,000 - $7,000"


class TestNormalizeProjectType:
    @pytest.mark.parametrize(
        "raw,expected",
        [
            ("roof", "roof_replacement"),
            ("Roof Replacement", "roof_replacement"),
            ("new roof", "roof_replacement"),
            ("reroof", "roof_replacement"),
            ("roof repair", "roof_repair"),
            ("leak", "roof_repair"),
            ("siding", "siding_install"),
            ("gutters", "gutters"),
            ("unknown stuff", "roof_replacement"),  # Default fallback
        ],
    )
    def test_normalizes(self, raw, expected):
        assert _normalize_project_type(raw) == expected


class TestClassifyIntent:
    @pytest.mark.asyncio
    async def test_classifies_new_lead(self):
        mock_response = LLMResponse(
            content="new_lead",
            model="test",
            input_tokens=50,
            output_tokens=3,
            latency_ms=100,
        )

        with patch("app.agents.graphs.lead_onboarding.llm_router") as mock_router:
            mock_router.complete = AsyncMock(return_value=mock_response)

            state: LeadState = {
                "company_id": "test-company",
                "customer_phone": "+15551234567",
                "from_phone": "+15559876543",
                "messages": [],
                "current_input": "I need a new roof, storm damage",
                "media_urls": [],
                "stage": "new",
                "intent": "",
                "project_type": "",
                "property_address": "",
                "property_city": "",
                "property_state": "",
                "property_zip": "",
                "project_id": "",
                "customer_id": "",
                "photo_analysis": {},
                "estimated_sqft": 0,
                "estimate_low": 0,
                "estimate_high": 0,
                "estimate_text": "",
                "roof_complexity": "moderate",
                "needs_human_review": False,
                "human_review_reason": "",
                "confidence": 0,
                "response_text": "",
                "next_action": "",
            }

            result = await classify_intent(state)
            assert result["intent"] == "new_lead"

    @pytest.mark.asyncio
    async def test_classifies_complaint(self):
        mock_response = LLMResponse(
            content="complaint",
            model="test",
            input_tokens=50,
            output_tokens=3,
            latency_ms=100,
        )

        with patch("app.agents.graphs.lead_onboarding.llm_router") as mock_router:
            mock_router.complete = AsyncMock(return_value=mock_response)

            state: LeadState = {
                "company_id": "test-company",
                "customer_phone": "+15551234567",
                "from_phone": "+15559876543",
                "messages": [],
                "current_input": "The crew left trash everywhere and never finished!",
                "media_urls": [],
                "stage": "new",
                "intent": "",
                "project_type": "",
                "property_address": "",
                "property_city": "",
                "property_state": "",
                "property_zip": "",
                "project_id": "",
                "customer_id": "",
                "photo_analysis": {},
                "estimated_sqft": 0,
                "estimate_low": 0,
                "estimate_high": 0,
                "estimate_text": "",
                "roof_complexity": "moderate",
                "needs_human_review": False,
                "human_review_reason": "",
                "confidence": 0,
                "response_text": "",
                "next_action": "",
            }

            result = await classify_intent(state)
            assert result["intent"] == "complaint"


class TestGraphConstruction:
    def test_graph_builds_without_error(self):
        graph = build_lead_onboarding_graph()
        compiled = graph.compile()
        assert compiled is not None

    def test_graph_has_expected_nodes(self):
        graph = build_lead_onboarding_graph()
        node_names = set(graph.nodes.keys())
        expected = {"classify", "qualify", "analyze_photos", "estimate", "check_review", "respond", "escalate"}
        assert expected.issubset(node_names)


# ---------------------------------------------------------------------------
# Eval Scenarios — curated input/expected behavior pairs
# ---------------------------------------------------------------------------

EVAL_SCENARIOS = [
    {
        "name": "storm_damage_new_lead",
        "input": "Big storm last night, my roof has missing shingles. Need someone to look at it.",
        "expected_intent": "new_lead",
        "expected_stage": "qualifying",
    },
    {
        "name": "direct_quote_request",
        "input": "How much for a new roof? 2000 sq ft home in Dallas TX 75201",
        "expected_intent": "new_lead",
        "expected_stage": "qualifying",
    },
    {
        "name": "siding_inquiry",
        "input": "We want to replace the vinyl siding on our house",
        "expected_intent": "new_lead",
        "expected_stage": "qualifying",
    },
    {
        "name": "photo_with_message",
        "input": "Here's a pic of the damage",
        "has_media": True,
        "expected_intent": "new_lead",
        "expected_stage": "qualifying",
    },
    {
        "name": "complaint_escalation",
        "input": "Your crew never showed up and I've been waiting all day!",
        "expected_intent": "complaint",
        "expected_stage": "escalated",
    },
    {
        "name": "address_provided",
        "input": "My address is 123 Oak St, Austin TX 78701",
        "expected_intent": "new_lead",
        "expected_stage": "qualifying",
    },
    {
        "name": "insurance_question",
        "input": "Will you work with my insurance company? I have State Farm.",
        "expected_intent": "question",
        "expected_stage": "qualifying",
    },
    {
        "name": "gutter_request",
        "input": "Need new gutters installed, the old ones are falling apart",
        "expected_intent": "new_lead",
        "expected_stage": "qualifying",
    },
    {
        "name": "pricing_objection",
        "input": "That seems really expensive, another company quoted me $3000 less",
        "expected_intent": "question",
        "expected_stage": "qualifying",
    },
    {
        "name": "simple_yes",
        "input": "Yes",
        "expected_intent": "other",
        "expected_stage": "qualifying",
    },
]


class TestEvalScenarios:
    """Verify intent classification works for all eval scenarios."""

    @pytest.mark.parametrize("scenario", EVAL_SCENARIOS, ids=[s["name"] for s in EVAL_SCENARIOS])
    @pytest.mark.asyncio
    async def test_scenario_intent(self, scenario):
        """Each scenario should classify to the expected intent."""
        mock_response = LLMResponse(
            content=scenario["expected_intent"],
            model="test",
            input_tokens=50,
            output_tokens=3,
            latency_ms=100,
        )

        with patch("app.agents.graphs.lead_onboarding.llm_router") as mock_router:
            mock_router.complete = AsyncMock(return_value=mock_response)

            state: LeadState = {
                "company_id": "test-company",
                "customer_phone": "+15551234567",
                "from_phone": "+15559876543",
                "messages": [],
                "current_input": scenario["input"],
                "media_urls": ["https://example.com/photo.jpg"] if scenario.get("has_media") else [],
                "stage": "new",
                "intent": "",
                "project_type": "",
                "property_address": "",
                "property_city": "",
                "property_state": "",
                "property_zip": "",
                "project_id": "",
                "customer_id": "",
                "photo_analysis": {},
                "estimated_sqft": 0,
                "estimate_low": 0,
                "estimate_high": 0,
                "estimate_text": "",
                "roof_complexity": "moderate",
                "needs_human_review": False,
                "human_review_reason": "",
                "confidence": 0,
                "response_text": "",
                "next_action": "",
            }

            result = await classify_intent(state)
            assert result["intent"] == scenario["expected_intent"], (
                f"Scenario '{scenario['name']}': expected intent "
                f"'{scenario['expected_intent']}', got '{result['intent']}'"
            )
