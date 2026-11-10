"""MCP server exposing the transit tools.

Run over stdio (what MCP hosts like Claude Desktop use):

    python -m transit_platform.mcp_server

The server reads the same store the ingest service writes, so tools answer
from live history: rail arrivals, headway and bunching analytics, and
bikeshare availability. Tools validate arguments with pydantic before
touching the store.
"""
from __future__ import annotations

from typing import Annotated, Optional

from mcp.server.fastmcp import FastMCP
from pydantic import Field

from . import analytics, rail_analytics
from .db import TransitDB

StationCode = Annotated[str, Field(
    min_length=2, max_length=4,
    description="WMATA station code, e.g. 'E03' for U Street/Cardozo")]
WindowMinutes = Annotated[int, Field(
    ge=1, le=10080, description="How far back to look, in minutes")]


def create_server(db: Optional[TransitDB] = None) -> FastMCP:
    database = db or TransitDB()

    mcp = FastMCP(
        "transit-platform",
        instructions=(
            "DC transit tools: live WMATA rail arrivals, headway and "
            "bunching analytics, and Capital Bikeshare availability. Data "
            "comes from the platform's own store, so answers are as fresh "
            "as the last poll (rail ~20s, bikeshare ~30s when ingest runs)."
        ),
    )

    @mcp.tool()
    def get_train_arrivals(station_code: StationCode) -> dict:
        """Upcoming trains at a Metro station from the latest prediction
        snapshot: line, destination, and minutes out per direction."""
        rows = database.latest_predictions()
        mine = [r for r in rows
                if r["station_code"] == station_code.upper()]
        return {"station_code": station_code.upper(),
                "as_of": max((r["fetched_at"] for r in mine), default=None),
                "trains": [{"line": r["line"], "destination": r["destination"],
                            "minutes": r["minutes"], "group": r.get("grp")}
                           for r in mine]}

    @mcp.tool()
    def get_station_headways(station_code: StationCode,
                             minutes: WindowMinutes = 60) -> dict:
        """Headway stats for a Metro station: how often trains come, the
        tightest gap between consecutive trains, and how often the station
        saw bunching or a service gap in the window."""
        return rail_analytics.station_headways_report(
            database, station_code.upper(), minutes=minutes)

    @mcp.tool()
    def get_rail_bunching() -> dict:
        """Bunches (trains arriving within 3 minutes of each other) and
        gaps (waits of 18+ minutes) across every watched Metro station in
        the latest snapshot."""
        return rail_analytics.bunching_report(database)

    @mcp.tool()
    def get_rail_lines() -> dict:
        """Trains currently reporting per Metro line."""
        return rail_analytics.lines_report(database)

    @mcp.tool()
    def get_bikeshare_summary() -> dict:
        """Capital Bikeshare system state: bikes and docks available,
        stations reporting, and which stations are empty or full."""
        return analytics.summary_report(database)

    @mcp.tool()
    def get_bikeshare_movers(minutes: WindowMinutes = 60,
                             limit: Annotated[int, Field(ge=1, le=100)] = 10
                             ) -> dict:
        """Bikeshare stations with the largest net bike change in the
        window - where bikes are draining and filling."""
        return analytics.movers_report(database, minutes=minutes, limit=limit)

    @mcp.tool()
    def find_bike_stations(name: Annotated[str, Field(
            min_length=2, description="Part of a station name, e.g. 'U St'")],
            limit: Annotated[int, Field(ge=1, le=50)] = 10) -> dict:
        """Search bikeshare stations by name to get their station_id for
        the other bike tools."""
        return {"stations": database.search_stations(name, limit)}

    @mcp.tool()
    def get_bike_station_stats(station_id: Annotated[str, Field(
            min_length=4, description="GBFS station_id, see find_bike_stations")],
            minutes: WindowMinutes = 1440) -> dict:
        """Availability stats for one bikeshare station: average bikes,
        and how much of the window it spent empty or full."""
        return analytics.station_stats_report(database, station_id,
                                              minutes=minutes)

    return mcp


def main():
    create_server().run()


if __name__ == "__main__":
    main()
