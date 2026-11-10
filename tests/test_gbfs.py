import json

from transit_platform.sources.gbfs import (parse_station_information,
                                           parse_station_status)

from conftest import load_fixture, make_gbfs_client


def test_parse_station_information():
    stations = parse_station_information(load_fixture("station_information.json"), "t0")
    assert len(stations) == 3
    s = stations[0]
    assert s.station_id
    assert s.name
    assert -90 <= s.lat <= 90 and -180 <= s.lon <= 180


def test_parse_station_status():
    last_updated, stations = parse_station_status(load_fixture("station_status.json"), "t0")
    assert isinstance(last_updated, int)
    assert len(stations) == 3
    for s in stations:
        assert s.num_bikes_available >= 0
        assert s.num_docks_available >= 0
        assert s.fetched_at == "t0"


def test_client_fetches_over_http():
    client = make_gbfs_client()
    feed = client.fetch_station_status()
    assert len(feed.stations) == 3
    assert json.loads(feed.raw)["data"]["stations"]
    info = client.fetch_station_information()
    assert len(info.stations) == 3


def test_client_raises_on_http_error():
    import pytest
    client = make_gbfs_client(status=500)
    with pytest.raises(Exception):
        client.fetch_station_status()
