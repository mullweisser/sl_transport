from homeassistant import config_entries
import voluptuous as vol
from .const import DOMAIN, TYPE_TRAVEL_TIME, TYPE_DISRUPTIONS, TYPE_DEPARTURES, CONF_TYPE, CONF_ORIGIN, CONF_DESTINATION, CONF_SITE_ID

class SLConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    VERSION = 1

    async def async_step_user(self, user_input=None):
        errors = {}
        if user_input is not None:
            return self.async_create_entry(title="SL Transport", data=user_input)

        schema = vol.Schema({
            vol.Required(CONF_TYPE): vol.In([TYPE_TRAVEL_TIME, TYPE_DISRUPTIONS, TYPE_DEPARTURES]),
        })

        if self.context.get("type"):
            tp = self.context["type"]
            if tp == TYPE_TRAVEL_TIME:
                schema = vol.Schema({
                    vol.Required(CONF_ORIGIN): str,
                    vol.Required(CONF_DESTINATION): str,
                })
            elif tp in (TYPE_DISRUPTIONS, TYPE_DEPARTURES):
                schema = vol.Schema({
                    vol.Required(CONF_SITE_ID): str,  # e.g. "9192" for Slussen
                })

        return self.async_show_form(step_id="user", data_schema=schema, errors=errors)

    async def async_step_import(self, import_info):
        return await self.async_step_user(import_info)
