import datetime as dt

from transit_platform import analytics
from transit_platform.schemas import StationInfo, StationStatus


def _row(station_id, bikes, docks=5, ts="2026-11-09T20:00:00+00:00", name=None):
    return {"station_id": station_id, "fetched_at": ts,
            "num_bikes_available": bikes, "num_ebikes_available": 0,
            "num_docks_available": docks, "is_installed": 1,
            "is_renting": 1, "is_returning": 1, "last_reported": 0,
            "name": name}


def test_summarize_latest_totals_and_flags():
    rows = [_row("s1", 4, docks=6, name="Alpha"),
            _row("s2", 0, docks=10, name="Beta"),
            _row("s3", 9, docks=0, name="Gamma")]
    out = analytics.summarize_latest(rows)
    assert out["stations_reporting"] == 3
    assert out["total_bikes_available"] == 13
    assert out["total_docks_available"] == 16
    assert [s["station_id"] for s in out["stations_empty"]] == ["s2"]
    assert [s["station_id"] for s in out["stations_full"]] == ["s3"]


def test_compute_movers_ranks_by_abs_change():
    t0 = "2026-11-09T20:00:00+00:00"
    t1 = "2026-11-09T20:30:00+00:00"
    rows = [_row("s1", 10, ts=t0), _row("s1", 3, ts=t1),   # -7
            _row("s2", 2, ts=t0), _row("s2", 6, ts=t1),    # +4
            _row("s3", 5, ts=t0)]                           # one sample, skipped
    out = analytics.compute_movers(rows, limit=10)
    assert [m["station_id"] for m in out] == ["s1", "s2"]
    assert out[0]["net_bike_change"] == -7
    assert out[1]["net_bike_change"] == 4


def test_compute_station_stats():
    rows = [_row("s1", 0), _row("s1", 4), _row("s1", 8), _row("s1", 4)]
    out = analytics.compute_station_stats(rows, capacity=16)
    assert out["samples"] == 4
    assert out["avg_bikes_available"] == 4.0
    assert out["min_bikes_available"] == 0
    assert out["max_bikes_available"] == 8
    assert out["pct_empty"] == 25.0
    assert out["pct_full"] == 0.0
    assert out["capacity"] == 16
    assert analytics.compute_station_stats([], None) == {"samples": 0}


def test_reports_over_db(db):
    now = dt.datetime.now(dt.timezone.utc)
    t_old = (now - dt.timedelta(minutes=30)).isoformat()
    t_new = now.isoformat()
    db.upsert_stations([StationInfo(station_id="s1", name="Test", lat=38.9,
                                    lon=-77.0, capacity=20)], t_old)
    db.insert_station_status([
        StationStatus(station_id="s1", fetched_at=t_old,
                      num_bikes_available=10, num_docks_available=10),
        StationStatus(station_id="s1", fetched_at=t_new,
                      num_bikes_available=4, num_docks_available=16),
    ])
    summary = analytics.summary_report(db)
    assert summary["total_bikes_available"] == 4
    movers = analytics.movers_report(db, minutes=60)
    assert movers["movers"][0]["net_bike_change"] == -6
    stats = analytics.station_stats_report(db, "s1", minutes=60)
    assert stats["samples"] == 2
    assert stats["capacity"] == 20


def test_movers_window_excludes_old_rows(db):
    now = dt.datetime.now(dt.timezone.utc)
    t_old = (now - dt.timedelta(hours=3)).isoformat()
    db.insert_station_status([
        StationStatus(station_id="s1", fetched_at=t_old,
                      num_bikes_available=10, num_docks_available=10)])
    movers = analytics.movers_report(db, minutes=60)
    assert movers["movers"] == []
