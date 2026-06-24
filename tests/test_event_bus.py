from __future__ import annotations

import asyncio

import pytest

from agentwall.inspector.event_bus import EventBus


def test_publish_no_loop_is_noop():
    bus = EventBus()
    q = bus.subscribe()
    bus.publish()  # loop not set — must not raise
    assert q.empty()


def test_subscribe_unsubscribe():
    bus = EventBus()
    q = bus.subscribe()
    assert q in bus._subscribers
    bus.unsubscribe(q)
    assert q not in bus._subscribers


def test_publish_no_subscribers_no_op():
    bus = EventBus()
    loop = asyncio.new_event_loop()
    bus.set_loop(loop)
    bus.publish()  # no subscribers — must not raise
    loop.close()


@pytest.mark.asyncio
async def test_publish_delivers_to_subscriber():
    bus = EventBus()
    bus.set_loop(asyncio.get_event_loop())
    q = bus.subscribe()
    bus.publish()
    msg = await asyncio.wait_for(q.get(), timeout=1.0)
    assert msg == {"type": "refresh"}
    bus.unsubscribe(q)


@pytest.mark.asyncio
async def test_publish_delivers_to_multiple_subscribers():
    bus = EventBus()
    bus.set_loop(asyncio.get_event_loop())
    q1 = bus.subscribe()
    q2 = bus.subscribe()
    bus.publish()
    m1 = await asyncio.wait_for(q1.get(), timeout=1.0)
    m2 = await asyncio.wait_for(q2.get(), timeout=1.0)
    assert m1 == {"type": "refresh"}
    assert m2 == {"type": "refresh"}
    bus.unsubscribe(q1)
    bus.unsubscribe(q2)


@pytest.mark.asyncio
async def test_unsubscribe_stops_delivery():
    bus = EventBus()
    bus.set_loop(asyncio.get_event_loop())
    q = bus.subscribe()
    bus.unsubscribe(q)
    bus.publish()
    assert q.empty()
