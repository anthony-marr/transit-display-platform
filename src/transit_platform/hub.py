"""In-process pub/sub: pollers publish normalized events, WebSocket clients
subscribe. Slow or stuck clients drop events instead of blocking ingest."""
from __future__ import annotations

import asyncio


class EventHub:
    def __init__(self, queue_size: int = 100):
        self._queue_size = queue_size
        self._subs: set[asyncio.Queue] = set()

    def subscribe(self) -> asyncio.Queue:
        q: asyncio.Queue = asyncio.Queue(maxsize=self._queue_size)
        self._subs.add(q)
        return q

    def unsubscribe(self, q: asyncio.Queue) -> None:
        self._subs.discard(q)

    async def publish(self, event: dict) -> None:
        for q in list(self._subs):
            try:
                q.put_nowait(event)
            except asyncio.QueueFull:
                pass
