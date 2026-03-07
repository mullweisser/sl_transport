import aiohttp
import logging
from datetime import datetime, timezone
from datetime import timedelta
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .const import CONF_DIRECTION, CONF_FORECAST, CONF_LINE, CONF_TRANSPORT, DEFAULT_FORECAST, DOMAIN, TYPE_TRAVEL_TIME, TYPE_DISRUPTIONS, TYPE_DEPARTURES

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
            if self.config_type == TYPE_TRAVEL_TIME:
                return await self._fetch_travel_time()
            elif self.config_type == TYPE_DISRUPTIONS:
                return await self._fetch_disruptions()
            elif self.config_type == TYPE_DEPARTURES:
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
        }
        async with self.session.get(url, params=params, timeout=aiohttp.ClientTimeout(total=15)) as resp:
            if resp.status != 200:
                raise Exception(f"HTTP {resp.status}")
            data = await resp.json()
            # Journey Planner v2 returns "journeys" with "tripDuration" in seconds
            journeys = data.get("journeys") or data.get("trips") or []
            if not journeys:
                return {"duration": None, "origin": self.config_data["origin"], "destination": self.config_data["destination"]}
            journey = journeys[0]
            duration_secs = journey.get("tripDuration") or journey.get("duration")
            return {
                "duration": duration_secs // 60 if duration_secs is not None else None,
                "origin": self.config_data["origin"],
                "destination": self.config_data["destination"],
                "interchanges": journey.get("interchanges"),
            }

    async def _fetch_disruptions(self):
        url = "https://deviations.integration.sl.se/v1/messages"
        params = {"future": "true"}
        site_id = self.config_data.get("site_id", "").strip()
        if site_id:
            params["site"] = site_id
        async with self.session.get(url, params=params, timeout=aiohttp.ClientTimeout(total=10)) as resp:
            if resp.status != 200:
                raise Exception(f"HTTP {resp.status}")
            data = await resp.json()
            # Filter to currently active deviations using publish window when available
            now = datetime.now(timezone.utc)
            active = []
            for d in data:
                publish = d.get("publish") or {}
                upto = publish.get("upto")
                if upto:
                    try:
                        expiry = datetime.fromisoformat(upto.replace("Z", "+00:00"))
                        if expiry < now:
                            continue
                    except (ValueError, AttributeError):
                        pass
                active.append(d)
            return {"deviations": active, "count": len(active)}

    async def _fetch_departures(self):
        site_id = self.config_data["site_id"]
        url = f"https://transport.integration.sl.se/v1/sites/{site_id}/departures"
        params = {}
        transport = self.config_data.get(CONF_TRANSPORT)
        if transport:
            params["transport"] = transport
        direction = self.config_data.get(CONF_DIRECTION)
        if direction is not None:
            params["direction"] = direction
        line = self.config_data.get(CONF_LINE)
        if line is not None:
            params["line"] = line
        forecast = self.config_data.get(CONF_FORECAST, DEFAULT_FORECAST)
        params["forecast"] = forecast
        async with self.session.get(url, params=params, timeout=aiohttp.ClientTimeout(total=10)) as resp:
            if resp.status != 200:
                raise Exception(f"HTTP {resp.status}")
            data = await resp.json()
            departures = data.get("departures", [])
            result = {
                "departures": departures,
                "deviations": [],
                "deviation_count": 0,
            }

        # Also fetch deviations for this stop so the departure entity can expose them
        try:
            dev_url = "https://deviations.integration.sl.se/v1/messages"
            async with self.session.get(
                dev_url,
                params={"site": site_id, "future": "true"},
                timeout=aiohttp.ClientTimeout(total=10),
            ) as dev_resp:
                if dev_resp.status == 200:
                    dev_data = await dev_resp.json()
                    now = datetime.now(timezone.utc)
                    active = []
                    for d in dev_data:
                        publish = d.get("publish") or {}
                        upto = publish.get("upto")
                        if upto:
                            try:
                                expiry = datetime.fromisoformat(upto.replace("Z", "+00:00"))
                                if expiry < now:
                                    continue
                            except (ValueError, AttributeError):
                                pass
                        active.append(d)
                    result["deviations"] = active
                    result["deviation_count"] = len(active)
        except Exception as err:
            _LOGGER.debug("Could not fetch deviations for site %s: %s", site_id, err)

        return result
