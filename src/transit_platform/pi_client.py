"""Thin display client. Subscribes to the platform feed and renders each
event as text. On the Raspberry Pi this is where the LED matrix hooks in -
the hardware stays a dumb front end, all data work happens in the service.
"""
from __future__ import annotations

import argparse
import json

from websockets.sync.client import connect


def render_event(event: dict) -> str:
    """One line per event. Replace with LED matrix rendering on the Pi."""
    kind = event.get("type")
    data = event.get("data", {})
    if kind == "hello":
        return (f"connected: platform v{data.get('version')} "
                f"(rail {data.get('rail')}, bikes {data.get('bike_filter')})")
    if kind == "bikeshare_status":
        stations = data.get("stations", [])
        if len(stations) <= 10:
            return " | ".join(
                f"bikes {s['station_id'][:8]}: {s['num_bikes_available']} bikes, "
                f"{s['num_docks_available']} docks" for s in stations)
        return (f"bikes: {data.get('stations_updated')} stations, "
                f"{data.get('total_bikes_available')} bikes available")
    if kind == "rail_vehicles":
        by_line: dict[str, int] = {}
        for v in data.get("vehicles", []):
            by_line[v.get("route_id") or "?"] = by_line.get(v.get("route_id") or "?", 0) + 1
        return "trains: " + ", ".join(f"{k} x{n}" for k, n in sorted(by_line.items()))
    if kind == "rail_predictions":
        lines = [f"{data.get('station_code')}: {p['line']} -> {p['destination']} "
                 f"{p['minutes']} min" for p in data.get("predictions", [])]
        return " | ".join(lines) if lines else f"{data.get('station_code')}: no predictions"
    if kind == "error":
        return f"ingest warning: {data.get('poller')} poll failed (kept retrying)"
    return f"{kind}: {json.dumps(data)[:200]}"


def main():
    parser = argparse.ArgumentParser(description="Display client for the transit platform feed")
    parser.add_argument("--url", default="ws://localhost:8000/ws/feed",
                        help="feed URL of a running transit-server")
    parser.add_argument("--station", action="append", default=[],
                        help="bikeshare station id to follow; repeatable")
    args = parser.parse_args()
    url = args.url
    if args.station:
        sep = "&" if "?" in url else "?"
        url = f"{url}{sep}stations={','.join(args.station)}"
    with connect(url) as ws:
        while True:
            raw = ws.recv()
            print(render_event(json.loads(raw)), flush=True)


if __name__ == "__main__":
    main()
