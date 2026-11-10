import asyncio
import datetime as dt
import json

import pytest

from transit_platform.mcp_server import create_server
from transit_platform.schemas import RailPrediction, StationInfo, StationStatus


@pytest.fixture
def mcp(db):
    now = dt.datetime.now(dt.timezone.utc)
    ts = now.isoformat()
    db.upsert_stations([StationInfo(station_id="st01", name="10th & U St NW",
                                    lat=38.9, lon=-77.0, capacity=20)], ts)
    db.insert_station_status([
        StationStatus(station_id="st01", fetched_at=ts,
                      num_bikes_available=7, num_docks_available=13)])
    db.insert_predictions([
        RailPrediction(station_code="E03", station_name="U Street", line="GR",
                       destination="Greenbelt", minutes="4", group="1",
                       fetched_at=ts),
        RailPrediction(station_code="E03", station_name="U Street", line="GR",
                       destination="Branch Av", minutes="6", group="2",
                       fetched_at=ts),
    ])
    return create_server(db=db)


def _call(mcp, name, args=None):
    content = asyncio.run(mcp.call_tool(name, args or {}))
    return json.loads(content[0].text)


def test_tools_registered(mcp):
    names = {t.name for t in asyncio.run(mcp.list_tools())}
    assert names == {
        "get_train_arrivals", "get_station_headways", "get_rail_bunching",
        "get_rail_lines", "get_bikeshare_summary", "get_bikeshare_movers",
        "find_bike_stations", "get_bike_station_stats",
    }


def test_get_train_arrivals(mcp):
    out = _call(mcp, "get_train_arrivals", {"station_code": "e03"})
    assert out["station_code"] == "E03"
    assert len(out["trains"]) == 2
    assert out["as_of"] is not None


def test_headways_and_bunching(mcp):
    out = _call(mcp, "get_station_headways",
                {"station_code": "E03", "minutes": 60})
    assert out["station_code"] == "E03"
    assert out["snapshots"] == 1
    out = _call(mcp, "get_rail_bunching")
    assert "bunches" in out and "gaps" in out


def test_bike_tools(mcp):
    out = _call(mcp, "get_bikeshare_summary")
    assert out["total_bikes_available"] == 7
    out = _call(mcp, "find_bike_stations", {"name": "U St"})
    assert out["stations"][0]["station_id"] == "st01"
    out = _call(mcp, "get_bike_station_stats",
                {"station_id": "st01", "minutes": 60})
    assert out["samples"] == 1
    out = _call(mcp, "get_bikeshare_movers", {"minutes": 60})
    assert out["movers"] == []  # one sample only
