import datetime as dt

from transit_platform import rail_analytics as ra
from transit_platform.schemas import RailPrediction, VehiclePosition


def _pred(station, grp, minutes, ts="2026-11-09T21:00:00+00:00", line="GR",
          name="Test Station"):
    return {"station_code": station, "station_name": name, "line": line,
            "destination": "X", "minutes": minutes, "group": grp,
            "fetched_at": ts}


def test_parse_minutes():
    assert ra.parse_minutes("3") == 3
    assert ra.parse_minutes("ARR") == 0
    assert ra.parse_minutes("BRD") == 0
    assert ra.parse_minutes("---") is None
    assert ra.parse_minutes(None) is None
    assert ra.parse_minutes("") is None


def test_snapshot_headways_per_direction():
    rows = [_pred("E03", "1", "2"), _pred("E03", "1", "5"),
            _pred("E03", "1", "14"), _pred("E03", "2", "1"),
            _pred("E03", "2", "4")]
    recs = ra.snapshot_headways(rows)
    by_group = {r["group"]: r for r in recs}
    assert by_group["1"]["etas"] == [2, 5, 14]
    assert by_group["1"]["headways"] == [3, 9]
    assert by_group["2"]["headways"] == [3]


def test_find_bunches_and_gaps():
    rows = [_pred("E03", "1", "3"), _pred("E03", "1", "5"),   # 2-min bunch
            _pred("E03", "1", "25"),                          # 20-min gap behind it
            _pred("K01", "1", "6", name="Other"), _pred("K01", "1", "12")]
    recs = ra.snapshot_headways(rows)
    bunches = ra.find_bunches(recs)
    gaps = ra.find_gaps(recs)
    assert len(bunches) == 1
    assert bunches[0]["station_code"] == "E03"
    assert bunches[0]["headway"] == 2
    assert bunches[0]["train_etas"] == [3, 5]
    assert len(gaps) == 1
    assert gaps[0]["gap"] == 20
    assert gaps[0]["next_train_eta"] == 25


def test_station_headway_summary_counts_snapshots():
    t0 = "2026-11-09T21:00:00+00:00"
    t1 = "2026-11-09T21:01:00+00:00"
    rows = ([_pred("E03", "1", "1", ts=t0), _pred("E03", "1", "3", ts=t0),
             _pred("E03", "1", "9", ts=t0)] +
            [_pred("E03", "1", "2", ts=t1), _pred("E03", "1", "10", ts=t1)])
    out = ra.station_headway_summary(rows)
    assert out["snapshots"] == 2
    assert out["min_headway"] == 2
    assert out["max_headway"] == 8
    # snapshot 0 has a 2-min bunch (1,3); snapshot 1 does not (2,10)
    assert out["pct_snapshots_bunched"] == 50.0
    assert out["pct_snapshots_gapped"] == 0.0
    assert ra.station_headway_summary([]) == {"snapshots": 0}


def test_line_summary_counts_distinct_vehicles():
    vehicles = [{"vehicle_id": "018", "route_id": "RED"},
                {"vehicle_id": "055", "route_id": "RED"},
                {"vehicle_id": "101", "route_id": "GRN"},
                {"vehicle_id": "018", "route_id": "RED"}]  # dupe ignored
    out = ra.line_summary(vehicles)
    assert out == [{"line": "GRN", "vehicles": 1},
                   {"line": "RED", "vehicles": 2}]


def test_reports_over_db(db):
    now = dt.datetime.now(dt.timezone.utc)
    ts = now.isoformat()
    db.insert_predictions([
        RailPrediction(station_code="E03", station_name="U Street", line="GR",
                       destination="Greenbelt", minutes="2", group="1",
                       fetched_at=ts),
        RailPrediction(station_code="E03", station_name="U Street", line="GR",
                       destination="Greenbelt", minutes="4", group="1",
                       fetched_at=ts),
        RailPrediction(station_code="E03", station_name="U Street", line="GR",
                       destination="Greenbelt", minutes="30", group="1",
                       fetched_at=ts),
    ])
    db.insert_vehicle_positions([
        VehiclePosition(vehicle_id="101", route_id="GRN", fetched_at=ts)])
    rep = ra.station_headways_report(db, "E03", minutes=60)
    assert rep["snapshots"] == 1
    assert rep["min_headway"] == 2
    assert rep["pct_snapshots_bunched"] == 100.0
    bunch = ra.bunching_report(db)
    assert bunch["bunches"][0]["headway"] == 2
    assert bunch["gaps"][0]["gap"] == 26
    lines = ra.lines_report(db)
    assert lines["lines"] == [{"line": "GRN", "vehicles": 1}]


def test_directions_stay_separate_through_db(db):
    now = dt.datetime.now(dt.timezone.utc).isoformat()
    db.insert_predictions([
        RailPrediction(station_code="E03", station_name="U Street", line="GR",
                       destination="Greenbelt", minutes="2", group="1",
                       fetched_at=now),
        RailPrediction(station_code="E03", station_name="U Street", line="GR",
                       destination="Greenbelt", minutes="4", group="1",
                       fetched_at=now),
        RailPrediction(station_code="E03", station_name="U Street", line="GR",
                       destination="Branch Av", minutes="3", group="2",
                       fetched_at=now),
        RailPrediction(station_code="E03", station_name="U Street", line="GR",
                       destination="Branch Av", minutes="11", group="2",
                       fetched_at=now),
    ])
    recs = ra.snapshot_headways(db.latest_predictions())
    by_group = {r["group"]: r for r in recs}
    assert by_group["1"]["headways"] == [2]
    assert by_group["2"]["headways"] == [8]
