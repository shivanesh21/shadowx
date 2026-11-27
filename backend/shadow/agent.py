"""
agent.py — Single-agent interface for ShadowX CLI.

Routes execution through shadow.core.Agent and shadow.tools.ToolRegistry.
Subscribes the terminal renderer directly to EventBus events, while streaming
structured logs to runs/default/events.jsonl.
"""

from __future__ import annotations
import os
import json
from pathlib import Path
from typing import Optional, Any

from rich.console import Console
from rich.panel import Panel
from rich.markdown import Markdown

from shadow.tools.registry import ToolRegistry
from shadow.core.agent import Agent, AgentSpec, AgentResult
from shadow.core.events import (
    Event,
    RunStarted,
    AgentMessage,
    ToolCallEvent,
    ToolResultEvent,
    FileChanged,
    TestResultEvent,
)
from shadow.core.event_bus import EventBus
from shadow.core.llm import GeminiProvider, LLMProvider

console = Console()

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------
MAX_STEPS    = 15                            # Hard cap on agentic iterations
HISTORY_FILE = Path("shadowx_history.json")  # Persisted conversation file
DEFAULT_LOG_PATH = Path("runs") / "default" / "events.jsonl"

SYSTEM_PROMPT = """\
You are ShadowX, a fast and proactive terminal AI coding agent.

Execution Rules:
1. Conversational messages (e.g. "hi", greetings, questions, explanations):
   - Answer directly, naturally, and concisely in 1 turn.
   - Do NOT create a plan. Do NOT call any tools.

2. Coding & file tasks:
   - Complete tasks autonomously in 2 to 3 steps maximum.
   - Write a minimal 1-2 bullet plan, then immediately call the required tools.
   - Do not hesitate or ask for permission — just execute the needed tools directly.
   - Conclude with a brief summary as soon as the task is finished.
"""


def _load_env_file() -> None:
    """Load key-value pairs from .env or ~/.shadow_env if present."""
    candidate_paths = [Path(".env"), Path.home() / ".shadow_env"]
    for path in candidate_paths:
        if path.exists():
            try:
                for line in path.read_text(encoding="utf-8").splitlines():
                    line = line.strip()
                    if line and not line.startswith("#") and "=" in line:
                        k, v = line.split("=", 1)
                        k = k.strip()
                        v = v.strip().strip("'\"")
                        if k and k not in os.environ:
                            os.environ[k] = v
            except Exception:
                pass


def load_history() -> list[dict]:
    """Load conversation history from disk (returns [] if none exists)."""
    if HISTORY_FILE.exists():
        try:
            data = json.loads(HISTORY_FILE.read_text(encoding="utf-8"))
            console.print(f"[dim]📂 Resumed history ({len(data)} turns)[/dim]")
            return data
        except Exception:
            pass
    return []


def save_history(history: list[dict]) -> None:
    """Persist conversation history to disk as JSON."""
    try:
        HISTORY_FILE.write_text(json.dumps(history, indent=2), encoding="utf-8")
    except Exception as e:
        console.print(f"[red]Warning: could not save history: {e}[/red]")


def clear_history() -> None:
    """Delete the saved history file."""
    if HISTORY_FILE.exists():
        HISTORY_FILE.unlink()
    console.print("[dim]🗑  History cleared.[/dim]")


def build_provider() -> LLMProvider:
    """Instantiate a GeminiProvider with automatic env loading."""
    _load_env_file()
    api_key = os.environ.get("GEMINI_API_KEY")

    if not api_key:
        try:
            console.print("[yellow]GEMINI_API_KEY is not set.[/yellow]")
            entered = console.input("[bold cyan]Enter your Gemini API key:[/bold cyan] ").strip()
            if entered:
                api_key = entered
                os.environ["GEMINI_API_KEY"] = api_key
                Path(".env").write_text(f"GEMINI_API_KEY={api_key}\nMODEL_NAME=gemini-3.5-flash-lite\n", encoding="utf-8")
                console.print("[green]Saved API key to .env for future runs.[/green]\n")
        except Exception:
            pass

    if not api_key:
        raise EnvironmentError(
            "GEMINI_API_KEY is not set. Add it to a .env file or run: $env:GEMINI_API_KEY='your_key'"
        )

    model_name = os.environ.get("MODEL_NAME", "gemini-3.5-flash-lite")
    return GeminiProvider(api_key=api_key, default_model=model_name)


def attach_cli_renderer(event_bus: EventBus) -> None:
    """
    Attach terminal UI rendering handlers to the EventBus.
    Decouples execution entirely from output presentation.
    """
    def on_run_started(event: Event) -> None:
        if isinstance(event, RunStarted):
            console.print(Panel(
                f"[bold cyan]🎯 Task:[/bold cyan] {event.idea}",
                border_style="cyan",
            ))

    def on_agent_message(event: Event) -> None:
        if isinstance(event, AgentMessage) and event.content:
            console.print(Panel(
                Markdown(event.content),
                title="[bold green]ShadowX[/bold green]",
                border_style="green",
            ))

    def on_tool_call(event: Event) -> None:
        if isinstance(event, ToolCallEvent):
            console.print(
                f"\n[bold magenta]🔧 Tool:[/bold magenta] [cyan]{event.tool_name}[/cyan]  "
                f"[dim]{event.arguments}[/dim]"
            )

    def on_tool_result(event: Event) -> None:
        if isinstance(event, ToolResultEvent):
            res_preview = event.result[:1000] + ("…" if len(event.result) > 1000 else "")
            border_color = "red" if event.is_error else "magenta"
            title_prefix = "Error: " if event.is_error else "Result: "
            console.print(Panel(
                res_preview,
                title=f"[{border_color}]{title_prefix}{event.tool_name}[/{border_color}]",
                border_style=border_color,
            ))

    def on_file_changed(event: Event) -> None:
        if isinstance(event, FileChanged):
            console.print(f"[dim cyan]📝 File modified:[/dim cyan] [bold]{event.path}[/bold]")

    def on_test_result(event: Event) -> None:
        if isinstance(event, TestResultEvent):
            color = "green" if event.failed == 0 and event.errors == 0 else "red"
            console.print(Panel(
                f"Passed: {event.passed} | Failed: {event.failed} | Errors: {event.errors}",
                title=f"[{color}]Pytest Results[/{color}]",
                border_style=color,
            ))

    event_bus.subscribe(on_run_started, "run_started")
    event_bus.subscribe(on_agent_message, "agent_message")
    event_bus.subscribe(on_tool_call, "tool_call")
    event_bus.subscribe(on_tool_result, "tool_result")
    event_bus.subscribe(on_file_changed, "file_changed")
    event_bus.subscribe(on_test_result, "test_result")


def run_task(
    task: str,
    history: list[dict],
    skip_confirm: bool = True,
    workspace_root: str = ".",
    log_path: Optional[Path] = DEFAULT_LOG_PATH,
) -> list[dict]:
    """
    Run one task through the hardened Agent engine and ToolRegistry.

    All terminal rendering is driven exclusively by EventBus subscriptions.
    All events are persisted to log_path (events.jsonl).
    """
    provider = build_provider()
    event_bus = EventBus(log_path=log_path)
    attach_cli_renderer(event_bus)

    registry = ToolRegistry(
        workspace_root=workspace_root,
        event_bus=event_bus,
        run_id="default",
    )

    tools = registry.get_all_tools(agent_name="ShadowX")
    declarations = registry.get_all_declarations()

    spec = AgentSpec(
        name="ShadowX",
        system_prompt=SYSTEM_PROMPT,
        allowed_tools=list(tools.keys()),
        max_steps=MAX_STEPS,
        require_finish_tool=False,
    )

    event_bus.emit(RunStarted(run_id="default", idea=task))

    agent = Agent(
        spec=spec,
        llm=provider,
        tool_registry=tools,
        tool_declarations=declarations,
        event_bus=event_bus,
    )

    result = agent.execute(task=task, initial_history=history)
    return result.history
