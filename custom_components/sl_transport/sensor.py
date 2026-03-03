from homeassistant.components.sensor import SensorEntity, SensorDeviceClass, SensorStateClass
from homeassistant.components.binary_sensor import BinarySensorEntity
from homeassistant.helpers.update_coordinator import CoordinatorEntity
from .const import DOMAIN

class BaseSLEntity(CoordinatorEntity):
    @property
    def device_info(self):
        return {
            "identifiers": {(DOMAIN, self.config_entry.entry_id)},
            "name": f"SL {self.config_entry.data['type'].title()}",
            "manufacturer": "SL / Trafiklab",
        }

class SLTravelTimeSensor(BaseSLEntity, SensorEntity):
    _attr_name = "SL Travel Time"
    _attr_native_unit_of_measurement = "min"
    _attr_device_class = SensorDeviceClass.DURATION
    _attr_state_class = SensorStateClass.MEASUREMENT

    @property
    def native_value(self):
        return self.coordinator.data.get("duration")

class SLDisruptionsSensor(BaseSLEntity, BinarySensorEntity):
    _attr_name = "SL Disruptions"

    @property
    def is_on(self):
        return self.coordinator.data.get("count", 0) > 0

    @property
    def extra_state_attributes(self):
        return {"deviations": self.coordinator.data.get("deviations", [])}

class SLDeparturesSensor(BaseSLEntity, SensorEntity):
    _attr_name = "SL Next Departure"

    @property
    def native_value(self):
        d = self.coordinator.data
        if not d.get("next_time"):
            return "No data"
        return f"{d.get('line')} → {d.get('dest')}"

    @property
    def extra_state_attributes(self):
        return {"upcoming": self.coordinator.data.get("departures", [])}

SENSOR_TYPES = {
    "travel_time": SLTravelTimeSensor,
    "disruptions": SLDisruptionsSensor,
    "departures": SLDeparturesSensor,
}

async def async_setup_entry(hass, entry, async_add_entities):
    coord = hass.data[DOMAIN][entry.entry_id]
    sensor_class = SENSOR_TYPES[entry.data["type"]]
    async_add_entities([sensor_class(coord, entry)], True)
