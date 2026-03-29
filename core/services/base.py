"""Base service class providing consistent lifecycle and health interface."""

import logging
from abc import ABC


class BaseService(ABC):
    """Abstract base for all Tonado services.

    Provides a common lifecycle (start/stop) and health reporting interface.
    Services may override start(), stop(), and health() as needed.
    """

    def __init__(self) -> None:
        self.logger = logging.getLogger(type(self).__name__)

    async def start(self) -> None:
        """Start the service. Override in subclass."""
        pass

    async def stop(self) -> None:
        """Stop the service. Override in subclass."""
        pass

    def health(self) -> dict:
        """Return health status. Override for detailed checks."""
        return {"status": "ok"}
