"""
Asynchronous Event Bus for Decoupled Inter-Agent Notifications and Audit Logging.
"""

import asyncio
from typing import Dict, List, Callable, Any, Type, TypeVar
from pydantic import BaseModel, Field
from datetime import datetime, timezone
import logging

logger = logging.getLogger("EventBus")


class SystemEvent(BaseModel):
    event_id: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    event_type: str
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    source_agent_id: str
    payload: Dict[str, Any] = Field(default_factory=dict)


E = TypeVar("E", bound=SystemEvent)


class EventBus:
    def __init__(self):
        self._subscribers: Dict[str, List[Callable[[SystemEvent], Any]]] = {}

    def subscribe(self, event_type: str, callback: Callable[[SystemEvent], Any]) -> None:
        if event_type not in self._subscribers:
            self._subscribers[event_type] = []
        self._subscribers[event_type].append(callback)

    async def publish(self, event: SystemEvent) -> None:
        logger.debug("Event published: %s from %s", event.event_type, event.source_agent_id)
        callbacks = self._subscribers.get(event.event_type, []) + self._subscribers.get("*", [])
        for cb in callbacks:
            try:
                res = cb(event)
                if asyncio.iscoroutine(res):
                    await res
            except Exception as e:
                logger.error("Error in event handler for %s: %s", event.event_type, e, exc_info=True)


# Global event bus
event_bus = EventBus()
