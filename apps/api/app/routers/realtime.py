import asyncio
from typing import Annotated

from fastapi import APIRouter, Depends, Request
from fastapi.responses import StreamingResponse

from app.auth.dependencies import get_current_api_user
from app.realtime import realtime_broker, sse_message

router = APIRouter(tags=["realtime"])


@router.get("/events/stream")
async def stream_realtime_events(
    request: Request,
    current_user: Annotated[dict, Depends(get_current_api_user)],
) -> StreamingResponse:
    owner_user_id = str(current_user["id"])

    async def event_stream():
        yield sse_message({"type": "connected", "ownerUserId": owner_user_id})
        async with realtime_broker.subscribe(owner_user_id=owner_user_id) as subscriber:
            while not await request.is_disconnected():
                try:
                    event = await asyncio.wait_for(subscriber.queue.get(), timeout=25)
                except TimeoutError:
                    yield ": keep-alive\n\n"
                    continue
                yield sse_message(event)

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )
