"""FastAPI service: REST over the store plus the WebSocket feed the Pi and
the dashboard subscribe to."""
from __future__ import annotations

import asyncio
import logging
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, Query, WebSocket, WebSocketDisconnect
from fastapi.responses import FileResponse

from . import analytics, config
from .db import TransitDB
from .hub import EventHub
from .ingest import Poller
from .schemas import utcnow_iso
from .sources.wmata import WMATAClient

log = logging.getLogger("transit_platform.api")
logging.basicConfig(level=logging.INFO)


def create_app(db: TransitDB | None = None, hub: EventHub | None = None,
               ingest: bool | None = None) -> FastAPI:
    enable_ingest = config.INGEST_ENABLED if ingest is None else ingest

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        app.state.db = db or TransitDB()
        app.state.hub = hub or EventHub()
        wmata = WMATAClient(config.WMATA_API_KEY) if config.WMATA_API_KEY else None
        app.state.poller = Poller(app.state.db, app.state.hub, wmata=wmata)
        task = asyncio.create_task(app.state.poller.run()) if enable_ingest else None
        log.info("transit platform up (ingest=%s, wmata=%s)",
                 enable_ingest, "key configured" if wmata else "no key - rail off")
        try:
            yield
        finally:
            if task:
                task.cancel()
                try:
                    await task
                except asyncio.CancelledError:
                    pass

    app = FastAPI(title="Transit Display Platform", version="0.1.0", lifespan=lifespan)

    @app.get("/health")
    def health():
        return {"status": "ok", "ts": utcnow_iso()}

    @app.get("/api/status")
    def status():
        return app.state.db.source_status()

    @app.get("/api/bikes/stations")
    def bikes(station_id: str | None = None, limit: int = Query(default=1000, le=5000)):
        return {"stations": app.state.db.latest_station_status(station_id, limit)}

    @app.get("/api/bikes/stations/{station_id}/history")
    def bike_history(station_id: str, limit: int = Query(default=200, le=2000)):
        return {"station_id": station_id,
                "history": app.state.db.station_history(station_id, limit)}

    @app.get("/api/rail/vehicles/latest")
    def rail_latest():
        return {"vehicles": app.state.db.latest_vehicle_positions()}

    @app.get("/api/analytics/bikes/summary")
    def bike_summary():
        return analytics.summary_report(app.state.db)

    @app.get("/api/analytics/bikes/movers")
    def bike_movers(minutes: int = Query(default=60, ge=1, le=10080),
                    limit: int = Query(default=10, ge=1, le=100)):
        return analytics.movers_report(app.state.db, minutes=minutes, limit=limit)

    @app.get("/api/analytics/bikes/stations/{station_id}/stats")
    def bike_station_stats(station_id: str,
                           minutes: int = Query(default=1440, ge=1, le=10080)):
        return analytics.station_stats_report(app.state.db, station_id, minutes=minutes)

    @app.get("/", include_in_schema=False)
    def dashboard():
        return FileResponse(Path(__file__).parent / "static" / "index.html")

    @app.websocket("/ws/feed")
    async def feed(ws: WebSocket, stations: str = Query(default="")):
        """Live event stream. Pass ?stations=id1,id2 to only receive
        bikeshare events for those stations; omit for the full feed."""
        await ws.accept()
        wanted = {s for s in stations.split(",") if s}
        await ws.send_json({
            "type": "hello", "ts": utcnow_iso(),
            "data": {
                "version": "0.1.0",
                "rail": "on" if config.WMATA_API_KEY else "off (no WMATA_API_KEY)",
                "bike_filter": sorted(wanted) if wanted else "all",
            },
        })
        queue = app.state.hub.subscribe()
        try:
            while True:
                event = await queue.get()
                if wanted and event.get("type") == "bikeshare_status":
                    rows = [s for s in event["data"]["stations"]
                            if s["station_id"] in wanted]
                    event = {**event,
                             "data": {**event["data"], "stations": rows}}
                await ws.send_json(event)
        except WebSocketDisconnect:
            pass
        finally:
            app.state.hub.unsubscribe(queue)

    return app


app = create_app()


def main():
    import uvicorn
    uvicorn.run("transit_platform.api:app", host="0.0.0.0", port=8000)


if __name__ == "__main__":
    main()
