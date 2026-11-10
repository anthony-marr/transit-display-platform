# Transit Display Platform

[![Tests](https://github.com/anthony-marr/transit-display-platform/actions/workflows/tests.yml/badge.svg)](https://github.com/anthony-marr/transit-display-platform/actions/workflows/tests.yml)

The platform behind my Raspberry Pi LED transit display. The Pi and the LED
matrix are unchanged - this project moves everything they used to do on-device
(poll an API, render, repeat) into a real streaming data service, so the
hardware becomes a thin front end. The service polls WMATA rail and Capital
Bikeshare feeds, stores raw snapshots and cleaned history, and serves the
results over REST and a WebSocket feed the Pi and a web dashboard subscribe
to.

Original LED display build: Jan - May 2026. This platform: started Nov 2026.

## How it fits together

```
   WMATA GTFS-RT rail feeds          Capital Bikeshare GBFS
   (vehicle positions, trip          (station info + status,
    updates, predictions;             no key needed, ~60s ttl)
    free developer key)
            |                                  |
            v                                  v
   +--------------------- poll every few seconds --------------------+
   |                     FastAPI ingest service                      |
   |  normalize -> pydantic models -> store                          |
   +--------+---------------------------+----------------+-----------+
            |                           |                |
            v                           v                v
   +----------------+          +----------------+  +------------------+
   |  raw_snapshots |          |  cleaned rows  |  |   EventHub       |
   |  (replayable)  |          |  (history)     |  |   pub/sub        |
   +----------------+          +----------------+  +------------------+
        SQLite by default,                |
        Postgres via TRANSIT_             v
        DATABASE_URL             +-------------------------+
                                 |  REST + WebSocket /ws   |
                                 +-----------+-------------+
                                             |
                                  +----------v-----------+
                                  |  Pi thin client      |
                                  |  (pi_client.py ->    |
                                  |   LED matrix)        |
                                  +----------------------+
```

Every payload from a feed validates through the pydantic models in
`src/transit_platform/schemas.py` before it touches the store, so a surprise
field from WMATA or Lyft fails at the boundary. Raw responses are kept in
`raw_snapshots` next to the cleaned rows, so any ingest bug can be replayed
from the original bytes.

## Quickstart

```bash
pip install -r requirements-dev.txt
python -m pytest -q                          # tests, no network needed (feeds are mocked)
python -m uvicorn transit_platform.api:app   # serve + ingest bikeshare immediately
```

In another terminal, watch the live feed the way the Pi will:

```bash
transit-pi-client                            # full feed
transit-pi-client --station <station_id>     # only your station(s)
```

REST endpoints:

- `GET /health`
- `GET /api/status` - last fetch per source and row counts
- `GET /api/bikes/stations` - latest status per station, joined with names
- `GET /api/bikes/stations/{id}/history` - time series for one station
- `GET /api/rail/vehicles/latest` - most recent rail vehicle positions
- `GET /api/analytics/rail/headways?station=E03` - headway stats per station
- `GET /api/analytics/rail/bunching` - bunches (<=3 min) and gaps (>=18 min) in the latest snapshot
- `GET /api/analytics/rail/lines` - trains reporting per line
- `GET /api/analytics/bikes/summary` - system totals plus empty/full stations
- `GET /api/analytics/bikes/movers?minutes=60` - largest net bike changes in a window
- `GET /api/analytics/bikes/stations/{id}/stats` - availability stats for one station
- `GET /` - web dashboard over the analytics endpoints
- `WS  /ws/feed` - live events (`?stations=id1,id2` to filter bikeshare)

## WMATA rail feeds

Rail needs a free WMATA developer key: register at
[developer.wmata.com](https://developer.wmata.com/), then:

```bash
export WMATA_API_KEY=your_key_here
export TRANSIT_PREDICTION_STATIONS=K01,B03   # optional, Metro API predictions
```

With no key configured the rail poller stays off and everything else runs -
the `hello` event on the feed says which mode you're in.

## Postgres

SQLite is the default so the project runs on a laptop with zero setup. For
the always-on deployment:

```bash
docker compose up -d
export TRANSIT_DATABASE_URL=postgresql+psycopg://transit:transit@localhost:5432/transit
```

## Configuration

| Variable | Default | What it does |
| --- | --- | --- |
| `TRANSIT_DATABASE_URL` | `sqlite:///transit.db` | store location |
| `WMATA_API_KEY` | _(none)_ | enables the rail poller |
| `TRANSIT_PREDICTION_STATIONS` | _(none)_ | station codes for Metro predictions |
| `TRANSIT_BIKE_POLL_SECONDS` | `30` | bikeshare poll interval |
| `TRANSIT_RAIL_POLL_SECONDS` | `20` | rail poll interval |
| `TRANSIT_INGEST` | `on` | `off` serves the API without pollers |

## MCP server

`src/transit_platform/mcp_server.py` exposes the same store to any MCP host
(Claude Desktop, etc.) over stdio, the same pattern as my
[garden-diagnostic-agent](https://github.com/anthony-marr/garden-diagnostic-agent):

```bash
python -m transit_platform.mcp_server
```

Tools: `get_train_arrivals`, `get_station_headways`, `get_rail_bunching`,
`get_rail_lines`, `get_bikeshare_summary`, `get_bikeshare_movers`,
`find_bike_stations`, `get_bike_station_stats`. Answers are as fresh as the
last poll (rail ~20s, bikeshare ~30s when ingest runs), so "should I leave
now?" is a lookup, not a guess.

## Roadmap

- Rail analytics ship in `rail_analytics.py`: per-direction headways,
  bunching (two trains within 3 minutes) and service gaps (18+ minutes)
  from stored predictions. An arrival-prediction model comes later.
- Deploy to a small always-on host so the Pi never waits on my laptop

## Data sources

- Capital Bikeshare GBFS:
  [capitalbikeshare.com/system-data](https://capitalbikeshare.com/system-data)
  (discovery doc: `gbfs.capitalbikeshare.com/gbfs/gbfs.json`)
- WMATA developer resources and GTFS-RT feeds:
  [wmata.com/about/developers.html](https://www.wmata.com/about/developers.html)
