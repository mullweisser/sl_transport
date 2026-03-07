from __future__ import annotations

import logging

import aiohttp
from homeassistant import config_entries
from homeassistant.helpers.aiohttp_client import async_get_clientsession
import voluptuous as vol

from .const import (
    CONF_DESTINATION,
    CONF_ORIGIN,
    CONF_POLL_INTERVAL,
    CONF_SITE_ID,
    CONF_TYPE,
    DEFAULT_POLL,
    DEFAULT_POLL_MINUTES,
    DOMAIN,
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
            description_placeholders={"example": "e.g. Slussen, Odenplan, T-Centralen"},
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

            if not errors:
                poll_minutes = int(user_input.get(CONF_POLL_INTERVAL, DEFAULT_POLL_MINUTES))
                title = user_input.get("name") or f"Departures – site {site_id}"
                return self.async_create_entry(
                    title=title,
                    data={
                        CONF_TYPE: TYPE_DEPARTURES,
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
            step_id="departures",
            data_schema=schema,
            errors=errors,
            description_placeholders={
                "example": (
                    "Search for a stop by name above, or enter a numeric site ID directly "
                    "(e.g. 9192 for Slussen)."
                )
            },
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
            description_placeholders={
                "example": (
                    "Leave blank for all SL deviations, or search/enter a site ID to filter "
                    "to a specific stop."
                )
            },
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
    """Allow users to change settings after initial setup."""

    def __init__(self, config_entry) -> None:
        self._config_entry = config_entry

    def _current(self, key, default=None):
        """Return the current value for a key, checking options then data."""
        return self._config_entry.options.get(
            key, self._config_entry.data.get(key, default)
        )

    async def async_step_init(self, user_input=None):
        is_departures = self._config_entry.data.get(CONF_TYPE) == TYPE_DEPARTURES

        if user_input is not None:
            poll_minutes = int(user_input.get(CONF_POLL_INTERVAL, DEFAULT_POLL_MINUTES))
            options = {CONF_POLL_INTERVAL: poll_minutes * 60}

            if is_departures:
                transport = user_input.get(CONF_TRANSPORT, "")
                if transport:
                    options[CONF_TRANSPORT] = transport

                direction = user_input.get(CONF_DIRECTION)
                if direction is not None:
                    try:
                        options[CONF_DIRECTION] = int(direction)
                    except (ValueError, TypeError):
                        pass

                line = user_input.get(CONF_LINE)
                if line is not None:
                    try:
                        options[CONF_LINE] = int(line)
                    except (ValueError, TypeError):
                        pass

                try:
                    options[CONF_FORECAST] = int(user_input.get(CONF_FORECAST, DEFAULT_FORECAST))
                except (ValueError, TypeError):
                    options[CONF_FORECAST] = DEFAULT_FORECAST

            return self.async_create_entry(title="", data=options)

        # Pre-fill current values
        current_seconds = self._current(CONF_POLL_INTERVAL, DEFAULT_POLL)
        current_minutes = max(1, current_seconds // 60)

        fields = {
            vol.Optional(CONF_POLL_INTERVAL, default=current_minutes): _poll_interval_schema(),
        }

        if is_departures:
            transport_options = [""] + TRANSPORT_MODES
            fields[vol.Optional(CONF_TRANSPORT, default=self._current(CONF_TRANSPORT, ""))] = vol.In(transport_options)
            current_direction = self._current(CONF_DIRECTION)
            fields[vol.Optional(CONF_DIRECTION, default=current_direction)] = vol.Any(None, vol.Coerce(int))
            current_line = self._current(CONF_LINE)
            fields[vol.Optional(CONF_LINE, default=current_line)] = vol.Any(None, vol.Coerce(int))
            fields[vol.Optional(CONF_FORECAST, default=self._current(CONF_FORECAST, DEFAULT_FORECAST))] = vol.All(vol.Coerce(int), vol.Range(min=1))

        return self.async_show_form(
            step_id="init",
            data_schema=vol.Schema(fields),
        )
