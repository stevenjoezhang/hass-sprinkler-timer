"""Sensor platform for Sprinkler Timer."""

from __future__ import annotations

from datetime import datetime

from homeassistant.components.sensor import SensorDeviceClass, SensorEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.typing import StateType

from .const import DOMAIN
from .entity import SprinklerTimerEntity
from .scheduler import SprinklerTimerController


class SprinklerTimerNextRunSensor(SprinklerTimerEntity, SensorEntity):
    """Sensor showing the next nominal run time."""

    _attr_device_class = SensorDeviceClass.TIMESTAMP
    _attr_icon = "mdi:calendar-clock"

    def __init__(self, controller: SprinklerTimerController) -> None:
        super().__init__(controller, "next_run")

    @property
    def name(self) -> str:
        """Return entity name."""
        return f"{self.controller.name} 下次喷淋时间"

    @property
    def native_value(self) -> datetime | None:
        """Return the next run time."""
        return self.controller.next_run

    @property
    def extra_state_attributes(self) -> dict:
        """Return compact timer attributes."""
        return self.controller.extra_state_attributes


class SprinklerTimerLastDecisionSensor(SprinklerTimerEntity, SensorEntity):
    """Sensor showing the latest decision."""

    _attr_icon = "mdi:message-text-clock"

    def __init__(self, controller: SprinklerTimerController) -> None:
        super().__init__(controller, "last_decision")

    @property
    def name(self) -> str:
        """Return entity name."""
        return f"{self.controller.name} 最近决策"

    @property
    def native_value(self) -> StateType:
        """Return the last decision."""
        return self.controller.last_decision


async def async_setup_entry(
    hass: HomeAssistant,
    config_entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up Sprinkler Timer sensor entities."""
    controller: SprinklerTimerController = hass.data[DOMAIN][config_entry.entry_id]
    async_add_entities(
        [
            SprinklerTimerNextRunSensor(controller),
            SprinklerTimerLastDecisionSensor(controller),
        ]
    )
