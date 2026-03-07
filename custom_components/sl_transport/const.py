DOMAIN = "sl_transport"

CONF_TYPE = "type"
CONF_ORIGIN = "origin"
CONF_DESTINATION = "destination"
CONF_SITE_ID = "site_id"
CONF_MODES = "modes"          # list e.g. [1,2,4] metro/bus/train
CONF_POLL_INTERVAL = "poll_interval"

# Departure filter parameters
CONF_TRANSPORT = "transport"
CONF_DIRECTION = "direction"
CONF_LINE = "line"
CONF_FORECAST = "forecast"

DEFAULT_FORECAST = 60  # minutes
MAX_FORECAST = 1200   # minutes (API maximum)

TRANSPORT_MODES = ["BUS", "TRAM", "METRO", "TRAIN", "FERRY", "SHIP", "TAXI"]

TYPE_TRAVEL_TIME = "travel_time"
TYPE_DISRUPTIONS = "disruptions"
TYPE_DEPARTURES = "departures"

DEFAULT_POLL = 59           # roughly 1 minute in seconds
DEFAULT_POLL_MINUTES = 1    # default shown in config forms

TRANSPORT_MODE_ICONS = {
    "BUS": "mdi:bus",
    "TRAM": "mdi:tram",
    "METRO": "mdi:subway",
    "TRAIN": "mdi:train",
    "FERRY": "mdi:ferry",
    "SHIP": "mdi:ship-wheel",
    "TAXI": "mdi:taxi",
}
