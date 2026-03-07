from __future__ import annotations

import logging

import aiohttp
from homeassistant import config_entries
from homeassistant.helpers.aiohttp_client import async_get_clientsession
import voluptuous as vol

from .const import (
    CONF_DESTINATION,
    CONF_DIRECTION,
    CONF_FORECAST,
    CONF_LINE,
    CONF_ORIGIN,
    CONF_POLL_INTERVAL,
    CONF_SITE_ID,
    CONF_TRANSPORT,
    CONF_TYPE,
    DEFAULT_FORECAST,
    DEFAULT_POLL,
    DEFAULT_POLL_MINUTES,
    DOMAIN,
    TRANSPORT_MODES,
    TYPE_DEPARTURES,
    TYPE_DISRUPTIONS,
    TYPE_TRAVEL_TIME,
)

_LOGGER = logging.getLogger(__name__)

TYPE_LABELS = {
    TYPE_DEPARTURES: "Departures (next departures + deviations for a stop)",
    TYPE_DISRUPTIONS: "Deviations (service disruptions for SL or a specific stop)",
    TYPE_TRAVEL_TIME: "Travel Time (journey duration between two stops)",
}

STEP_USER_SCHEMA = vol.Schema(
    {vol.Required(CONF_TYPE): vol.In(list(TYPE_LABELS.keys()))}
)

# SL Journey Planner locations endpoint – returns stops matching a text query
_LOCATIONS_URL = "https://journeyplanner.integration.sl.se/v2/locations/by-text"


def _poll_interval_schema(default: int = DEFAULT_POLL_MINUTES) -> vol.Schema:
    return vol.All(vol.Coerce(int), vol.Range(min=1, max=1440))


def _extract_site_id(raw_id: str) -> str:
    """Extract a plain numeric SL site ID from a raw ID or GID string.

    SL GID format example: ``9021014009192000`` → site ID ``9192``.
    Positions 7-12 contain the stop-area ID with leading zeros.
    """
    digits = "".join(c for c in raw_id if c.isdigit())
    if digits.isdigit() and len(digits) <= 6:
        return digits.lstrip("0") or digits
    if len(digits) >= 13:
        candidate = digits[7:13].lstrip("0")
        if candidate:
            return candidate
    return digits if digits else ""


class SLConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    VERSION = 1

    def __init__(self) -> None:
        self._selected_type: str | None = None
        self._pending_type: str | None = None  # which step to return to after lookup
        self._search_results: dict[str, str] = {}  # display label -> site_id
        self._prefill_site_id: str = ""

    # ------------------------------------------------------------------
    # Step 1 – choose integration type
    # ------------------------------------------------------------------

    async def async_step_user(self, user_input=None):
        if user_input is not None:
            self._selected_type = user_input[CONF_TYPE]
            self._pending_type = self._selected_type
            if self._selected_type == TYPE_TRAVEL_TIME:
                return await self.async_step_travel_time()
            elif self._selected_type == TYPE_DEPARTURES:
                return await self.async_step_departures()
            elif self._selected_type == TYPE_DISRUPTIONS:
                return await self.async_step_deviations()

        return self.async_show_form(
            step_id="user",
            data_schema=STEP_USER_SCHEMA,
        )

    # ------------------------------------------------------------------
    # Step 2a – travel time
    # ------------------------------------------------------------------

    async def async_step_travel_time(self, user_input=None):
        errors = {}
        if user_input is not None:
            origin = user_input[CONF_ORIGIN].strip()
            destination = user_input[CONF_DESTINATION].strip()
            if not origin:
                errors[CONF_ORIGIN] = "invalid_stop"
            if not destination:
                errors[CONF_DESTINATION] = "invalid_stop"
            if not errors:
                poll_minutes = int(user_input.get(CONF_POLL_INTERVAL, DEFAULT_POLL_MINUTES))
                title = user_input.get("name") or f"{origin} → {destination}"
                return self.async_create_entry(
                    title=title,
                    data={
                        CONF_TYPE: TYPE_TRAVEL_TIME,
                        CONF_ORIGIN: origin,
                        CONF_DESTINATION: destination,
                        CONF_POLL_INTERVAL: poll_minutes * 60,
                    },
                )

        schema = vol.Schema(
            {
                vol.Required(CONF_ORIGIN): str,
                vol.Required(CONF_DESTINATION): str,
                vol.Optional("name"): str,
                vol.Optional(CONF_POLL_INTERVAL, default=DEFAULT_POLL_MINUTES): _poll_interval_schema(),
            }
        )
        return self.async_show_form(
            step_id="travel_time",
            data_schema=schema,
            errors=errors,
        )

    # ------------------------------------------------------------------
    # Step 2b – departures
    # ------------------------------------------------------------------

    async def async_step_departures(self, user_input=None):
        errors = {}
        prefill = self._prefill_site_id
        self._prefill_site_id = ""

        if user_input is not None:
            lookup_query = user_input.get("lookup_query", "").strip()
            site_id = user_input.get(CONF_SITE_ID, "").strip()

            if lookup_query:
                self._pending_type = TYPE_DEPARTURES
                return await self.async_step_site_lookup({"search_query": lookup_query})

            if not site_id:
                errors[CONF_SITE_ID] = "invalid_site_id"
            elif not site_id.isdigit():
                errors[CONF_SITE_ID] = "invalid_site_id"

            direction = user_input.get(CONF_DIRECTION)
            line = user_input.get(CONF_LINE)
            forecast = user_input.get(CONF_FORECAST, DEFAULT_FORECAST)

            if direction is not None:
                try:
                    direction = int(direction)
                except (ValueError, TypeError):
                    errors[CONF_DIRECTION] = "invalid_integer"
                    direction = None

            if line is not None:
                try:
                    line = int(line)
                except (ValueError, TypeError):
                    errors[CONF_LINE] = "invalid_integer"
                    line = None

            try:
                forecast = int(forecast)
            except (ValueError, TypeError):
                errors[CONF_FORECAST] = "invalid_integer"
                forecast = DEFAULT_FORECAST

            if not errors:
                poll_minutes = int(user_input.get(CONF_POLL_INTERVAL, DEFAULT_POLL_MINUTES))
                title = user_input.get("name") or f"Departures – site {site_id}"
                entry_data = {
                    CONF_TYPE: TYPE_DEPARTURES,
                    CONF_SITE_ID: site_id,
                    CONF_POLL_INTERVAL: poll_minutes * 60,
                    CONF_FORECAST: forecast,
                }
                transport = user_input.get(CONF_TRANSPORT)
                if transport:
                    entry_data[CONF_TRANSPORT] = transport
                if direction is not None:
                    entry_data[CONF_DIRECTION] = direction
                if line is not None:
                    entry_data[CONF_LINE] = line
                return self.async_create_entry(title=title, data=entry_data)

        transport_options = [""] + TRANSPORT_MODES
        schema = vol.Schema(
            {
                vol.Optional("lookup_query"): str,
                vol.Optional(CONF_SITE_ID, default=prefill): str,
                vol.Optional(CONF_TRANSPORT, default=""): vol.In(transport_options),
                vol.Optional(CONF_DIRECTION): vol.Any(None, vol.Coerce(int)),
                vol.Optional(CONF_LINE): vol.Any(None, vol.Coerce(int)),
                vol.Optional(CONF_FORECAST, default=DEFAULT_FORECAST): vol.All(vol.Coerce(int), vol.Range(min=1)),
                vol.Optional("name"): str,
                vol.Optional(CONF_POLL_INTERVAL, default=DEFAULT_POLL_MINUTES): _poll_interval_schema(),
            }
        )
        return self.async_show_form(
            step_id="departures",
            data_schema=schema,
            errors=errors,
        )

    # ------------------------------------------------------------------
    # Step 2c – deviations
    # ------------------------------------------------------------------

    async def async_step_deviations(self, user_input=None):
        errors = {}
        prefill = self._prefill_site_id
        self._prefill_site_id = ""

        if user_input is not None:
            lookup_query = user_input.get("lookup_query", "").strip()
            site_id = user_input.get(CONF_SITE_ID, "").strip()

            if lookup_query:
                self._pending_type = TYPE_DISRUPTIONS
                return await self.async_step_site_lookup({"search_query": lookup_query})

            if site_id and not site_id.isdigit():
                errors[CONF_SITE_ID] = "invalid_site_id"

            if not errors:
                poll_minutes = int(user_input.get(CONF_POLL_INTERVAL, DEFAULT_POLL_MINUTES))
                if site_id:
                    title = user_input.get("name") or f"Deviations – site {site_id}"
                else:
                    title = user_input.get("name") or "SL Deviations (all)"
                return self.async_create_entry(
                    title=title,
                    data={
                        CONF_TYPE: TYPE_DISRUPTIONS,
                        CONF_SITE_ID: site_id,
                        CONF_POLL_INTERVAL: poll_minutes * 60,
                    },
                )

        schema = vol.Schema(
            {
                vol.Optional("lookup_query"): str,
                vol.Optional(CONF_SITE_ID, default=prefill): str,
                vol.Optional("name"): str,
                vol.Optional(CONF_POLL_INTERVAL, default=DEFAULT_POLL_MINUTES): _poll_interval_schema(),
            }
        )
        return self.async_show_form(
            step_id="deviations",
            data_schema=schema,
            errors=errors,
        )

    # ------------------------------------------------------------------
    # Step 3 (optional) – site lookup
    # ------------------------------------------------------------------

    async def async_step_site_lookup(self, user_input=None):
        """Two-phase step: first collect a search query, then show results."""
        errors = {}

        if user_input is not None:
            if "selected_site" in user_input:
                # User picked a stop from the results list
                selected = user_input["selected_site"]
                self._prefill_site_id = self._search_results.get(selected, "")
                if self._pending_type == TYPE_DEPARTURES:
                    return await self.async_step_departures()
                return await self.async_step_deviations()

            if "search_query" in user_input:
                query = user_input["search_query"].strip()
                if not query:
                    errors["search_query"] = "empty_search"
                else:
                    results = await self._do_stop_search(query)
                    if not results:
                        errors["search_query"] = "no_results"
                    else:
                        self._search_results = {r["label"]: r["id"] for r in results}
                        return self.async_show_form(
                            step_id="site_lookup",
                            data_schema=vol.Schema(
                                {
                                    vol.Required("selected_site"): vol.In(
                                        list(self._search_results.keys())
                                    )
                                }
                            ),
                            description_placeholders={"query": query},
                        )

        # Initial search query form
        return self.async_show_form(
            step_id="site_lookup",
            data_schema=vol.Schema({vol.Required("search_query"): str}),
            errors=errors,
        )

    # ------------------------------------------------------------------
    # SL API helpers
    # ------------------------------------------------------------------

    async def _do_stop_search(self, query: str) -> list[dict]:
        """Search SL Journey Planner for stops matching *query*.

        Returns a list of dicts with ``label`` (display string) and ``id`` (site ID).
        """
        session = async_get_clientsession(self.hass)
        try:
            async with session.get(
                _LOCATIONS_URL,
                params={"input": query, "type": "STOP"},
                timeout=aiohttp.ClientTimeout(total=10),
            ) as resp:
                if resp.status != 200:
                    _LOGGER.warning("SL locations API returned HTTP %s", resp.status)
                    return []
                data = await resp.json()
        except Exception as err:
            _LOGGER.warning("Stop search request failed: %s", err)
            return []

        # The API may return a list directly or nest results under a key
        if isinstance(data, list):
            locations = data
        else:
            locations = (
                data.get("stopLocations")
                or data.get("locations")
                or data.get("stopLocation")
                or []
            )

        results: list[dict] = []
        seen: set[str] = set()
        for loc in locations:
            name = loc.get("name", "").strip()
            raw_id = str(loc.get("extId") or loc.get("id") or "")
            site_id = _extract_site_id(raw_id)
            if not name or not site_id or not site_id.isdigit():
                continue
            if site_id in seen:
                continue
            seen.add(site_id)
            results.append({"label": f"{name} (ID: {site_id})", "id": site_id})
            if len(results) >= 15:
                break

        return results

    # ------------------------------------------------------------------
    # Options flow
    # ------------------------------------------------------------------

    @staticmethod
    def async_get_options_flow(config_entry):
        return SLOptionsFlowHandler(config_entry)


class SLOptionsFlowHandler(config_entries.OptionsFlow):
    """Allow users to change the polling interval after initial setup."""

    def __init__(self, config_entry) -> None:
        self._config_entry = config_entry

    async def async_step_init(self, user_input=None):
        if user_input is not None:
            poll_minutes = int(user_input.get(CONF_POLL_INTERVAL, DEFAULT_POLL_MINUTES))
            return self.async_create_entry(
                title="",
                data={CONF_POLL_INTERVAL: poll_minutes * 60},
            )

        # Determine current interval in minutes to pre-fill the field
        current_seconds = self._config_entry.options.get(
            CONF_POLL_INTERVAL,
            self._config_entry.data.get(CONF_POLL_INTERVAL, DEFAULT_POLL),
        )
        current_minutes = max(1, current_seconds // 60)

        return self.async_show_form(
            step_id="init",
            data_schema=vol.Schema(
                {
                    vol.Optional(CONF_POLL_INTERVAL, default=current_minutes): _poll_interval_schema(),
                }
            ),
        )
