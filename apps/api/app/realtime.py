import asyncio
import contextlib
import json
from collections.abc import AsyncIterator
from dataclasses import dataclass, field
from typing import Any


@dataclass(eq=False)
class RealtimeSubscriber:
    owner_user_id: str
    queue: asyncio.Queue[dict[str, Any]] = field(default_factory=lambda: asyncio.Queue(maxsize=100))


class RealtimeBroker:
    def __init__(self) -> None:
        self._subscribers: set[RealtimeSubscriber] = set()

    @contextlib.asynccontextmanager
    async def subscribe(self, *, owner_user_id: str) -> AsyncIterator[RealtimeSubscriber]:
        subscriber = RealtimeSubscriber(owner_user_id=owner_user_id)
        self._subscribers.add(subscriber)
        try:
            yield subscriber
        finally:
            self._subscribers.discard(subscriber)

    def publish(self, event: dict[str, Any]) -> None:
        owner_user_id = str(event.get("ownerUserId") or "")
        if not owner_user_id:
            return
        self._publish_to(
            event,
            lambda subscriber: subscriber.owner_user_id == owner_user_id,
        )

    def publish_all(self, event: dict[str, Any]) -> None:
        self._publish_to(event, lambda _subscriber: True)

    def _publish_to(
        self,
        event: dict[str, Any],
        predicate,
    ) -> None:
        stale: list[RealtimeSubscriber] = []
        for subscriber in list(self._subscribers):
            if not predicate(subscriber):
                continue
            try:
                subscriber.queue.put_nowait(event)
            except asyncio.QueueFull:
                stale.append(subscriber)
        for subscriber in stale:
            self._subscribers.discard(subscriber)


realtime_broker = RealtimeBroker()


def sse_message(event: dict[str, Any]) -> str:
    event_type = str(event.get("type") or "message")
    data = json.dumps(event, separators=(",", ":"), ensure_ascii=False)
    return f"event: {event_type}\ndata: {data}\n\n"
