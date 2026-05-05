"""Switch platform for Sprinkler Timer."""

from __future__ import annotations

from homeassistant.components.switch import SwitchEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import DOMAIN
from .entity import SprinklerTimerEntity
from .scheduler import SprinklerTimerController


class SprinklerTimerEnabledSwitch(SprinklerTimerEntity, SwitchEntity):
    """Enable or disable one sprinkler timer."""

    _attr_icon = "mdi:sprinkler-variant"

    def __init__(self, controller: SprinklerTimerController) -> None:
        super().__init__(controller, "enabled")

    @property
    def name(self) -> str:
        """Return entity name."""
        return f"{self.controller.name} 定时器开关"

    @property
    def is_on(self) -> bool:
        """Return whether this timer is enabled."""
        return self.controller.enabled

    @property
    def extra_state_attributes(self) -> dict:
        """Return compact timer attributes."""
        return self.controller.extra_state_attributes

    async def async_turn_on(self, **kwargs) -> None:
        """Enable the timer."""
        await self.controller.async_set_enabled(True)

    async def async_turn_off(self, **kwargs) -> None:
        """Disable the timer."""
        await self.controller.async_set_enabled(False)


async def async_setup_entry(
    hass: HomeAssistant,
    config_entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up Sprinkler Timer switch entities."""
    controller: SprinklerTimerController = hass.data[DOMAIN][config_entry.entry_id]
    async_add_entities([SprinklerTimerEnabledSwitch(controller)])
