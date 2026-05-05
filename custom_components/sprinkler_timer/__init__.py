"""Sprinkler Timer integration."""

from __future__ import annotations

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant

from .const import DOMAIN, PLATFORMS
from .scheduler import SprinklerTimerController


async def async_setup(hass: HomeAssistant, config: dict) -> bool:
    """Set up the Sprinkler Timer integration."""
    hass.data.setdefault(DOMAIN, {})
    return True


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up one sprinkler timer."""
    controller = SprinklerTimerController(hass, entry)
    await controller.async_setup()

    hass.data.setdefault(DOMAIN, {})[entry.entry_id] = controller

    async def _async_update_listener(
        hass: HomeAssistant, updated_entry: ConfigEntry
    ) -> None:
        controller.async_options_updated()

    entry.async_on_unload(entry.add_update_listener(_async_update_listener))

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload one sprinkler timer."""
    unload_ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)

    controller: SprinklerTimerController | None = hass.data[DOMAIN].pop(
        entry.entry_id, None
    )
    if controller is not None:
        await controller.async_unload()

    return unload_ok
