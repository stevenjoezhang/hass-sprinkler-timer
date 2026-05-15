"""Scheduler and runtime state for Sprinkler Timer."""

from __future__ import annotations

from collections.abc import Callable
from datetime import date, datetime, time, timedelta
import logging
from typing import Any

from homeassistant.const import ATTR_ENTITY_ID, CONF_LATITUDE, CONF_LONGITUDE
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import CALLBACK_TYPE, HomeAssistant, callback
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.event import async_call_later, async_track_point_in_time
from homeassistant.helpers.storage import Store
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
from .qweather import QWeatherClient, QWeatherError

_LOGGER = logging.getLogger(__name__)

RAIN_FORECAST_HOURS = 12
RAIN_PAST_HOURS = 12
RAIN_FUTURE_HOURS = 12
RAIN_TIMELINE_KEEP_HOURS = 72
RAIN_REFRESH_SECONDS = 3600
STORE_VERSION = 1


class SprinklerTimerController:
    """Run one sprinkler timer config entry."""

    def __init__(self, hass: HomeAssistant, entry: ConfigEntry) -> None:
        self.hass = hass
        self.entry = entry
        self._listeners: list[Callable[[], None]] = []
        self._remove_next_run: CALLBACK_TYPE | None = None
        self._remove_stop: CALLBACK_TYPE | None = None
        self._remove_refresh: CALLBACK_TYPE | None = None
        self._running = False
        self._next_run: datetime | None = None
        self._last_decision = "尚未执行"
        self._forecast_warning: str | None = None
        self._last_rain_12h: float | None = None
        self._rain_window_total: float | None = None
        self._last_forecast_update: datetime | None = None
        self._rain_timeline: dict[str, float] = {}
        self._store: Store[dict[str, Any]] = Store(
            hass,
            STORE_VERSION,
            f"{DOMAIN}.{entry.entry_id}.rain_timeline",
            private=True,
        )

    async def async_setup(self) -> None:
        """Set up the controller."""
        await self._async_load_rain_timeline()
        self.async_schedule_next_run()
        self._schedule_forecast_refresh(soon=True)

    async def async_unload(self) -> None:
        """Unload the controller and cancel callbacks."""
        self._cancel_callbacks()
        if self._running:
            await self._async_turn_sprinklers_off()
            self._running = False
        await self._async_save_rain_timeline()
        self._listeners.clear()

    @property
    def options(self) -> dict[str, Any]:
        """Return merged options for this timer."""
        return {
            CONF_ENABLED: DEFAULT_ENABLED,
            CONF_DURATION_MINUTES: DEFAULT_DURATION_MINUTES,
            CONF_RAIN_SKIP: DEFAULT_RAIN_SKIP,
            CONF_RAIN_THRESHOLD: DEFAULT_RAIN_THRESHOLD,
            CONF_REPEAT_DAYS: DEFAULT_REPEAT_DAYS,
            CONF_START_TIMES: list(DEFAULT_START_TIMES),
            **dict(self.entry.options),
        }

    @property
    def name(self) -> str:
        """Return the timer name."""
        return str(self.options.get(CONF_PLAN_NAME) or self.entry.title)

    @property
    def enabled(self) -> bool:
        """Return whether the timer is enabled."""
        return bool(self.options.get(CONF_ENABLED, DEFAULT_ENABLED))

    @property
    def next_run(self) -> datetime | None:
        """Return the next scheduled run."""
        return self._next_run

    @property
    def last_decision(self) -> str:
        """Return the latest scheduling decision."""
        return self._last_decision

    @property
    def last_rain_12h(self) -> float | None:
        """Return the latest fetched 12-hour rain amount."""
        return self._last_rain_12h

    @property
    def rain_window_total(self) -> float | None:
        """Return the current past/future rain window total."""
        return self._rain_window_total

    @property
    def running(self) -> bool:
        """Return whether this controller is currently watering."""
        return self._running

    @property
    def scheduled_times(self) -> list[str]:
        """Return configured start times."""
        return list(self.options.get(CONF_START_TIMES, DEFAULT_START_TIMES))

    @callback
    def async_add_listener(self, listener: Callable[[], None]) -> CALLBACK_TYPE:
        """Add a state listener."""
        self._listeners.append(listener)

        @callback
        def remove_listener() -> None:
            if listener in self._listeners:
                self._listeners.remove(listener)

        return remove_listener

    @callback
    def async_options_updated(self) -> None:
        """Handle changed config entry options."""
        self.async_schedule_next_run()
        self._schedule_forecast_refresh(soon=True)

    @callback
    def async_schedule_next_run(self) -> None:
        """Schedule the next watering callback."""
        if self._remove_next_run is not None:
            self._remove_next_run()
            self._remove_next_run = None

        self._next_run = self._calculate_next_run()
        if self.enabled and self._next_run is not None:
            self._remove_next_run = async_track_point_in_time(
                self.hass, self._async_handle_scheduled_run, self._next_run
            )

        self._notify_listeners()

    async def async_set_enabled(self, enabled: bool) -> None:
        """Persist and apply the enabled switch state."""
        options = self.options
        options[CONF_ENABLED] = enabled
        self.hass.config_entries.async_update_entry(self.entry, options=options)

    async def _async_handle_scheduled_run(self, now: datetime) -> None:
        """Handle a scheduled watering time."""
        self._remove_next_run = None
        self._forecast_warning = None

        if not self.enabled:
            self._last_decision = "已跳过：定时器已关闭"
            self.async_schedule_next_run()
            return

        if self._running:
            self._last_decision = "已跳过：上一次喷淋仍在运行"
            self.async_schedule_next_run()
            return

        options = self.options
        if options.get(CONF_RAIN_SKIP, DEFAULT_RAIN_SKIP):
            try:
                await self._async_refresh_forecast()
            except QWeatherError as err:
                _LOGGER.warning("Unable to refresh rain forecast: %s", err)
                self._forecast_warning = f"无法获取降雨预报（{err}）"

            rain_window_total = self._calculate_rain_window_total(now)
            threshold = float(options.get(CONF_RAIN_THRESHOLD, DEFAULT_RAIN_THRESHOLD))
            if rain_window_total >= threshold:
                self._last_decision = (
                    f"已跳过：过去 12 小时到未来 12 小时累计降雨 "
                    f"{rain_window_total:.1f} mm，"
                    f"达到阈值 {threshold:g} mm"
                )
                self.async_schedule_next_run()
                return

        await self._async_start_watering(now)

    async def _async_start_watering(self, now: datetime) -> None:
        """Turn sprinklers on and schedule stop."""
        duration = float(
            self.options.get(CONF_DURATION_MINUTES, DEFAULT_DURATION_MINUTES)
        )
        switches = self._configured_switches()
        if not switches:
            self._last_decision = "已跳过：没有绑定喷淋开关"
            self.async_schedule_next_run()
            return

        try:
            await self.hass.services.async_call(
                "switch",
                "turn_on",
                {ATTR_ENTITY_ID: switches},
                blocking=True,
            )
        except Exception as err:  # noqa: BLE001
            self._last_decision = f"启动失败：{err}"
            _LOGGER.exception("Failed to turn on sprinkler switches")
            self.async_schedule_next_run()
            return

        self._running = True
        self._last_decision = self._format_decision_message(
            f"已执行：{dt_util.as_local(now).strftime('%Y-%m-%d %H:%M')} "
            f"开始喷淋 {duration:g} 分钟"
        )
        self._notify_listeners()

        if self._remove_stop is not None:
            self._remove_stop()
        self._remove_stop = async_call_later(
            self.hass,
            timedelta(minutes=duration),
            self._async_stop_after_duration,
        )

    async def _async_stop_after_duration(self, now: datetime) -> None:
        """Stop sprinklers after the configured duration."""
        self._remove_stop = None
        await self._async_turn_sprinklers_off()
        self._running = False
        self._last_decision = self._format_decision_message(
            f"已完成：{dt_util.as_local(now).strftime('%Y-%m-%d %H:%M')} 停止喷淋"
        )
        self.async_schedule_next_run()

    async def _async_turn_sprinklers_off(self) -> None:
        """Turn all configured sprinklers off."""
        switches = self._configured_switches()
        if not switches:
            return
        try:
            await self.hass.services.async_call(
                "switch",
                "turn_off",
                {ATTR_ENTITY_ID: switches},
                blocking=True,
            )
        except Exception:  # noqa: BLE001
            _LOGGER.exception("Failed to turn off sprinkler switches")

    async def _async_refresh_forecast(self, now: datetime | None = None) -> None:
        """Fetch future rain and merge it into the local rain timeline."""
        options = self.options
        if not options.get(CONF_RAIN_SKIP, DEFAULT_RAIN_SKIP):
            return

        now = dt_util.as_local(now or dt_util.now())
        client = QWeatherClient(
            async_get_clientsession(self.hass),
            str(options[CONF_API_KEY]),
            float(options[CONF_LATITUDE]),
            float(options[CONF_LONGITUDE]),
            str(options.get(CONF_API_HOST, DEFAULT_QWEATHER_HOST)),
        )
        forecast = await client.async_get_hourly_rain(RAIN_FORECAST_HOURS)

        self._forecast_warning = None
        self._last_rain_12h = sum(forecast.values())
        current_hour = self._hour_start(now)
        for forecast_time, rain in forecast.items():
            local_hour = self._hour_start(dt_util.as_local(forecast_time))
            # Future forecast can roll forward every hour; past slots remain frozen.
            if local_hour >= current_hour:
                self._rain_timeline[self._hour_key(local_hour)] = rain

        self._last_forecast_update = now
        self._prune_rain_timeline(now)
        self._rain_window_total = self._calculate_rain_window_total(now)
        await self._async_save_rain_timeline()
        self._notify_listeners()

    def _calculate_next_run(self) -> datetime | None:
        """Calculate the next nominal run time."""
        if not self.enabled:
            return None

        start_times = self._start_times()
        if not start_times:
            return None

        now = dt_util.now()
        anchor = self._anchor_date()
        repeat_days = max(1, int(self.options.get(CONF_REPEAT_DAYS, DEFAULT_REPEAT_DAYS)))

        for offset in range(0, repeat_days + 370):
            candidate_date = now.date() + timedelta(days=offset)
            days_since_anchor = (candidate_date - anchor).days
            if days_since_anchor < 0 or days_since_anchor % repeat_days != 0:
                continue
            for start_time in start_times:
                candidate = datetime.combine(
                    candidate_date, start_time, tzinfo=dt_util.DEFAULT_TIME_ZONE
                )
                if candidate > now:
                    return candidate
        return None

    def _anchor_date(self) -> date:
        """Return the hidden repeat-cycle anchor date."""
        raw = self.entry.data.get(CONF_CREATED_DATE)
        if isinstance(raw, str):
            try:
                return date.fromisoformat(raw)
            except ValueError:
                pass
        return dt_util.now().date()

    def _start_times(self) -> list[time]:
        """Return configured start times as sorted time objects."""
        parsed: list[time] = []
        for raw in self.options.get(CONF_START_TIMES, DEFAULT_START_TIMES):
            try:
                parsed.append(parse_time(str(raw)))
            except (TypeError, ValueError):
                _LOGGER.warning("Ignoring invalid sprinkler start time: %s", raw)
        return sorted(parsed)

    def _calculate_rain_window_total(self, now: datetime | None = None) -> float:
        """Return rain total for the past 12h plus future 12h window."""
        now = dt_util.as_local(now or dt_util.now())
        current_hour = self._hour_start(now)
        total = 0.0
        for offset in range(-RAIN_PAST_HOURS, RAIN_FUTURE_HOURS):
            hour = current_hour + timedelta(hours=offset)
            total += float(self._rain_timeline.get(self._hour_key(hour), 0.0))
        self._rain_window_total = total
        return total

    def _configured_switches(self) -> list[str]:
        """Return configured switch entity ids."""
        switches = self.options.get(CONF_SPRINKLER_SWITCHES, [])
        if not isinstance(switches, list):
            return []

        registry = er.async_get(self.hass)
        resolved: list[str] = []
        for entity_id_or_uuid in switches:
            try:
                entity_id = er.async_validate_entity_id(registry, entity_id_or_uuid)
            except vol.Invalid:
                _LOGGER.warning(
                    "Ignoring unknown sprinkler switch: %s", entity_id_or_uuid
                )
                continue
            if entity_id:
                resolved.append(entity_id)
        return resolved

    def _format_decision_message(self, message: str) -> str:
        """Append forecast warning to visible decision text when present."""
        if not self._forecast_warning:
            return message
        return f"{message}；{self._forecast_warning}，已按无雨继续喷淋"

    def _cancel_callbacks(self) -> None:
        """Cancel pending callbacks."""
        if self._remove_next_run is not None:
            self._remove_next_run()
            self._remove_next_run = None
        if self._remove_stop is not None:
            self._remove_stop()
            self._remove_stop = None
        if self._remove_refresh is not None:
            self._remove_refresh()
            self._remove_refresh = None

    @callback
    def _schedule_forecast_refresh(self, soon: bool = False) -> None:
        """Schedule the next hourly forecast refresh."""
        if self._remove_refresh is not None:
            self._remove_refresh()
            self._remove_refresh = None

        delay = 5 if soon else RAIN_REFRESH_SECONDS
        self._remove_refresh = async_call_later(
            self.hass,
            delay,
            self._async_handle_forecast_refresh,
        )

    async def _async_handle_forecast_refresh(self, now: datetime) -> None:
        """Refresh forecast and reschedule hourly refresh."""
        self._remove_refresh = None
        try:
            await self._async_refresh_forecast(now)
        except QWeatherError as err:
            _LOGGER.warning("Unable to refresh rain forecast: %s", err)
        finally:
            self._schedule_forecast_refresh()

    async def _async_load_rain_timeline(self) -> None:
        """Load persisted rain timeline."""
        data = await self._store.async_load()
        if not isinstance(data, dict):
            return

        timeline = data.get("timeline")
        if isinstance(timeline, dict):
            self._rain_timeline = {
                str(key): float(value)
                for key, value in timeline.items()
                if isinstance(value, int | float)
            }

        last_update = data.get("last_forecast_update")
        if isinstance(last_update, str):
            self._last_forecast_update = dt_util.parse_datetime(last_update)

        last_rain_12h = data.get("last_rain_12h")
        if isinstance(last_rain_12h, int | float):
            self._last_rain_12h = float(last_rain_12h)

        self._prune_rain_timeline()
        self._calculate_rain_window_total()

    async def _async_save_rain_timeline(self) -> None:
        """Persist rain timeline."""
        await self._store.async_save(
            {
                "timeline": self._rain_timeline,
                "last_forecast_update": (
                    self._last_forecast_update.isoformat()
                    if self._last_forecast_update
                    else None
                ),
                "last_rain_12h": self._last_rain_12h,
            }
        )

    def _prune_rain_timeline(self, now: datetime | None = None) -> None:
        """Keep only a bounded rain timeline."""
        now = dt_util.as_local(now or dt_util.now())
        current_hour = self._hour_start(now)
        start = current_hour - timedelta(hours=RAIN_TIMELINE_KEEP_HOURS)
        end = current_hour + timedelta(hours=RAIN_TIMELINE_KEEP_HOURS)

        pruned: dict[str, float] = {}
        for key, value in self._rain_timeline.items():
            parsed = dt_util.parse_datetime(key)
            if parsed is None:
                continue
            hour = self._hour_start(dt_util.as_local(parsed))
            if start <= hour <= end:
                pruned[self._hour_key(hour)] = float(value)
        self._rain_timeline = pruned

    @staticmethod
    def _hour_start(value: datetime) -> datetime:
        """Round a datetime down to the hour."""
        return value.replace(minute=0, second=0, microsecond=0)

    @staticmethod
    def _hour_key(value: datetime) -> str:
        """Return stable storage key for an hourly slot."""
        return value.isoformat()

    @callback
    def _notify_listeners(self) -> None:
        """Notify entities that state changed."""
        for listener in list(self._listeners):
            listener()

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Return useful debugging attributes for the sparse exposed entities."""
        return {
            "scheduled_times": [format_time(value) for value in self._start_times()],
            "sprinkler_switches": self._configured_switches(),
            "last_rain_12h_mm": self._last_rain_12h,
            "rain_window_total_mm": self._rain_window_total,
            "last_forecast_update": (
                self._last_forecast_update.isoformat()
                if self._last_forecast_update
                else None
            ),
            "running": self._running,
        }
