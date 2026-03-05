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


class SLLineDepartureSensor(BaseSLEntity, SensorEntity):
    """Tracks next departures for a specific line + destination at a stop."""

    def __init__(self, coordinator, entry, line: str, destination: str):
        super().__init__(coordinator, entry)
        self._line = line
        self._destination = destination
        safe_line = line.replace(" ", "_").lower()
        safe_dest = destination.replace(" ", "_").lower()
        self._attr_unique_id = f"{DOMAIN}_{entry.entry_id}_{safe_line}_{safe_dest}"
        self._attr_name = f"{entry.title} {line} \u2192 {destination}"

    def _matching_departures(self):
        data = self.coordinator.data or {}
        return [
            dep for dep in data.get("departures", [])
            if dep.get("line", {}).get("designation") == self._line
            and dep.get("destination") == self._destination
        ]

    @property
    def native_value(self):
        deps = self._matching_departures()
        if not deps:
            return None
        next_dep = deps[0]
        return next_dep.get("display") or next_dep.get("expected") or next_dep.get("scheduled")

    @property
    def extra_state_attributes(self):
        data = self.coordinator.data or {}
        deps = self._matching_departures()
        upcoming = []
        for dep in deps:
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
        next_dep = deps[0] if deps else {}
        next_line_info = next_dep.get("line", {})
        return {
            "line": self._line,
            "transport_mode": next_line_info.get("transport_mode"),
            "destination": self._destination,
            "expected": next_dep.get("expected"),
            "scheduled": next_dep.get("scheduled"),
            "display": next_dep.get("display"),
            "state": next_dep.get("state"),
            "upcoming_departures": upcoming,
            "deviations": deviations,
            "deviation_count": data.get("deviation_count", 0),
        }


async def async_setup_entry(hass, entry, async_add_entities):
    entry_type = entry.data.get("type")
    coord = hass.data[DOMAIN][entry.entry_id]

    if entry_type == TYPE_TRAVEL_TIME:
        async_add_entities([SLTravelTimeSensor(coord, entry)], True)

    elif entry_type == TYPE_DEPARTURES:
        known_keys: set = set()

        def _discover_sensors():
            data = coord.data or {}
            new_sensors = []
            for dep in data.get("departures", []):
                line = dep.get("line", {}).get("designation")
                dest = dep.get("destination")
                if line and dest:
                    key = (line, dest)
                    if key not in known_keys:
                        known_keys.add(key)
                        new_sensors.append(SLLineDepartureSensor(coord, entry, line, dest))
            if new_sensors:
                async_add_entities(new_sensors)

        # Discover from data already available after first_refresh in __init__.py
        _discover_sensors()

        # Re-run discovery on each coordinator update to catch any new line+destination combos
        entry.async_on_unload(coord.async_add_listener(_discover_sensors))
