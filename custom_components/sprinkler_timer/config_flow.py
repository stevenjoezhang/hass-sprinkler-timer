"""Config flow for Sprinkler Timer."""

from __future__ import annotations

import re
from typing import Any
from uuid import uuid4

from homeassistant import config_entries
from homeassistant.const import CONF_LATITUDE, CONF_LONGITUDE
from homeassistant.core import callback
from homeassistant.helpers import selector
from homeassistant.util import dt as dt_util
import voluptuous as vol

from .const import (
    CONF_API_KEY,
    CONF_API_HOST,
    CONF_CREATED_DATE,
    CONF_DURATION_MINUTES,
    CONF_ENABLED,
    CONF_PLAN_NAME,
    CONF_RAIN_SKIP,
    CONF_RAIN_THRESHOLD,
    CONF_REPEAT_DAYS,
    CONF_SPRINKLER_SWITCHES,
    CONF_START_TIMES,
    DEFAULT_DURATION_MINUTES,
    DEFAULT_ENABLED,
    DEFAULT_QWEATHER_HOST,
    DEFAULT_RAIN_SKIP,
    DEFAULT_RAIN_THRESHOLD,
    DEFAULT_REPEAT_DAYS,
    DEFAULT_START_TIMES,
    DOMAIN,
    format_time,
    parse_time,
)

TIME_RE = re.compile(r"^\d{1,2}:\d{2}$")


class ConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle a Sprinkler Timer config flow."""

    VERSION = 1

    @staticmethod
    @callback
    def async_get_options_flow(
        config_entry: config_entries.ConfigEntry,
    ) -> config_entries.OptionsFlow:
        """Create the options flow."""
        return SprinklerTimerOptionsFlow()

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> config_entries.ConfigFlowResult:
        """Create one sprinkler timer."""
        errors: dict[str, str] = {}

        if user_input is not None:
            try:
                options = _normalize_input(user_input)
            except vol.Invalid:
                errors["base"] = "invalid_input"
            else:
                await self.async_set_unique_id(str(uuid4()))
                return self.async_create_entry(
                    title=options[CONF_PLAN_NAME],
                    data={CONF_CREATED_DATE: dt_util.now().date().isoformat()},
                    options=options,
                )

        return self.async_show_form(
            step_id="user",
            data_schema=_schema(self.hass, {}),
            errors=errors,
        )


class SprinklerTimerOptionsFlow(config_entries.OptionsFlow):
    """Handle Sprinkler Timer options."""

    async def async_step_init(
        self, user_input: dict[str, Any] | None = None
    ) -> config_entries.ConfigFlowResult:
        """Edit one sprinkler timer."""
        errors: dict[str, str] = {}

        if user_input is not None:
            try:
                options = _normalize_input(user_input)
            except vol.Invalid:
                errors["base"] = "invalid_input"
            else:
                self.hass.config_entries.async_update_entry(
                    self.config_entry,
                    title=options[CONF_PLAN_NAME],
                    options=options,
                )
                return self.async_create_entry(title="", data=options)

        return self.async_show_form(
            step_id="init",
            data_schema=_schema(self.hass, dict(self.config_entry.options)),
            errors=errors,
        )


def _schema(hass, existing: dict[str, Any]) -> vol.Schema:
    """Build the shared create/edit schema."""
    defaults = {
        CONF_PLAN_NAME: existing.get(CONF_PLAN_NAME, "庭院喷淋"),
        CONF_SPRINKLER_SWITCHES: existing.get(CONF_SPRINKLER_SWITCHES, []),
        CONF_API_KEY: existing.get(CONF_API_KEY, ""),
        CONF_API_HOST: existing.get(CONF_API_HOST, DEFAULT_QWEATHER_HOST),
        CONF_LATITUDE: existing.get(CONF_LATITUDE, round(hass.config.latitude, 3)),
        CONF_LONGITUDE: existing.get(CONF_LONGITUDE, round(hass.config.longitude, 3)),
        CONF_RAIN_SKIP: existing.get(CONF_RAIN_SKIP, DEFAULT_RAIN_SKIP),
        CONF_RAIN_THRESHOLD: existing.get(
            CONF_RAIN_THRESHOLD, DEFAULT_RAIN_THRESHOLD
        ),
        CONF_START_TIMES: ", ".join(
            existing.get(CONF_START_TIMES, DEFAULT_START_TIMES)
        ),
        CONF_DURATION_MINUTES: existing.get(
            CONF_DURATION_MINUTES, DEFAULT_DURATION_MINUTES
        ),
        CONF_REPEAT_DAYS: existing.get(CONF_REPEAT_DAYS, DEFAULT_REPEAT_DAYS),
        CONF_ENABLED: existing.get(CONF_ENABLED, DEFAULT_ENABLED),
    }

    return vol.Schema(
        {
            vol.Required(
                CONF_PLAN_NAME, default=defaults[CONF_PLAN_NAME]
            ): selector.TextSelector(),
            vol.Required(
                CONF_SPRINKLER_SWITCHES,
                default=defaults[CONF_SPRINKLER_SWITCHES],
            ): selector.EntitySelector(
                selector.EntitySelectorConfig(
                    domain="switch",
                    multiple=True,
                    reorder=True,
                )
            ),
            vol.Required(
                CONF_API_KEY, default=defaults[CONF_API_KEY]
            ): selector.TextSelector(),
            vol.Required(
                CONF_API_HOST, default=defaults[CONF_API_HOST]
            ): selector.TextSelector(),
            vol.Required(
                CONF_LATITUDE,
                default=defaults[CONF_LATITUDE],
            ): selector.NumberSelector(
                selector.NumberSelectorConfig(
                    min=-90,
                    max=90,
                    step=0.001,
                    mode=selector.NumberSelectorMode.BOX,
                )
            ),
            vol.Required(
                CONF_LONGITUDE,
                default=defaults[CONF_LONGITUDE],
            ): selector.NumberSelector(
                selector.NumberSelectorConfig(
                    min=-180,
                    max=180,
                    step=0.001,
                    mode=selector.NumberSelectorMode.BOX,
                )
            ),
            vol.Required(
                CONF_RAIN_SKIP,
                default=defaults[CONF_RAIN_SKIP],
            ): selector.BooleanSelector(),
            vol.Required(
                CONF_RAIN_THRESHOLD,
                default=defaults[CONF_RAIN_THRESHOLD],
            ): selector.NumberSelector(
                selector.NumberSelectorConfig(
                    min=0,
                    max=100,
                    step=0.1,
                    mode=selector.NumberSelectorMode.BOX,
                    unit_of_measurement="mm",
                )
            ),
            vol.Required(
                CONF_START_TIMES,
                default=defaults[CONF_START_TIMES],
            ): selector.TextSelector(),
            vol.Required(
                CONF_DURATION_MINUTES,
                default=defaults[CONF_DURATION_MINUTES],
            ): selector.NumberSelector(
                selector.NumberSelectorConfig(
                    min=1,
                    max=240,
                    step=1,
                    mode=selector.NumberSelectorMode.BOX,
                    unit_of_measurement="min",
                )
            ),
            vol.Required(
                CONF_REPEAT_DAYS,
                default=defaults[CONF_REPEAT_DAYS],
            ): selector.NumberSelector(
                selector.NumberSelectorConfig(
                    min=1,
                    max=365,
                    step=1,
                    mode=selector.NumberSelectorMode.BOX,
                    unit_of_measurement="d",
                )
            ),
            vol.Required(
                CONF_ENABLED, default=defaults[CONF_ENABLED]
            ): selector.BooleanSelector(),
        }
    )


def _normalize_input(user_input: dict[str, Any]) -> dict[str, Any]:
    """Validate and normalize user input before storing it."""
    plan_name = str(user_input[CONF_PLAN_NAME]).strip()
    if not plan_name:
        raise vol.Invalid("计划名称不能为空")

    switches = user_input.get(CONF_SPRINKLER_SWITCHES) or []
    if not isinstance(switches, list) or not switches:
        raise vol.Invalid("至少需要绑定一个喷淋 switch")

    api_key = str(user_input[CONF_API_KEY]).strip()
    if not api_key:
        raise vol.Invalid("和风天气 API Key 不能为空")

    api_host = str(user_input[CONF_API_HOST]).strip().rstrip("/")
    if not api_host.startswith(("https://", "http://")):
        raise vol.Invalid("和风天气 API Host 必须以 http:// 或 https:// 开头")

    start_times = _parse_start_times(str(user_input[CONF_START_TIMES]))

    return {
        CONF_PLAN_NAME: plan_name,
        CONF_SPRINKLER_SWITCHES: switches,
        CONF_API_KEY: api_key,
        CONF_API_HOST: api_host,
        CONF_LATITUDE: float(user_input[CONF_LATITUDE]),
        CONF_LONGITUDE: float(user_input[CONF_LONGITUDE]),
        CONF_RAIN_SKIP: bool(user_input[CONF_RAIN_SKIP]),
        CONF_RAIN_THRESHOLD: float(user_input[CONF_RAIN_THRESHOLD]),
        CONF_START_TIMES: start_times,
        CONF_DURATION_MINUTES: int(float(user_input[CONF_DURATION_MINUTES])),
        CONF_REPEAT_DAYS: int(float(user_input[CONF_REPEAT_DAYS])),
        CONF_ENABLED: bool(user_input[CONF_ENABLED]),
    }


def _parse_start_times(raw: str) -> list[str]:
    """Parse comma-separated HH:MM start times."""
    normalized = raw.replace("，", ",")
    parts = [part.strip() for part in normalized.split(",") if part.strip()]
    if not parts:
        raise vol.Invalid("至少需要设置一个开始时间")

    parsed = []
    for part in parts:
        if not TIME_RE.match(part):
            raise vol.Invalid("开始时间请使用 HH:MM 格式，多个时间用逗号分隔")
        try:
            parsed.append(parse_time(part))
        except ValueError as err:
            raise vol.Invalid("开始时间超出有效范围") from err

    unique = sorted({format_time(value) for value in parsed}, key=parse_time)
    return unique
