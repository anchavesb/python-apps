"""Weather tool: Bureau of Meteorology (AU) and OpenWeatherMap (Global)."""

from __future__ import annotations

import json

import httpx

from dolores_common.logging import get_logger

from ..config import settings
from .base import Tool

log = get_logger(__name__)

_BOM_BASE_URL = "https://api.weather.bom.gov.au/v1"
_OWM_BASE_URL = "https://api.openweathermap.org/data/2.5"


class WeatherTool(Tool):
    """Get current weather or forecast for a location."""

    @property
    def name(self) -> str:
        return "weather_get"

    @property
    def description(self) -> str:
        return (
            "Get the current weather and forecast for a given location. "
            "Automatically uses Bureau of Meteorology for Australian locations."
        )

    @property
    def parameters(self) -> dict:
        return {
            "type": "object",
            "properties": {
                "location": {
                    "type": "string",
                    "description": "City name or location (e.g. 'Melbourne, AU' or 'London').",
                },
                "units": {
                    "type": "string",
                    "enum": ["metric", "imperial"],
                    "default": "metric",
                    "description": "Unit system to use.",
                },
            },
            "required": ["location"],
        }

    async def execute(self, **kwargs) -> str:
        location: str = kwargs.get("location", "")
        units: str = kwargs.get("units", "metric")

        if not location:
            return "No location provided."

        log.info("weather_request", location=location)

        # Basic heuristic for AU
        is_au = ", au" in location.lower() or " australia" in location.lower()

        try:
            if is_au:
                return await self._get_bom_weather(location)
            else:
                return await self._get_owm_weather(location, units)
        except Exception as e:
            log.error("weather_failed", location=location, error=str(e))
            return f"Failed to get weather for {location}: {e}"

    async def _get_bom_weather(self, location: str) -> str:
        """Fetch weather from BOM (AU)."""
        # Step 1: Search for location to get geohash
        clean_loc = location.lower().replace(", au", "").replace(" australia", "").strip()
        async with httpx.AsyncClient(timeout=10) as client:
            search_resp = await client.get(f"{_BOM_BASE_URL}/locations", params={"search": clean_loc})
            search_resp.raise_for_status()
            search_results = search_resp.json().get("data", [])

            if not search_results:
                # Fallback to OWM if BOM doesn't find it
                return await self._get_owm_weather(location)

            best = search_results[0]
            geohash = best["geohash"][:6]
            name = f"{best['name']}, {best['state']}"

            # Step 2: Get Daily Forecast
            forecast_resp = await client.get(f"{_BOM_BASE_URL}/locations/{geohash}/forecasts/daily")
            forecast_resp.raise_for_status()
            forecast_data = forecast_resp.json().get("data", [])

            if not forecast_data:
                return f"No forecast data found for {name} on BOM."

            today = forecast_data[0]
            summary = today.get("short_amendment") or today.get("precis") or "mainly clear"
            min_temp = today.get("temp_min")
            max_temp = today.get("temp_max")
            rain_chance = today.get("rain", {}).get("chance")

            # Construct a human-readable sentence to help the LLM
            text = f"In {name}, it is expected to be {summary}."
            if min_temp is not None and max_temp is not None:
                text += f" Temperatures will range from {min_temp}°C to {max_temp}°C."
            elif max_temp is not None:
                text += f" Expect a high of {max_temp}°C."

            if rain_chance:
                text += f" There is a {rain_chance}% chance of rain."

            result = {
                "location": name,
                "source": "Bureau of Meteorology",
                "date": today.get("date"),
                "summary": summary,
                "min": min_temp,
                "max": max_temp,
                "rain_chance": rain_chance,
                "rain_amount": today.get("rain", {}).get("amount", {}).get("range"),
                "text": text,
            }
            return json.dumps(result, ensure_ascii=False)

    async def _get_owm_weather(self, location: str, units: str = "metric") -> str:
        """Fetch weather from OpenWeatherMap."""
        if not settings.owm_api_key:
            return "OpenWeatherMap API key is not configured. Please set OPENWEATHERMAP_API_KEY."

        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.get(
                f"{_OWM_BASE_URL}/weather",
                params={
                    "q": location,
                    "units": units,
                    "appid": settings.owm_api_key,
                },
            )
            if resp.status_code == 404:
                return f"Location '{location}' not found."
            resp.raise_for_status()
            data = resp.json()

            name = data.get("name")
            country = data.get("sys", {}).get("country")
            full_name = f"{name}, {country}" if country else name
            condition = data.get("weather", [{}])[0].get("description", "clear")
            temp = data.get("main", {}).get("temp")

            text = f"The weather in {full_name} is currently {condition} with a temperature of {temp}°C."

            result = {
                "location": full_name,
                "source": "OpenWeatherMap",
                "condition": condition,
                "temp": temp,
                "feels_like": data.get("main", {}).get("feels_like"),
                "humidity": data.get("main", {}).get("humidity"),
                "wind_speed": data.get("wind", {}).get("speed"),
                "text": text,
            }
            return json.dumps(result, ensure_ascii=False)
