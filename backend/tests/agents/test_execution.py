"""Tests for the Project Execution Agent."""

from unittest.mock import AsyncMock, patch

import pytest

from app.agents.graphs.project_execution import (
    ExecutionState,
    build_execution_graph,
    check_weather,
    evaluate_schedule,
)
from app.integrations.weather.client import DayForecast, WeatherAlert, WeatherForecast


def _make_state(**overrides) -> ExecutionState:
    base: ExecutionState = {
        "company_id": "test-co",
        "project_id": "test-project",
        "trigger": {},
        "project_status": "scheduled",
        "property_zip": "75201",
        "scheduled_start": "2026-04-01T08:00:00Z",
        "crew_lead_phone": "+15551111111",
        "customer_phone": "+15552222222",
        "from_phone": "+15559999999",
        "forecast": [],
        "weather_alerts": [],
        "weather_safe": True,
        "proposed_date": "",
        "reschedule_reason": "",
        "reschedule_approved": False,
        "actions": [],
        "messages_to_send": [],
        "events_to_emit": [],
    }
    base.update(overrides)
    return base


class TestWeatherCheck:
    @pytest.mark.asyncio
    async def test_clear_weather_is_workable(self):
        forecast = WeatherForecast(
            location="75201",
            days=[
                DayForecast(
                    date="2026-04-01",
                    temp_high_f=72, temp_low_f=55,
                    precip_chance=10, precip_inches=0,
                    wind_speed_mph=8, conditions="Clear",
                    is_workable=True,
                ),
            ],
            alerts=[],
        )

        with patch("app.agents.graphs.project_execution.weather_provider") as mock:
            mock.get_forecast = AsyncMock(return_value=forecast)

            state = _make_state()
            result = await check_weather(state)
            assert result["weather_safe"] is True
            assert len(result["forecast"]) == 1

    @pytest.mark.asyncio
    async def test_rain_day_is_not_workable(self):
        forecast = WeatherForecast(
            location="75201",
            days=[
                DayForecast(
                    date="2026-04-01",
                    temp_high_f=68, temp_low_f=52,
                    precip_chance=85, precip_inches=1.5,
                    wind_speed_mph=15, conditions="Rain",
                    is_workable=False,
                ),
                DayForecast(
                    date="2026-04-02",
                    temp_high_f=72, temp_low_f=55,
                    precip_chance=10, precip_inches=0,
                    wind_speed_mph=8, conditions="Clear",
                    is_workable=True,
                ),
            ],
            alerts=[],
        )

        with patch("app.agents.graphs.project_execution.weather_provider") as mock:
            mock.get_forecast = AsyncMock(return_value=forecast)

            state = _make_state()
            result = await check_weather(state)
            assert result["weather_safe"] is False

    @pytest.mark.asyncio
    async def test_weather_alerts_captured(self):
        forecast = WeatherForecast(
            location="75201",
            days=[],
            alerts=[
                WeatherAlert(
                    alert_type="hail",
                    severity="warning",
                    description="Large hail possible",
                    start_time="2026-04-01T12:00Z",
                    end_time="2026-04-01T18:00Z",
                ),
            ],
        )

        with patch("app.agents.graphs.project_execution.weather_provider") as mock:
            mock.get_forecast = AsyncMock(return_value=forecast)

            state = _make_state()
            result = await check_weather(state)
            assert len(result["weather_alerts"]) == 1
            assert result["weather_alerts"][0]["alert_type"] == "hail"


class TestScheduleEvaluation:
    @pytest.mark.asyncio
    async def test_safe_weather_no_reschedule(self):
        state = _make_state(weather_safe=True, weather_alerts=[])
        result = await evaluate_schedule(state)
        assert result["reschedule_reason"] == ""

    @pytest.mark.asyncio
    async def test_unsafe_weather_proposes_reschedule(self):
        state = _make_state(
            weather_safe=False,
            forecast=[
                {"date": "2026-04-01", "is_workable": False, "conditions": "Rain"},
                {"date": "2026-04-02", "is_workable": True, "conditions": "Clear"},
            ],
        )
        result = await evaluate_schedule(state)
        assert "unsafe" in result["reschedule_reason"].lower()
        assert result["proposed_date"] == "2026-04-02"


class TestExecutionGraph:
    def test_graph_builds(self):
        graph = build_execution_graph()
        compiled = graph.compile()
        assert compiled is not None

    def test_graph_has_expected_nodes(self):
        graph = build_execution_graph()
        expected = {"check_weather", "evaluate", "reschedule", "dispatch", "send_messages"}
        assert expected.issubset(set(graph.nodes.keys()))
