"""Lightweight async event bus for inter-service communication."""

import asyncio
import logging
from collections import defaultdict
from typing import Any, Callable, Coroutine

logger = logging.getLogger(__name__)

# Type alias for event handlers
EventHandler = Callable[..., Coroutine[Any, Any, None]]


class EventBus:
    """In-process async event bus using asyncio.

    Services publish events, other services subscribe to them.
    All handlers run concurrently via asyncio.gather.
    """

    def __init__(self) -> None:
        self._handlers: dict[str, list[EventHandler]] = defaultdict(list)

    def subscribe(self, event: str, handler: EventHandler) -> None:
        """Register a handler for an event type."""
        self._handlers[event].append(handler)
        logger.debug("Subscribed %s to '%s'", handler.__qualname__, event)

    def unsubscribe(self, event: str, handler: EventHandler) -> None:
        """Remove a handler for an event type."""
        try:
            self._handlers[event].remove(handler)
        except ValueError:
            pass

    async def publish(self, event: str, **kwargs: Any) -> None:
        """Publish an event, calling all registered handlers concurrently."""
        handlers = self._handlers.get(event, [])
        if not handlers:
            return

        logger.debug("Publishing '%s' to %d handler(s)", event, len(handlers))
        results = await asyncio.gather(
            *(h(**kwargs) for h in handlers),
            return_exceptions=True,
        )
        for i, result in enumerate(results):
            if isinstance(result, Exception):
                logger.error(
                    "Handler %s failed on '%s': %s",
                    handlers[i].__qualname__,
                    event,
                    result,
                )
