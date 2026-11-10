"""Rail analytics: headways and bunching from stored WMATA predictions.

WMATA's prediction feed gives, per station and per direction ("Group"), the
minutes until each upcoming train arrives. Consecutive trains in one snapshot
give predicted headways, which is enough to spot bunching (two trains about
to arrive on top of each other) and gaps (a long wait behind them) without a
schedule. Pure functions take row dicts so the math is testable without a
database; the ``*_report`` wrappers pull rows from TransitDB.
"""
from __future__ import annotations

from .analytics import window_start_iso

BUNCH_MINUTES = 3   # two trains this close together are bunched
GAP_MINUTES = 18    # a wait this long behind a bunch is a service gap


def parse_minutes(value: str) -> int | None:
    """WMATA "Min" field: a number, "ARR"/"BRD" (arriving/boarding -> 0),
    or "---" (no estimate -> None)."""
    if value is None:
        return None
    text = str(value).strip().upper()
    if text in {"ARR", "BRD"}:
        return 0
    try:
        return int(text)
    except ValueError:
        return None


def snapshot_headways(snapshot_rows: list[dict]) -> list[dict]:
    """Per (station, direction) in one snapshot: sorted ETAs and the
    headways between consecutive trains."""
    groups: dict[tuple, list[dict]] = {}
    for row in snapshot_rows:
        eta = parse_minutes(row.get("minutes"))
        if eta is None:
            continue
        key = (row["station_code"], row.get("grp") or row.get("group") or "?")
        groups.setdefault(key, []).append({**row, "eta": eta})
    out = []
    for (station_code, grp), rows in sorted(groups.items()):
        rows.sort(key=lambda r: r["eta"])
        etas = [r["eta"] for r in rows]
        headways = [b - a for a, b in zip(etas, etas[1:])]
        out.append({
            "station_code": station_code,
            "station_name": rows[0]["station_name"],
            "group": grp,
            "lines": sorted({r["line"] for r in rows}),
            "etas": etas,
            "headways": headways,
        })
    return out


def find_bunches(headway_records: list[dict],
                 threshold: int = BUNCH_MINUTES) -> list[dict]:
    """Station-directions where two trains arrive within `threshold` minutes."""
    out = []
    for rec in headway_records:
        for i, hw in enumerate(rec["headways"]):
            if hw <= threshold:
                out.append({
                    "station_code": rec["station_code"],
                    "station_name": rec["station_name"],
                    "group": rec["group"],
                    "lines": rec["lines"],
                    "headway": hw,
                    "train_etas": [rec["etas"][i], rec["etas"][i + 1]],
                })
    out.sort(key=lambda b: b["headway"])
    return out


def find_gaps(headway_records: list[dict],
              threshold: int = GAP_MINUTES) -> list[dict]:
    """Station-directions with a wait of at least `threshold` minutes."""
    out = []
    for rec in headway_records:
        for i, hw in enumerate(rec["headways"]):
            if hw >= threshold:
                out.append({
                    "station_code": rec["station_code"],
                    "station_name": rec["station_name"],
                    "group": rec["group"],
                    "lines": rec["lines"],
                    "gap": hw,
                    "next_train_eta": rec["etas"][i + 1],
                })
    out.sort(key=lambda g: -g["gap"])
    return out


def station_headway_summary(window_rows: list[dict]) -> dict:
    """Headway stats for one station across every snapshot in the window:
    how often trains come, how tight the tightest pair is, and how often
    the station is bunched or gapped."""
    by_snapshot: dict[str, list[dict]] = {}
    for row in window_rows:
        by_snapshot.setdefault(row["fetched_at"], []).append(row)
    all_headways: list[int] = []
    snapshots = 0
    bunched = 0
    gapped = 0
    for fetched_at in sorted(by_snapshot):
        records = snapshot_headways(by_snapshot[fetched_at])
        if not records:
            continue
        snapshots += 1
        hws = [h for rec in records for h in rec["headways"]]
        all_headways.extend(hws)
        if find_bunches(records):
            bunched += 1
        if find_gaps(records):
            gapped += 1
    if not snapshots:
        return {"snapshots": 0}
    return {
        "snapshots": snapshots,
        "avg_headway": (round(sum(all_headways) / len(all_headways), 1)
                        if all_headways else None),
        "min_headway": min(all_headways) if all_headways else None,
        "max_headway": max(all_headways) if all_headways else None,
        "pct_snapshots_bunched": round(100.0 * bunched / snapshots, 1),
        "pct_snapshots_gapped": round(100.0 * gapped / snapshots, 1),
        "bunch_threshold_minutes": BUNCH_MINUTES,
        "gap_threshold_minutes": GAP_MINUTES,
    }


def line_summary(latest_vehicles: list[dict]) -> list[dict]:
    """Trains per line from the most recent vehicle-positions snapshot."""
    counts: dict[str, set] = {}
    for row in latest_vehicles:
        line = row.get("route_id") or "?"
        counts.setdefault(line, set()).add(row["vehicle_id"])
    return [{"line": line, "vehicles": len(ids)}
            for line, ids in sorted(counts.items())]


# -- DB-backed reports ----------------------------------------------------

def station_headways_report(db, station_code: str, minutes: int = 60) -> dict:
    rows = db.predictions_in_window(window_start_iso(minutes),
                                    station_code=station_code)
    return {"station_code": station_code, "window_minutes": minutes,
            **station_headway_summary(rows)}


def bunching_report(db) -> dict:
    latest = db.latest_predictions()
    records = snapshot_headways(latest)
    return {"snapshot_count": len({r["fetched_at"] for r in latest}),
            "bunches": find_bunches(records),
            "gaps": find_gaps(records)}


def lines_report(db) -> dict:
    return {"lines": line_summary(db.latest_vehicle_positions())}
