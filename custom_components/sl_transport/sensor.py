from homeassistant.components.sensor import SensorEntity, SensorDeviceClass, SensorStateClass
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN, TYPE_TRAVEL_TIME, TYPE_DEPARTURES


class BaseSLEntity(CoordinatorEntity):
    def __init__(self, coordinator, entry):
        super().__init__(coordinator)
        self.config_entry = entry

    @property
    def device_info(self):
        return {
            "identifiers": {(DOMAIN, self.config_entry.entry_id)},
            "name": self.config_entry.title,
            "manufacturer": "SL / Trafiklab",
        }


class SLTravelTimeSensor(BaseSLEntity, SensorEntity):
    _attr_native_unit_of_measurement = "min"
    _attr_device_class = SensorDeviceClass.DURATION
    _attr_state_class = SensorStateClass.MEASUREMENT

    def __init__(self, coordinator, entry):
        super().__init__(coordinator, entry)
        self._attr_name = entry.title
        self._attr_unique_id = f"{DOMAIN}_{entry.entry_id}_travel_time"

    @property
    def native_value(self):
        return (self.coordinator.data or {}).get("duration")

    @property
    def extra_state_attributes(self):
        data = self.coordinator.data or {}
        return {
            "origin": data.get("origin"),
            "destination": data.get("destination"),
            "interchanges": data.get("interchanges"),
        }


class SLDeparturesSensor(BaseSLEntity, SensorEntity):
    def __init__(self, coordinator, entry):
        super().__init__(coordinator, entry)
        self._attr_name = entry.title
        self._attr_unique_id = f"{DOMAIN}_{entry.entry_id}_departures"

    @property
    def native_value(self):
        data = self.coordinator.data or {}
        line = data.get("line")
        dest = data.get("dest")
        display = data.get("display")
        if not line and not dest:
            return "No data"
        parts = []
        if line:
            parts.append(line)
        if dest:
            parts.append(f"→ {dest}")
        if display:
            parts.append(f"({display})")
        return " ".join(parts)

    @property
    def extra_state_attributes(self):
        data = self.coordinator.data or {}
        upcoming = []
        for dep in data.get("departures", []):
            line_info = dep.get("line", {})
            upcoming.append(
                {
                    "line": line_info.get("designation"),
                    "transport_mode": line_info.get("transport_mode"),
                    "destination": dep.get("destination"),
                    "expected": dep.get("expected"),
                    "scheduled": dep.get("scheduled"),
                    "display": dep.get("display"),
                    "state": dep.get("state"),
                }
            )
        deviations = []
        for dev in data.get("deviations", []):
            for variant in dev.get("message_variants", []):
                if variant.get("language", "sv") in ("sv", "en"):
                    deviations.append(
                        {
                            "header": variant.get("header"),
                            "details": variant.get("details"),
                        }
                    )
                    break
        return {
            "upcoming_departures": upcoming,
            "deviations": deviations,
            "deviation_count": data.get("deviation_count", 0),
        }


SENSOR_TYPES = {
    TYPE_TRAVEL_TIME: SLTravelTimeSensor,
    TYPE_DEPARTURES: SLDeparturesSensor,
}


async def async_setup_entry(hass, entry, async_add_entities):
    entry_type = entry.data.get("type")
    if entry_type not in SENSOR_TYPES:
        return
    coord = hass.data[DOMAIN][entry.entry_id]
    sensor_class = SENSOR_TYPES[entry_type]
    async_add_entities([sensor_class(coord, entry)], True)
