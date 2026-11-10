"""Analytics over the stored feed history.

The heavy lifting is pure functions over row dicts so the math is testable
without a database; the ``*_report`` wrappers pull rows from TransitDB and
shape the JSON the API returns.
"""
from __future__ import annotations

import datetime as dt


def _parse_ts(value: str) -> dt.datetime | None:
    try:
        return dt.datetime.fromisoformat(value)
    except (TypeError, ValueError):
        return None


def window_start_iso(minutes: int) -> str:
    return (dt.datetime.now(dt.timezone.utc)
            - dt.timedelta(minutes=minutes)).isoformat()


def summarize_latest(latest_rows: list[dict]) -> dict:
    """System-wide bikeshare totals from one latest-row-per-station snapshot."""
    total_bikes = sum(r["num_bikes_available"] for r in latest_rows)
    total_ebikes = sum(r["num_ebikes_available"] for r in latest_rows)
    total_docks = sum(r["num_docks_available"] for r in latest_rows)
    empty = [r for r in latest_rows if r["num_bikes_available"] == 0]
    full = [r for r in latest_rows
            if r["is_returning"] and r["num_docks_available"] == 0]
    return {
        "stations_reporting": len(latest_rows),
        "total_bikes_available": total_bikes,
        "total_ebikes_available": total_ebikes,
        "total_docks_available": total_docks,
        "stations_empty": sorted(({"station_id": r["station_id"], "name": r.get("name")}
                                  for r in empty), key=lambda r: r["name"] or ""),
        "stations_full": sorted(({"station_id": r["station_id"], "name": r.get("name")}
                                 for r in full), key=lambda r: r["name"] or ""),
    }


def compute_movers(window_rows: list[dict], limit: int = 10) -> list[dict]:
    """Stations with the largest net bike change across the window.

    Compares each station's first and last sample inside the window, so a
    station needs at least two samples to rank.
    """
    by_station: dict[str, list[dict]] = {}
    for row in window_rows:
        by_station.setdefault(row["station_id"], []).append(row)
    out = []
    for station_id, rows in by_station.items():
        rows.sort(key=lambda r: r["fetched_at"])
        if len(rows) < 2:
            continue
        first, last = rows[0], rows[-1]
        net = last["num_bikes_available"] - first["num_bikes_available"]
        out.append({
            "station_id": station_id,
            "name": last.get("name") or first.get("name"),
            "net_bike_change": net,
            "bikes_start": first["num_bikes_available"],
            "bikes_end": last["num_bikes_available"],
            "samples": len(rows),
        })
    out.sort(key=lambda r: -abs(r["net_bike_change"]))
    return out[:limit]


def compute_station_stats(history_rows: list[dict], capacity: int | None) -> dict:
    """Availability stats for one station over its history rows."""
    if not history_rows:
        return {"samples": 0}
    bikes = [r["num_bikes_available"] for r in history_rows]
    docks = [r["num_docks_available"] for r in history_rows]
    n = len(history_rows)
    return {
        "samples": n,
        "avg_bikes_available": round(sum(bikes) / n, 2),
        "min_bikes_available": min(bikes),
        "max_bikes_available": max(bikes),
        "avg_docks_available": round(sum(docks) / n, 2),
        "pct_empty": round(100.0 * sum(1 for b in bikes if b == 0) / n, 1),
        "pct_full": round(100.0 * sum(1 for d in docks if d == 0) / n, 1),
        "capacity": capacity,
    }


# -- DB-backed reports ----------------------------------------------------

def summary_report(db) -> dict:
    return summarize_latest(db.latest_station_status())


def movers_report(db, minutes: int = 60, limit: int = 10) -> dict:
    rows = db.station_status_in_window(window_start_iso(minutes))
    names = {s["station_id"]: s.get("name")
             for s in db.latest_station_status()}
    for row in rows:
        row["name"] = names.get(row["station_id"])
    return {"window_minutes": minutes,
            "movers": compute_movers(rows, limit=limit)}


def station_stats_report(db, station_id: str, minutes: int = 1440) -> dict:
    rows = db.station_status_in_window(window_start_iso(minutes),
                                       station_id=station_id)
    latest = db.latest_station_status(station_id)
    capacity = latest[0].get("capacity") if latest else None
    return {"station_id": station_id, "window_minutes": minutes,
            **compute_station_stats(rows, capacity)}
