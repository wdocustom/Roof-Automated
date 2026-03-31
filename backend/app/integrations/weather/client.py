"""Weather integration for proactive scheduling decisions.

Uses Visual Crossing API (free tier: 1000 calls/day) for forecasts.
Stubbed interface allows swapping to Meteomatics/Xweather later.
"""

from dataclasses import dataclass

import httpx

from app.core.config import settings


@dataclass
class DayForecast:
    """Weather forecast for a single day."""

    date: str
    temp_high_f: float
    temp_low_f: float
    precip_chance: float  # 0-100
    precip_inches: float
    wind_speed_mph: float
    conditions: str  # "Clear", "Rain", "Snow", etc.
    is_workable: bool  # Safe for roofing/siding work


@dataclass
class WeatherAlert:
    """Severe weather alert that may affect job scheduling."""

    alert_type: str  # "thunderstorm", "hail", "high_wind", "extreme_cold"
    severity: str  # "watch", "warning", "advisory"
    description: str
    start_time: str
    end_time: str


@dataclass
class WeatherForecast:
    """Multi-day forecast for a location."""

    location: str
    days: list[DayForecast]
    alerts: list[WeatherAlert]
    source: str = "visual_crossing"


class WeatherProvider:
    """Abstract weather provider interface."""

    async def get_forecast(
        self,
        zip_code: str,
        days: int = 7,
    ) -> WeatherForecast:
        """Get weather forecast for a ZIP code."""
        raise NotImplementedError


class VisualCrossingProvider(WeatherProvider):
    """Visual Crossing Weather API integration."""

    BASE_URL = "https://weather.visualcrossing.com/VisualCrossingWebServices/rest/services/timeline"

    def __init__(self, api_key: str = ""):
        self.api_key = api_key or getattr(settings, "visual_crossing_api_key", "")

    async def get_forecast(self, zip_code: str, days: int = 7) -> WeatherForecast:
        if not self.api_key:
            return _mock_forecast(zip_code, days)

        async with httpx.AsyncClient() as client:
            resp = await client.get(
                f"{self.BASE_URL}/{zip_code}",
                params={
                    "unitGroup": "us",
                    "key": self.api_key,
                    "contentType": "json",
                    "include": "days,alerts",
                },
                timeout=10.0,
            )
            resp.raise_for_status()
            data = resp.json()

        forecast_days = []
        for day_data in data.get("days", [])[:days]:
            is_workable = _is_workable_day(
                precip_chance=day_data.get("precipprob", 0),
                wind_speed=day_data.get("windspeed", 0),
                temp_high=day_data.get("tempmax", 70),
                temp_low=day_data.get("tempmin", 50),
            )
            forecast_days.append(
                DayForecast(
                    date=day_data.get("datetime", ""),
                    temp_high_f=day_data.get("tempmax", 0),
                    temp_low_f=day_data.get("tempmin", 0),
                    precip_chance=day_data.get("precipprob", 0),
                    precip_inches=day_data.get("precip", 0),
                    wind_speed_mph=day_data.get("windspeed", 0),
                    conditions=day_data.get("conditions", "Unknown"),
                    is_workable=is_workable,
                )
            )

        alerts = []
        for alert_data in data.get("alerts", []):
            alerts.append(
                WeatherAlert(
                    alert_type=_classify_alert(alert_data.get("event", "")),
                    severity=alert_data.get("severity", "advisory"),
                    description=alert_data.get("description", ""),
                    start_time=alert_data.get("onset", ""),
                    end_time=alert_data.get("ends", ""),
                )
            )

        return WeatherForecast(
            location=zip_code,
            days=forecast_days,
            alerts=alerts,
            source="visual_crossing",
        )


def _is_workable_day(
    precip_chance: float,
    wind_speed: float,
    temp_high: float,
    temp_low: float,
) -> bool:
    """Determine if conditions are safe for exterior work.

    Roofing/siding work should not proceed when:
    - Rain probability > 40%
    - Wind > 25 mph (unsafe for elevated work)
    - Temperature < 35°F (shingles become brittle)
    - Temperature > 105°F (heat safety)
    """
    if precip_chance > 40:
        return False
    if wind_speed > 25:
        return False
    if temp_low < 35:
        return False
    return not temp_high > 105


def _classify_alert(event: str) -> str:
    event_lower = event.lower()
    if "hail" in event_lower:
        return "hail"
    if "thunder" in event_lower or "lightning" in event_lower:
        return "thunderstorm"
    if "wind" in event_lower or "tornado" in event_lower:
        return "high_wind"
    if "cold" in event_lower or "freeze" in event_lower or "winter" in event_lower:
        return "extreme_cold"
    if "heat" in event_lower:
        return "extreme_heat"
    return "other"


def _mock_forecast(zip_code: str, days: int) -> WeatherForecast:
    """Return mock forecast for development/testing."""
    mock_days = []
    for i in range(days):
        mock_days.append(
            DayForecast(
                date=f"2026-04-{i + 1:02d}",
                temp_high_f=72.0,
                temp_low_f=55.0,
                precip_chance=10.0 if i != 2 else 80.0,  # Rain on day 3
                precip_inches=0.0 if i != 2 else 1.2,
                wind_speed_mph=8.0,
                conditions="Clear" if i != 2 else "Rain",
                is_workable=i != 2,
            )
        )

    return WeatherForecast(
        location=zip_code,
        days=mock_days,
        alerts=[],
        source="mock",
    )


# Default provider
weather_provider = VisualCrossingProvider()
