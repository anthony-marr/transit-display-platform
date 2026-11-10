from fastapi.testclient import TestClient

from transit_platform.api import create_app
from transit_platform.db import TransitDB
from transit_platform.hub import EventHub
from transit_platform.schemas import StationInfo, StationStatus


def _client(tmp_path):
    db = TransitDB(f"sqlite:///{tmp_path}/api.db")
    app = create_app(db=db, hub=EventHub(), ingest=False)
    return TestClient(app), db


def test_health(tmp_path):
    client, _ = _client(tmp_path)
    with client:
        resp = client.get("/health")
        assert resp.status_code == 200
        assert resp.json()["status"] == "ok"


def test_bikes_endpoint(tmp_path):
    client, db = _client(tmp_path)
    db.upsert_stations([StationInfo(station_id="s1", name="Test", lat=38.9,
                                    lon=-77.0, capacity=10)], "t0")
    db.insert_station_status([StationStatus(station_id="s1", fetched_at="t1",
                                            num_bikes_available=4, num_docks_available=6)])
    with client:
        body = client.get("/api/bikes/stations").json()
        assert body["stations"][0]["num_bikes_available"] == 4
        assert body["stations"][0]["name"] == "Test"


def test_status_endpoint(tmp_path):
    client, db = _client(tmp_path)
    db.record_snapshot("bikeshare_gbfs", "t1", b"{}")
    with client:
        body = client.get("/api/status").json()
        assert body["sources"]["bikeshare_gbfs"]["snapshots"] == 1


def test_websocket_hello_and_broadcast(tmp_path):
    client, _ = _client(tmp_path)
    with client:
        with client.websocket_connect("/ws/feed?stations=s1") as ws:
            hello = ws.receive_json()
            assert hello["type"] == "hello"
            assert hello["data"]["bike_filter"] == ["s1"]
            client.portal.call(client.app.state.hub.publish, {
                "type": "bikeshare_status", "ts": "t1",
                "data": {"stations_updated": 1, "total_bikes_available": 4,
                         "total_ebikes_available": 0,
                         "stations": [
                             {"station_id": "s1", "num_bikes_available": 4,
                              "num_docks_available": 6},
                             {"station_id": "s2", "num_bikes_available": 1,
                              "num_docks_available": 9},
                         ]},
            })
            event = ws.receive_json()
            assert event["type"] == "bikeshare_status"
            # the station filter kept only s1
            assert [s["station_id"] for s in event["data"]["stations"]] == ["s1"]
