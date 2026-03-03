# SL Transport - Home Assistant Integration

Custom HACS integration for SL (Stockholm) public transport using official key-less APIs.

## Features
- Travel time sensor (A→B)
- Disruptions binary sensor + details
- Next departures sensor

## Installation
1. HACS → Integrations → 3-dots → Custom repositories
2. Add: https://github.com/YOURUSERNAME/sl_transport  Category: Integration
3. Search & install "SL Transport"
4. Restart HA
5. Settings → Devices & services → Add Integration → SL Transport

Add multiple instances for different routes/stops.

## APIs used (2026)
- Journey: https://journeyplanner.integration.sl.se/v2/
- Deviations: https://deviations.integration.sl.se/v1/
- Transport/Departures: https://transport.integration.sl.se/v1/

No API key needed — respect fair use.
