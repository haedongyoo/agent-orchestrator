"""
Redis Pub/Sub bridge — connects Celery worker events to FastAPI WebSocket broadcast.

Celery workers (step_results, etc.) call publish_event() to push events to Redis.
The FastAPI process runs subscribe_and_broadcast() as a background task, which
listens on Redis pub/sub and forwards events to in-memory WebSocket clients.
"""
from __future__ import annotations

import asyncio
import json
import uuid

import redis as sync_redis
import structlog

from app.config import settings

log = structlog.get_logger()

CHANNEL_PREFIX = "ws:thread:"


def publish_event(thread_id: uuid.UUID, event: dict) -> None:
    """Publish a WebSocket event from a synchronous context (Celery tasks)."""
    channel = f"{CHANNEL_PREFIX}{thread_id}"
    r = sync_redis.Redis.from_url(settings.redis_url)
    try:
        r.publish(channel, json.dumps(event, default=str))
    finally:
        r.close()


async def subscribe_and_broadcast() -> None:
    """Subscribe to Redis pub/sub and forward events to WebSocket clients.

    Runs as a long-lived background task inside the FastAPI process.
    Uses pattern subscribe on ``ws:thread:*`` to catch all thread events.
    """
    from redis.asyncio import Redis as AsyncRedis
    from app.services.connectors.webchat import broadcast

    r = AsyncRedis.from_url(settings.redis_url)
    pubsub = r.pubsub()
    await pubsub.psubscribe(f"{CHANNEL_PREFIX}*")

    log.info("pubsub.subscriber_started", pattern=f"{CHANNEL_PREFIX}*")

    try:
        async for message in pubsub.listen():
            if message["type"] != "pmessage":
                continue

            channel = message["channel"]
            if isinstance(channel, bytes):
                channel = channel.decode()

            thread_id_str = channel.removeprefix(CHANNEL_PREFIX)
            try:
                thread_id = uuid.UUID(thread_id_str)
                data = message["data"]
                if isinstance(data, bytes):
                    data = data.decode()
                event = json.loads(data)
                await broadcast(thread_id, event)
                log.debug(
                    "pubsub.broadcast_ok",
                    thread_id=thread_id_str,
                    event_type=event.get("type"),
                )
            except Exception:
                log.warning("pubsub.broadcast_error", exc_info=True)
    except asyncio.CancelledError:
        log.info("pubsub.subscriber_stopping")
    finally:
        await pubsub.punsubscribe()
        await r.aclose()
        log.info("pubsub.subscriber_stopped")
