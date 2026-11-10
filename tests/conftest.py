import json
import sys
from pathlib import Path

import httpx
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from transit_platform.db import TransitDB  # noqa: E402
from transit_platform.sources.gbfs import GBFSClient  # noqa: E402

FIXTURES = Path(__file__).parent / "fixtures"


def load_fixture(name: str) -> bytes:
    return (FIXTURES / name).read_bytes()


@pytest.fixture
def db():
    database = TransitDB("sqlite://")
    yield database
    database.close()


def make_gbfs_client(status=200):
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.host == "gbfs.lyft.com"
        if request.url.path.endswith("station_status.json"):
            body = load_fixture("station_status.json")
        elif request.url.path.endswith("station_information.json"):
            body = load_fixture("station_information.json")
        else:
            return httpx.Response(404)
        return httpx.Response(status, content=body)

    return GBFSClient(base_url="https://gbfs.lyft.com/gbfs/1.1/dca-cabi/en",
                      transport=httpx.MockTransport(handler))
