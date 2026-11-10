import time

from google.transit import gtfs_realtime_pb2

from transit_platform.sources.wmata import (parse_predictions,
                                            parse_trip_updates,
                                            parse_vehicle_positions)


def _feed_with_vehicle() -> bytes:
    feed = gtfs_realtime_pb2.FeedMessage()
    feed.header.gtfs_realtime_version = "2.0"
    e = feed.entity.add()
    e.id = "e1"
    e.vehicle.trip.trip_id = "trip-123"
    e.vehicle.trip.route_id = "RED"
    e.vehicle.trip.direction_id = 0
    e.vehicle.vehicle.id = "501"
    e.vehicle.stop_id = "A01"
    e.vehicle.timestamp = int(time.time())
    return feed.SerializeToString()


def test_parse_vehicle_positions():
    vehicles = parse_vehicle_positions(_feed_with_vehicle(), "t0")
    assert len(vehicles) == 1
    v = vehicles[0]
    assert v.vehicle_id == "501"
    assert v.trip_id == "trip-123"
    assert v.route_id == "RED"
    assert v.direction_id == 0
    assert v.stop_id == "A01"
    assert v.fetched_at == "t0"


def test_parse_trip_updates():
    feed = gtfs_realtime_pb2.FeedMessage()
    feed.header.gtfs_realtime_version = "2.0"
    e = feed.entity.add()
    e.id = "e1"
    e.trip_update.trip.trip_id = "trip-9"
    e.trip_update.trip.route_id = "BLU"
    stu = e.trip_update.stop_time_update.add()
    stu.stop_id = "K01"
    stu.arrival.time = 1794300000
    stu.departure.time = 1794300030
    rows = parse_trip_updates(feed.SerializeToString(), "t0")
    assert len(rows) == 1
    r = rows[0]
    assert r.trip_id == "trip-9" and r.route_id == "BLU"
    assert r.stop_id == "K01"
    assert r.arrival_time == 1794300000 and r.departure_time == 1794300030


def test_parse_predictions_keeps_minutes_verbatim():
    payload = {"Trains": [
        {"Car": "8", "Destination": "ShadyGr", "DestinationCode": "A15",
         "DestinationName": "Shady Grove", "Group": "1", "Line": "RD",
         "LocationCode": "K01", "LocationName": "Metro Center", "Min": "3"},
        {"Car": "6", "Destination": "Glenmont", "DestinationCode": "B11",
         "DestinationName": "Glenmont", "Group": "2", "Line": "RD",
         "LocationCode": "K01", "LocationName": "Metro Center", "Min": "BRD"},
    ]}
    preds = parse_predictions(payload, "K01", "t0")
    assert [p.minutes for p in preds] == ["3", "BRD"]
    assert preds[0].destination == "Shady Grove"
    assert preds[1].line == "RD"
