"""
sse.py — Server-Sent Events stream generator for ShadowX Factory.

Streams events from the run's events.jsonl file. On connect it replays
all events after Last-Event-ID (line number), then tails the file for
new events until the run reaches a terminal state (done/failed/cancelled).

We use file polling (0.3s interval) rather than inotify so this works on
Windows without extra dependencies.
"""

from __future__ import annotations
import asyncio
import json
import time
from pathlib import Path
from typing import AsyncIterator

RUNS_DIR = Path("runs")
TERMINAL_STATUSES = {"done", "failed", "cancelled"}
POLL_INTERVAL = 0.3   # seconds between file-tail checks
MAX_TAIL_WAIT = 300   # seconds before giving up on a stalled run


def _is_run_terminal(run_id: str) -> bool:
    """Check state.json to see whether the run has ended."""
    state_file = RUNS_DIR / run_id / "state.json"
    try:
        state = json.loads(state_file.read_text(encoding="utf-8"))
        return state.get("status", "").lower() in TERMINAL_STATUSES
    except Exception:
        return False


async def event_stream(run_id: str, last_event_id: int = -1) -> AsyncIterator[dict]:
    """
    Async generator yielding SSE-compatible dicts with 'id', 'event', 'data'.

    last_event_id is the last line number the client already received,
    so -1 means start from the beginning (replay all history).
    """
    events_file = RUNS_DIR / run_id / "events.jsonl"

    # Wait up to 5s for the run to actually create its events file.
    waited = 0.0
    while not events_file.exists() and waited < 5.0:
        await asyncio.sleep(0.2)
        waited += 0.2

    if not events_file.exists():
        yield {"event": "error", "data": json.dumps({"message": f"Run '{run_id}' not found"})}
        return

    # Replay: read all lines after last_event_id and emit them.
    start_line = last_event_id + 1  # 0-indexed line to start from
    current_line = 0
    stall_timer = 0.0

    while True:
        try:
            lines = events_file.read_text(encoding="utf-8").splitlines()
        except Exception:
            lines = []

        # Emit any new lines since we last checked.
        while current_line < len(lines):
            if current_line >= start_line:
                raw = lines[current_line].strip()
                if raw:
                    yield {
                        "id": str(current_line),
                        "event": "message",
                        "data": raw,
                    }
            current_line += 1
            stall_timer = 0.0  # Reset stall counter whenever we emit something

        # Stop once the run is in a terminal state and we've sent everything.
        if _is_run_terminal(run_id):
            # Drain any remaining lines written between our last read and now.
            try:
                lines = events_file.read_text(encoding="utf-8").splitlines()
            except Exception:
                lines = []
            while current_line < len(lines):
                if current_line >= start_line:
                    raw = lines[current_line].strip()
                    if raw:
                        yield {
                            "id": str(current_line),
                            "event": "message",
                            "data": raw,
                        }
                current_line += 1

            # Final synthetic "done" event so the client knows to close.
            yield {
                "event": "done",
                "data": json.dumps({"run_id": run_id, "status": "terminal"}),
            }
            return

        stall_timer += POLL_INTERVAL
        if stall_timer > MAX_TAIL_WAIT:
            yield {
                "event": "error",
                "data": json.dumps({"message": "SSE timed out waiting for run events"}),
            }
            return

        await asyncio.sleep(POLL_INTERVAL)
