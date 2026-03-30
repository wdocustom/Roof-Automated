"""Project Execution Agent — scheduling, weather-aware rescheduling, crew dispatch.

This agent manages the physical execution of jobs:
  1. Schedule jobs based on crew availability and weather
  2. Monitor weather forecasts and proactively reschedule
  3. Dispatch crews with all context needed
  4. Handle material ordering/delay management (stubs)
  5. Coordinate with customer via engagement agent

Runs inside Temporal Activities for durability. Weather checks can be
scheduled as recurring Temporal activities.
"""

from __future__ import annotations

import operator
from datetime import datetime, timedelta, timezone
from typing import Annotated, Any, TypedDict

from langgraph.graph import END, StateGraph

from app.agents.events import Event, EventType, emit_event
from app.integrations.llm.router import LLMRequest, ModelTier, llm_router
from app.integrations.weather.client import weather_provider


# ---------------------------------------------------------------------------
# State
# ---------------------------------------------------------------------------

class ExecutionState(TypedDict):
    """State for the project execution agent."""

    company_id: str
    project_id: str
    trigger: dict  # Event that triggered this agent

    # Project context
    project_status: str
    property_zip: str
    scheduled_start: str
    crew_lead_phone: str
    customer_phone: str
    from_phone: str

    # Weather
    forecast: list[dict]
    weather_alerts: list[dict]
    weather_safe: bool

    # Scheduling
    proposed_date: str
    reschedule_reason: str
    reschedule_approved: bool

    # Outputs
    actions: Annotated[list[dict], operator.add]
    messages_to_send: Annotated[list[dict], operator.add]
    events_to_emit: Annotated[list[dict], operator.add]


# ---------------------------------------------------------------------------
# Nodes
# ---------------------------------------------------------------------------

async def check_weather(state: ExecutionState) -> dict:
    """Check weather forecast for the job location."""
    zip_code = state.get("property_zip", "")
    if not zip_code:
        return {"weather_safe": True, "forecast": [], "weather_alerts": []}

    forecast = await weather_provider.get_forecast(zip_code=zip_code, days=7)

    forecast_data = [
        {
            "date": d.date,
            "conditions": d.conditions,
            "precip_chance": d.precip_chance,
            "wind_speed_mph": d.wind_speed_mph,
            "temp_high_f": d.temp_high_f,
            "is_workable": d.is_workable,
        }
        for d in forecast.days
    ]

    alerts_data = [
        {
            "alert_type": a.alert_type,
            "severity": a.severity,
            "description": a.description,
        }
        for a in forecast.alerts
    ]

    # Check if scheduled date is workable
    scheduled = state.get("scheduled_start", "")
    weather_safe = True

    if scheduled:
        for day in forecast.days:
            if day.date == scheduled[:10]:  # Compare date portion
                weather_safe = day.is_workable
                break

    return {
        "forecast": forecast_data,
        "weather_alerts": alerts_data,
        "weather_safe": weather_safe,
    }


async def evaluate_schedule(state: ExecutionState) -> dict:
    """Evaluate if the current schedule is viable or needs adjustment."""
    if state.get("weather_safe", True) and not state.get("weather_alerts"):
        return {"reschedule_reason": "", "proposed_date": ""}

    # Find next workable day
    proposed = ""
    for day in state.get("forecast", []):
        if day.get("is_workable", False):
            proposed = day["date"]
            break

    reason_parts = []
    if not state.get("weather_safe"):
        scheduled = state.get("scheduled_start", "unknown")
        reason_parts.append(f"Weather unsafe on scheduled date ({scheduled[:10]})")

    for alert in state.get("weather_alerts", []):
        reason_parts.append(f"{alert['severity'].title()}: {alert['alert_type']}")

    return {
        "reschedule_reason": "; ".join(reason_parts),
        "proposed_date": proposed,
    }


async def propose_reschedule(state: ExecutionState) -> dict:
    """Generate reschedule proposal and notify customer + crew."""
    reason = state.get("reschedule_reason", "")
    proposed = state.get("proposed_date", "")
    customer_phone = state.get("customer_phone", "")
    crew_lead_phone = state.get("crew_lead_phone", "")

    messages = []

    if customer_phone and proposed:
        messages.append({
            "to": customer_phone,
            "body": (
                f"Weather update: We need to reschedule your job due to {reason}. "
                f"Proposing {proposed} instead. Reply YES to confirm or suggest "
                f"an alternative date."
            ),
        })

    if crew_lead_phone and proposed:
        messages.append({
            "to": crew_lead_phone,
            "body": (
                f"Schedule change: Job at project {state['project_id'][:8]}... "
                f"rescheduled to {proposed} due to weather. Confirm availability."
            ),
        })

    events = [{
        "type": EventType.JOB_RESCHEDULED.value,
        "data": {
            "reason": reason,
            "original_date": state.get("scheduled_start", ""),
            "proposed_date": proposed,
        },
        "description": f"Rescheduled from {state.get('scheduled_start', 'N/A')[:10]} to {proposed}: {reason}",
    }]

    return {
        "messages_to_send": messages,
        "events_to_emit": events,
        "actions": [{"action": "reschedule_proposed", "proposed_date": proposed, "reason": reason}],
    }


async def dispatch_crew(state: ExecutionState) -> dict:
    """Dispatch crew for the scheduled job — send all needed context."""
    crew_lead_phone = state.get("crew_lead_phone", "")
    if not crew_lead_phone:
        return {"actions": [{"action": "dispatch_skipped", "reason": "no crew lead assigned"}]}

    # Build dispatch message with key details
    forecast_today = ""
    for day in state.get("forecast", []):
        if day.get("date") == state.get("scheduled_start", "")[:10]:
            forecast_today = f"Weather: {day['conditions']}, High {day['temp_high_f']}°F"
            break

    messages = [{
        "to": crew_lead_phone,
        "body": (
            f"Dispatch confirmed for today.\n"
            f"Project: {state['project_id'][:8]}...\n"
            f"{forecast_today}\n"
            f"Upload progress photos at each milestone. Text COMPLETE when done."
        ),
    }]

    events = [{
        "type": EventType.CREW_DISPATCHED.value,
        "data": {"crew_lead_phone": crew_lead_phone},
        "description": "Crew dispatched for scheduled work",
    }]

    return {
        "messages_to_send": messages,
        "events_to_emit": events,
        "actions": [{"action": "crew_dispatched"}],
    }


async def send_messages(state: ExecutionState) -> dict:
    """Send all queued messages via SMS."""
    from app.agents.tools.messaging import send_text_message

    from_phone = state.get("from_phone", "")
    for msg in state.get("messages_to_send", []):
        await send_text_message.ainvoke({
            "to_phone": msg["to"],
            "body": msg["body"],
            "from_phone": from_phone,
        })

    # Emit all queued events
    for event_data in state.get("events_to_emit", []):
        await emit_event(
            company_id=state["company_id"],
            event=Event(
                event_type=EventType(event_data["type"]),
                agent_name="execution",
                project_id=state["project_id"],
                data=event_data.get("data", {}),
                description=event_data.get("description", ""),
            ),
        )

    return {}


# ---------------------------------------------------------------------------
# Routing
# ---------------------------------------------------------------------------

def route_after_evaluate(state: ExecutionState) -> str:
    if state.get("reschedule_reason"):
        return "reschedule"
    return "dispatch"


# ---------------------------------------------------------------------------
# Graph
# ---------------------------------------------------------------------------

def build_execution_graph() -> StateGraph:
    """Build the Project Execution Agent graph.

    Flow:
        check_weather → evaluate_schedule → reschedule → send_messages
                                          ↓
                                        dispatch → send_messages
    """
    graph = StateGraph(ExecutionState)

    graph.add_node("check_weather", check_weather)
    graph.add_node("evaluate", evaluate_schedule)
    graph.add_node("reschedule", propose_reschedule)
    graph.add_node("dispatch", dispatch_crew)
    graph.add_node("send_messages", send_messages)

    graph.set_entry_point("check_weather")
    graph.add_edge("check_weather", "evaluate")

    graph.add_conditional_edges("evaluate", route_after_evaluate, {
        "reschedule": "reschedule",
        "dispatch": "dispatch",
    })

    graph.add_edge("reschedule", "send_messages")
    graph.add_edge("dispatch", "send_messages")
    graph.add_edge("send_messages", END)

    return graph


execution_graph = build_execution_graph().compile()
