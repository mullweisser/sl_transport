import aiohttp
import logging
from datetime import timedelta
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .const import DOMAIN

_LOGGER = logging.getLogger(__name__)

class SLCoordinator(DataUpdateCoordinator):
    def __init__(self, hass, session: aiohttp.ClientSession, config_type: str, data: dict, update_interval: timedelta):
        super().__init__(
            hass,
            _LOGGER,
            name=DOMAIN,
            update_interval=update_interval,
        )
        self.session = session
        self.config_type = config_type
        self.config_data = data

    async def _async_update_data(self):
        try:
            if self.config_type == "travel_time":
                return await self._fetch_travel_time()
            elif self.config_type == "disruptions":
                return await self._fetch_disruptions()
            elif self.config_type == "departures":
                return await self._fetch_departures()
        except Exception as err:
            raise UpdateFailed(f"Error fetching SL data: {err}") from err

    async def _fetch_travel_time(self):
        url = "https://journeyplanner.integration.sl.se/v2/trips"
        params = {
            "name_origin": self.config_data["origin"],
            "name_destination": self.config_data["destination"],
            "type_origin": "any",
            "type_destination": "any",
            "calc_number_of_trips": 1,
            # Add modes: e.g. &incl_mot_1=true for metro etc. — extend later
        }
        async with self.session.get(url, params=params, timeout=15) as resp:
            if resp.status != 200:
                raise Exception(f"HTTP {resp.status}")
            data = await resp.json()
            if not data.get("trips"):
                return {"duration": None}
            trip = data["trips"][0]
            return {"duration": trip.get("duration") // 60}  # minutes

    async def _fetch_disruptions(self):
        url = "https://deviations.integration.sl.se/v1/messages"
        params = {"site": self.config_data["site_id"], "future": "true"}
        async with self.session.get(url, params=params, timeout=10) as resp:
            if resp.status != 200:
                raise Exception(f"HTTP {resp.status}")
            data = await resp.json()
            active = [d for d in data if d.get("mainNews")]
            return {"deviations": active, "count": len(active)}

    async def _fetch_departures(self):
        url = f"https://transport.integration.sl.se/v1/sites/{self.config_data['site_id']}/departures"
        async with self.session.get(url, timeout=10) as resp:
            if resp.status != 200:
                raise Exception(f"HTTP {resp.status}")
            data = await resp.json()
            next_dep = data.get("departures", [{}])[0] if data.get("departures") else {}
            return {
                "next_time": next_dep.get("expectedDateTime"),
                "line": next_dep.get("line", {}).get("name"),
                "dest": next_dep.get("destination"),
                "departures": data.get("departures", [])[:8]
            }
