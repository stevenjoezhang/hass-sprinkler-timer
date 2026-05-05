"""Constants for the Sprinkler Timer integration."""

from __future__ import annotations

from datetime import time
from typing import Final

DOMAIN: Final = "sprinkler_timer"

PLATFORMS: Final = ["switch", "sensor"]

CONF_API_KEY: Final = "api_key"
CONF_API_HOST: Final = "api_host"
CONF_CREATED_DATE: Final = "created_date"
CONF_DURATION_MINUTES: Final = "duration_minutes"
CONF_ENABLED: Final = "enabled"
CONF_PLAN_NAME: Final = "plan_name"
CONF_RAIN_SKIP: Final = "rain_skip"
CONF_RAIN_THRESHOLD: Final = "rain_threshold"
CONF_REPEAT_DAYS: Final = "repeat_days"
CONF_SPRINKLER_SWITCHES: Final = "sprinkler_switches"
CONF_START_TIMES: Final = "start_times"

DEFAULT_DURATION_MINUTES: Final = 10
DEFAULT_ENABLED: Final = True
DEFAULT_RAIN_SKIP: Final = True
DEFAULT_RAIN_THRESHOLD: Final = 3.0
DEFAULT_REPEAT_DAYS: Final = 1
DEFAULT_START_TIMES: Final = ("14:00",)

DEFAULT_QWEATHER_HOST: Final = "https://devapi.qweather.com"
QWEATHER_TIMEOUT: Final = 20

ATTR_LAST_RAIN_12H: Final = "last_rain_12h_mm"
ATTR_RAIN_SKIP_ENABLED: Final = "rain_skip_enabled"
ATTR_SCHEDULED_TIMES: Final = "scheduled_times"


def parse_time(value: str) -> time:
    """Parse a HH:MM time string."""
    hour_str, minute_str = value.strip().split(":", 1)
    return time(hour=int(hour_str), minute=int(minute_str))


def format_time(value: time) -> str:
    """Format a time object as HH:MM."""
    return f"{value.hour:02d}:{value.minute:02d}"
