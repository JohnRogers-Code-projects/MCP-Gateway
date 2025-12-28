"""
Open-Meteo Weather API Domain

Endpoints for the Open-Meteo weather API.
https://open-meteo.com/en/docs

This domain provides:
- Current weather conditions
- 7-day weather forecasts
"""

from __future__ import annotations

from ..config import OPEN_METEO_BASE_URL
from ..endpoints import HttpMethod, RestEndpoint


OPEN_METEO_ENDPOINTS: list[RestEndpoint] = [
    RestEndpoint(
        name="get_weather",
        path="/v1/forecast",
        method=HttpMethod.GET,
        description="Get current weather for coordinates. Returns temperature, wind speed, and conditions.",
        query_params=["latitude", "longitude", "current_weather"],
        base_url=OPEN_METEO_BASE_URL,
    ),
    RestEndpoint(
        name="get_forecast",
        path="/v1/forecast",
        method=HttpMethod.GET,
        description="Get 7-day weather forecast for coordinates.",
        query_params=["latitude", "longitude", "daily", "timezone"],
        base_url=OPEN_METEO_BASE_URL,
    ),
]
