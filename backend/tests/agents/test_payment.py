"""Tests for the Payment & Closure Agent."""

import pytest

from app.agents.graphs.payment_closure import (
    PaymentState,
    build_payment_graph,
    route_after_determine,
)
from app.agents.events import EventType


def _make_state(**overrides) -> PaymentState:
    base: PaymentState = {
        "company_id": "test-co",
        "project_id": "test-project",
        "trigger": {},
        "project_status": "in_progress",
        "contract_amount": 8500.0,
        "amount_paid": 0.0,
        "amount_due": 8500.0,
        "customer_phone": "+15552222222",
        "customer_email": "customer@test.com",
        "from_phone": "+15559999999",
        "property_address": "123 Oak St",
        "payment_schedule": [],
        "current_milestone_payment": {},
        "days_overdue": 0,
        "actions": [],
        "events_to_emit": [],
        "messages_to_send": [],
    }
    base.update(overrides)
    return base


class TestPaymentRouting:
    def test_routes_milestone_to_invoice(self):
        state = _make_state(
            current_milestone_payment={"type": "milestone_invoice", "amount": 4250}
        )
        assert route_after_determine(state) == "invoice"

    def test_routes_final_to_invoice(self):
        state = _make_state(
            current_milestone_payment={"type": "final_invoice", "amount": 4250}
        )
        assert route_after_determine(state) == "invoice"

    def test_routes_overdue_to_reminder(self):
        state = _make_state(
            current_milestone_payment={"type": "reminder", "amount": 8500}
        )
        assert route_after_determine(state) == "reminder"

    def test_routes_paid_to_warranty(self):
        state = _make_state(
            current_milestone_payment={"type": "none"},
            amount_due=0,
        )
        assert route_after_determine(state) == "warranty"

    def test_routes_nothing_to_notify(self):
        state = _make_state(
            current_milestone_payment={"type": "none"},
            amount_due=5000,  # Still owes money, but no action determined
        )
        assert route_after_determine(state) == "notify"


class TestPaymentGraph:
    def test_graph_builds(self):
        graph = build_payment_graph()
        compiled = graph.compile()
        assert compiled is not None

    def test_graph_has_expected_nodes(self):
        graph = build_payment_graph()
        expected = {"load_context", "determine", "invoice", "reminder", "warranty", "notify"}
        assert expected.issubset(set(graph.nodes.keys()))
