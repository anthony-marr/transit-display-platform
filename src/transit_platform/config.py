"""Runtime configuration, all from environment variables with safe defaults."""
from __future__ import annotations

import os

# Storage. SQLite by default so the milestone runs on a laptop with zero
# setup; point at Postgres for the always-on deployment (see docker-compose).
DATABASE_URL = os.environ.get("TRANSIT_DATABASE_URL", "sqlite:///transit.db")

# WMATA. The rail feeds require a free developer key from
# https://developer.wmata.com/ - with no key configured the rail poller
# stays off and everything else still runs.
WMATA_API_KEY = os.environ.get("WMATA_API_KEY", "")
WMATA_GTFSRT_BASE = os.environ.get("TRANSIT_WMATA_BASE", "https://api.wmata.com/gtfs")
WMATA_API_BASE = os.environ.get("TRANSIT_WMATA_API", "https://api.wmata.com")
# Metro stations to poll predictions for (comma-separated station codes,
# e.g. "K01,B03" for Metro Center and Smithsonian). Empty = predictions off.
WMATA_PREDICTION_STATIONS = [
    s.strip() for s in os.environ.get("TRANSIT_PREDICTION_STATIONS", "").split(",") if s.strip()
]

# Capital Bikeshare GBFS (no key needed). The discovery document is at
# https://gbfs.capitalbikeshare.com/gbfs/gbfs.json and points here.
GBFS_BASE = os.environ.get(
    "TRANSIT_GBFS_BASE", "https://gbfs.lyft.com/gbfs/1.1/dca-cabi/en"
)

BIKESHARE_POLL_SECONDS = float(os.environ.get("TRANSIT_BIKE_POLL_SECONDS", "30"))
STATION_INFO_POLL_SECONDS = float(os.environ.get("TRANSIT_INFO_POLL_SECONDS", "3600"))
RAIL_POLL_SECONDS = float(os.environ.get("TRANSIT_RAIL_POLL_SECONDS", "20"))

# Set TRANSIT_INGEST=off to serve the API without background pollers (tests).
INGEST_ENABLED = os.environ.get("TRANSIT_INGEST", "on").lower() not in {"off", "0", "false"}
