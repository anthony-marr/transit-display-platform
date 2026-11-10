from transit_platform.schemas import (RailPrediction, StationInfo,
                                      StationStatus, VehiclePosition)


def _status(station_id="s1", fetched_at="t1", bikes=5):
    return StationStatus(station_id=station_id, fetched_at=fetched_at,
                         num_bikes_available=bikes, num_docks_available=7)


def test_station_status_roundtrip(db):
    db.upsert_stations([StationInfo(station_id="s1", name="Test Station",
                                    lat=38.9, lon=-77.0, capacity=15)], "t0")
    db.insert_station_status([_status()])
    rows = db.latest_station_status()
    assert len(rows) == 1
    assert rows[0]["station_id"] == "s1"
    assert rows[0]["name"] == "Test Station"
    assert rows[0]["num_bikes_available"] == 5


def test_latest_returns_newest_snapshot_only(db):
    db.insert_station_status([_status(fetched_at="t1", bikes=5),
                              _status(fetched_at="t2", bikes=9)])
    rows = db.latest_station_status()
    assert len(rows) == 1
    assert rows[0]["num_bikes_available"] == 9


def test_history_orders_newest_first(db):
    db.insert_station_status([_status(fetched_at="t1"), _status(fetched_at="t3")])
    db.insert_station_status([_status(fetched_at="t2")])
    hist = db.station_history("s1")
    assert [h["fetched_at"] for h in hist] == ["t3", "t2", "t1"]


def test_vehicle_positions_roundtrip(db):
    db.insert_vehicle_positions([VehiclePosition(vehicle_id="501", route_id="RED",
                                                 trip_id="t1", fetched_at="f1")])
    assert db.latest_vehicle_positions()[0]["route_id"] == "RED"


def test_predictions_roundtrip(db):
    n = db.insert_predictions([RailPrediction(station_code="K01", station_name="Metro Center",
                                              line="RD", destination="Shady Grove",
                                              minutes="3", group="1", fetched_at="f1")])
    assert n == 1


def test_source_status_counts(db):
    db.record_snapshot("bikeshare_gbfs", "t1", b"{}")
    db.insert_station_status([_status()])
    out = db.source_status()
    assert out["sources"]["bikeshare_gbfs"]["last_fetch"] == "t1"
    assert out["rows"]["station_status_rows"] == 1
