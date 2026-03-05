from homeassistant.components.binary_sensor import BinarySensorEntity, BinarySensorDeviceClass
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN, TYPE_DISRUPTIONS, TYPE_DEPARTURES


class SLDeviationsBinarySensor(CoordinatorEntity, BinarySensorEntity):
    """Binary sensor that is ON when active deviations exist for a stop or all of SL."""

    _attr_device_class = BinarySensorDeviceClass.PROBLEM

    def __init__(self, coordinator, entry):
        super().__init__(coordinator)
        self.config_entry = entry
        site_id = entry.data.get("site_id", "")
        self._attr_name = entry.title
        self._attr_unique_id = f"{DOMAIN}_{entry.entry_id}_deviations"

    @property
    def is_on(self):
        data = self.coordinator.data or {}
        return data.get("count", 0) > 0 or data.get("deviation_count", 0) > 0

    @property
    def extra_state_attributes(self):
        data = self.coordinator.data or {}
        deviations = data.get("deviations", [])
        attrs = {"deviation_count": len(deviations)}
        # Flatten message_variants for readability
        messages = []
        for dev in deviations:
            for variant in dev.get("message_variants", []):
                if variant.get("language", "sv") in ("sv", "en"):
                    messages.append(
                        {
                            "header": variant.get("header"),
                            "details": variant.get("details"),
                            "scope_alias": variant.get("scope_alias"),
                        }
                    )
                    break
            else:
                messages.append({"deviation_case_id": dev.get("deviation_case_id")})
        attrs["deviations"] = messages
        # Expose each deviation as numbered flat attributes for dashboard card use
        for i, msg in enumerate(messages, start=1):
            attrs[f"deviation_{i}_header"] = msg.get("header")
            attrs[f"deviation_{i}_details"] = msg.get("details")
            attrs[f"deviation_{i}_scope_alias"] = msg.get("scope_alias")
        return attrs

    @property
    def device_info(self):
        return {
            "identifiers": {(DOMAIN, self.config_entry.entry_id)},
            "name": self.config_entry.title,
            "manufacturer": "SL / Trafiklab",
        }


async def async_setup_entry(hass, entry, async_add_entities):
    if entry.data.get("type") not in (TYPE_DISRUPTIONS, TYPE_DEPARTURES):
        return
    coord = hass.data[DOMAIN][entry.entry_id]
    async_add_entities([SLDeviationsBinarySensor(coord, entry)], True)
