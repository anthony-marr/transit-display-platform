import asyncio

from transit_platform.db import TransitDB
from transit_platform.hub import EventHub
from transit_platform.ingest import Poller

from conftest import make_gbfs_client


def test_bikeshare_poll_stores_and_broadcasts(tmp_path):
    db = TransitDB(f"sqlite:///{tmp_path}/ingest.db")
    hub = EventHub()

    async def run():
        queue = hub.subscribe()
        poller = Poller(db, hub, gbfs=make_gbfs_client())
        n = await poller.poll_station_status_once()
        assert n == 3
        event = queue.get_nowait()
        assert event["type"] == "bikeshare_status"
        assert event["data"]["stations_updated"] == 3
        assert len(event["data"]["stations"]) == 3

    asyncio.run(run())
    rows = db.latest_station_status()
    assert len(rows) == 3
    assert db.source_status()["sources"]["bikeshare_gbfs"]["snapshots"] == 1
    db.close()


def test_station_info_poll_upserts(tmp_path):
    db = TransitDB(f"sqlite:///{tmp_path}/info.db")
    hub = EventHub()

    async def run():
        poller = Poller(db, hub, gbfs=make_gbfs_client())
        assert await poller.poll_station_info_once() == 3
        assert await poller.poll_station_info_once() == 3  # upsert, not duplicate

    asyncio.run(run())
    assert db.source_status()["rows"]["stations"] == 3
    db.close()


def test_rail_poll_skips_without_key(tmp_path):
    db = TransitDB(f"sqlite:///{tmp_path}/rail.db")
    hub = EventHub()

    async def run():
        poller = Poller(db, hub, gbfs=make_gbfs_client(), wmata=None)
        result = await poller.poll_rail_once()
        assert "skipped" in result

    asyncio.run(run())
    db.close()
