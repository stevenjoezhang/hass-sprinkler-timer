"""Shared entity helpers for Sprinkler Timer."""

from __future__ import annotations

from homeassistant.core import CALLBACK_TYPE
from homeassistant.helpers.entity import DeviceInfo, Entity

from .const import DOMAIN
from .scheduler import SprinklerTimerController


class SprinklerTimerEntity(Entity):
    """Base class for Sprinkler Timer entities."""

    _attr_should_poll = False

    def __init__(self, controller: SprinklerTimerController, suffix: str) -> None:
        self.controller = controller
        self._suffix = suffix
        self._remove_listener: CALLBACK_TYPE | None = None
        self._attr_unique_id = f"{controller.entry.entry_id}_{suffix}"

    @property
    def device_info(self) -> DeviceInfo:
        """Return device info for this timer."""
        return DeviceInfo(
            identifiers={(DOMAIN, self.controller.entry.entry_id)},
            name=self.controller.name,
            manufacturer="Sprinkler Timer",
            model="Timer",
        )

    async def async_added_to_hass(self) -> None:
        """Subscribe to controller updates."""
        self._remove_listener = self.controller.async_add_listener(
            self.async_write_ha_state
        )

    async def async_will_remove_from_hass(self) -> None:
        """Unsubscribe from controller updates."""
        if self._remove_listener is not None:
            self._remove_listener()
            self._remove_listener = None
