"""Minimal QWeather client for Sprinkler Timer."""

from __future__ import annotations

import asyncio
from datetime import datetime
import logging
from typing import Any

from aiohttp import ClientError, ClientSession

from .const import DEFAULT_QWEATHER_HOST, QWEATHER_TIMEOUT

_LOGGER = logging.getLogger(__name__)


class QWeatherError(Exception):
    """Raised when QWeather data cannot be fetched or parsed."""


class QWeatherClient:
    """Small client for the QWeather hourly forecast endpoint."""

    def __init__(
        self,
        session: ClientSession,
        api_key: str,
        latitude: float,
        longitude: float,
        api_host: str = DEFAULT_QWEATHER_HOST,
    ) -> None:
        self._session = session
        self._api_key = api_key
        self._latitude = latitude
        self._longitude = longitude
        self._api_host = api_host.rstrip("/")

    async def async_get_rain_12h(self) -> float:
        """Return expected precipitation in the next 12 hours, in millimeters."""
        forecast = await self.async_get_hourly_rain(12)
        return sum(forecast.values())

    async def async_get_hourly_rain(self, hours: int = 12) -> dict[datetime, float]:
        """Return expected hourly precipitation keyed by forecast time."""
        url = f"{self._api_host}/v7/weather/24h"
        params = {
            "location": f"{self._longitude},{self._latitude}",
            "key": self._api_key,
        }

        try:
            async with asyncio.timeout(QWEATHER_TIMEOUT):
                response = await self._session.get(url, params=params)
                response.raise_for_status()
                payload: dict[str, Any] = await response.json()
        except (TimeoutError, ClientError, ValueError) as err:
            raise QWeatherError(f"Unable to fetch QWeather forecast: {err}") from err

        code = str(payload.get("code", ""))
        if code and code != "200":
            _LOGGER.debug("QWeather returned non-success payload: %s", payload)
            raise QWeatherError(f"QWeather returned code {code}")

        hourly = payload.get("hourly")
        if not isinstance(hourly, list):
            raise QWeatherError("QWeather response did not include hourly forecast")

        forecast: dict[datetime, float] = {}
        for item in hourly[:hours]:
            if not isinstance(item, dict):
                continue
            fx_time = item.get("fxTime")
            if not isinstance(fx_time, str):
                continue
            try:
                forecast_time = datetime.fromisoformat(fx_time)
                rain = float(item.get("precip", 0) or 0)
            except (TypeError, ValueError):
                continue
            forecast[forecast_time] = rain

        return forecast
