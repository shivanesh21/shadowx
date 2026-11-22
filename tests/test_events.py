"""
test_events.py — Unit tests for ShadowX events and in-process EventBus.
"""

import json
from pathlib import Path
from shadow.core.events import (
    RunStarted,
    AgentMessage,
    ToolCallEvent,
    ToolResultEvent,
    LLMCallEvent,
    StageFinished,
)
from shadow.core.event_bus import EventBus


def test_event_serialization():
    event = AgentMessage(run_id="run_123", agent_name="Analyst", content="Hello world")
    d = event.to_dict()

    assert d["run_id"] == "run_123"
    assert d["agent_name"] == "Analyst"
    assert d["content"] == "Hello world"
    assert d["event_type"] == "agent_message"
    assert "timestamp" in d
    assert "event_id" in d


def test_event_bus_subscription():
    bus = EventBus()
    received_specific = []
    received_all = []

    bus.subscribe(lambda e: received_specific.append(e), "tool_call")
    bus.subscribe(lambda e: received_all.append(e), "*")

    tc_event = ToolCallEvent(run_id="run_1", agent_name="Dev", tool_name="read_file", arguments={"path": "main.py"})
    msg_event = AgentMessage(run_id="run_1", agent_name="Dev", content="Reading file...")

    bus.emit(tc_event)
    bus.emit(msg_event)

    assert len(received_specific) == 1
    assert received_specific[0].tool_name == "read_file"
    assert len(received_all) == 2
    assert bus.history == [tc_event, msg_event]


def test_event_bus_file_logging(tmp_path: Path):
    log_file = tmp_path / "events.jsonl"
    bus = EventBus(log_path=log_file)

    event1 = RunStarted(run_id="r1", idea="CLI app")
    event2 = StageFinished(run_id="r1", stage="ANALYSIS", summary="Done")

    bus.emit(event1)
    bus.emit(event2)

    assert log_file.exists()
    lines = log_file.read_text(encoding="utf-8").strip().splitlines()
    assert len(lines) == 2

    parsed1 = json.loads(lines[0])
    parsed2 = json.loads(lines[1])

    assert parsed1["event_type"] == "run_started"
    assert parsed1["idea"] == "CLI app"
    assert parsed2["stage"] == "ANALYSIS"
