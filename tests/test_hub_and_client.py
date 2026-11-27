import asyncio

from transit_platform.hub import EventHub
from transit_platform.pi_client import render_event


def test_hub_delivers_to_every_subscriber():
    async def run():
        hub = EventHub()
        a, b = hub.subscribe(), hub.subscribe()
        await hub.publish({"type": "x"})
        assert a.get_nowait() == {"type": "x"}
        assert b.get_nowait() == {"type": "x"}
    asyncio.run(run())


def test_hub_unsubscribe_stops_delivery():
    async def run():
        hub = EventHub()
        q = hub.subscribe()
        hub.unsubscribe(q)
        hub.unsubscribe(q)  # second call is harmless
        await hub.publish({"type": "x"})
        assert q.empty()
    asyncio.run(run())


def test_hub_drops_events_for_a_full_queue_without_blocking_others():
    async def run():
        hub = EventHub(queue_size=1)
        slow, fast = hub.subscribe(), hub.subscribe()
        await hub.publish({"n": 1})
        fast.get_nowait()
        await hub.publish({"n": 2})  # slow is full: dropped, no exception
        assert slow.get_nowait() == {"n": 1} and slow.empty()
        assert fast.get_nowait() == {"n": 2}
    asyncio.run(run())


def test_render_hello():
    out = render_event({"type": "hello", "data": {
        "version": "0.1", "rail": "on", "bike_filter": "all"}})
    assert out == "connected: platform v0.1 (rail on, bikes all)"


def test_render_rail_predictions_and_empty():
    event = {"type": "rail_predictions", "data": {
        "station_code": "A01",
        "predictions": [{"line": "RD", "destination": "Shady Grove",
                         "minutes": 4}]}}
    assert render_event(event) == "A01: RD -> Shady Grove 4 min"
    event["data"]["predictions"] = []
    assert render_event(event) == "A01: no predictions"


def test_render_rail_vehicles_counts_per_line():
    vehicles = [{"route_id": "RED"}, {"route_id": "RED"},
                {"route_id": None}, {"route_id": "BLUE"}]
    out = render_event({"type": "rail_vehicles", "data": {"vehicles": vehicles}})
    assert out == "trains: ? x1, BLUE x1, RED x2"


def test_render_bikeshare_summary_for_many_stations():
    data = {"stations": [{}] * 11, "stations_updated": 11,
            "total_bikes_available": 42}
    assert render_event({"type": "bikeshare_status", "data": data}) == \
        "bikes: 11 stations, 42 bikes available"


def test_render_unknown_event_is_truncated():
    out = render_event({"type": "weird", "data": {"k": "v" * 500}})
    assert out.startswith("weird: ") and len(out) == len("weird: ") + 200
