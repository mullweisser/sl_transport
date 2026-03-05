from homeassistant import config_entries
import voluptuous as vol

from .const import (
    DOMAIN,
    TYPE_TRAVEL_TIME,
    TYPE_DISRUPTIONS,
    TYPE_DEPARTURES,
    CONF_TYPE,
    CONF_ORIGIN,
    CONF_DESTINATION,
    CONF_SITE_ID,
)

TYPE_LABELS = {
    TYPE_DEPARTURES: "Departures (next departures + deviations for a stop)",
    TYPE_DISRUPTIONS: "Deviations (service disruptions for SL or a specific stop)",
    TYPE_TRAVEL_TIME: "Travel Time (journey duration between two stops)",
}

STEP_USER_SCHEMA = vol.Schema(
    {vol.Required(CONF_TYPE): vol.In(list(TYPE_LABELS.keys()))}
)


class SLConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    VERSION = 1

    def __init__(self):
        self._selected_type = None

    async def async_step_user(self, user_input=None):
        if user_input is not None:
            self._selected_type = user_input[CONF_TYPE]
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
                title = user_input.get("name") or f"{origin} → {destination}"
                return self.async_create_entry(
                    title=title,
                    data={
                        CONF_TYPE: TYPE_TRAVEL_TIME,
                        CONF_ORIGIN: origin,
                        CONF_DESTINATION: destination,
                    },
                )

        schema = vol.Schema(
            {
                vol.Required(CONF_ORIGIN): str,
                vol.Required(CONF_DESTINATION): str,
                vol.Optional("name"): str,
            }
        )
        return self.async_show_form(
            step_id="travel_time",
            data_schema=schema,
            errors=errors,
            description_placeholders={
                "example": "e.g. Slussen, Odenplan, T-Centralen"
            },
        )

    async def async_step_departures(self, user_input=None):
        errors = {}
        if user_input is not None:
            site_id = user_input[CONF_SITE_ID].strip()
            if not site_id.isdigit():
                errors[CONF_SITE_ID] = "invalid_site_id"
            if not errors:
                title = user_input.get("name") or f"Departures – site {site_id}"
                return self.async_create_entry(
                    title=title,
                    data={
                        CONF_TYPE: TYPE_DEPARTURES,
                        CONF_SITE_ID: site_id,
                    },
                )

        schema = vol.Schema(
            {
                vol.Required(CONF_SITE_ID): str,
                vol.Optional("name"): str,
            }
        )
        return self.async_show_form(
            step_id="departures",
            data_schema=schema,
            errors=errors,
            description_placeholders={
                "example": "e.g. 9192 for Slussen. Find your site ID at sl.se or rejseplanen.se."
            },
        )

    async def async_step_deviations(self, user_input=None):
        errors = {}
        if user_input is not None:
            site_id = user_input.get(CONF_SITE_ID, "").strip()
            if site_id and not site_id.isdigit():
                errors[CONF_SITE_ID] = "invalid_site_id"
            if not errors:
                if site_id:
                    title = user_input.get("name") or f"Deviations – site {site_id}"
                else:
                    title = user_input.get("name") or "SL Deviations (all)"
                return self.async_create_entry(
                    title=title,
                    data={
                        CONF_TYPE: TYPE_DISRUPTIONS,
                        CONF_SITE_ID: site_id,
                    },
                )

        schema = vol.Schema(
            {
                vol.Optional(CONF_SITE_ID): str,
                vol.Optional("name"): str,
            }
        )
        return self.async_show_form(
            step_id="deviations",
            data_schema=schema,
            errors=errors,
            description_placeholders={
                "example": "Leave blank to show all SL deviations, or enter a site ID to filter."
            },
        )
