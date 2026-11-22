"""
event_bus.py — In-process synchronous and asynchronous event bus.

Subscribers (CLI, JSONL file logger, SSE broadcaster) receive typed events
emitted by agents and the orchestrator.
"""

from __future__ import annotations
import json
import logging
from pathlib import Path
from typing import Callable, Any
from shadow.core.events import Event

logger = logging.getLogger(__name__)


class EventBus:
    """
    Central event dispatcher for a run.
    Handlers can subscribe to specific event types or '*' for all events.
    """

    def __init__(self, log_path: Path | None = None) -> None:
        self._handlers: dict[str, list[Callable[[Event], Any]]] = {}
        self._all_handlers: list[Callable[[Event], Any]] = []
        self._log_path = log_path
        self._event_history: list[Event] = []

        if self._log_path:
            self._log_path.parent.mkdir(parents=True, exist_ok=True)

    def subscribe(self, handler: Callable[[Event], Any], event_type: str = "*") -> None:
        """Register a callback for an event type or wildcard '*'."""
        if event_type == "*":
            self._all_handlers.append(handler)
        else:
            self._handlers.setdefault(event_type, []).append(handler)

    def emit(self, event: Event) -> None:
        """Publish an event to all registered subscribers and write to JSONL log."""
        self._event_history.append(event)

        # 1. Append to events.jsonl if configured
        if self._log_path:
            try:
                with open(self._log_path, "a", encoding="utf-8") as f:
                    f.write(json.dumps(event.to_dict()) + "\n")
            except Exception as e:
                logger.error(f"Failed to log event to {self._log_path}: {e}")

        # 2. Invoke wildcard handlers
        for handler in self._all_handlers:
            try:
                handler(event)
            except Exception as e:
                logger.exception(f"Error in wildcard event handler: {e}")

        # 3. Invoke specific event type handlers
        for handler in self._handlers.get(event.event_type, []):
            try:
                handler(event)
            except Exception as e:
                logger.exception(f"Error in {event.event_type} handler: {e}")

    @property
    def history(self) -> list[Event]:
        """Return the in-memory recorded events."""
        return list(self._event_history)
