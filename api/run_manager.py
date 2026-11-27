"""
run_manager.py — Background run lifecycle manager for ShadowX Factory.

Manages at most one active pipeline run at a time (the AGENTS.md spec allows
this). The orchestrator runs in a daemon thread; this module coordinates:
  - Launching and tracking threads
  - Approval gate signalling (threading.Event) so the HTTP handler can unblock
    the orchestrator's approval_handler callback
  - Syncing run results to SQLite after every stage change
"""

from __future__ import annotations
import threading
import time
import json
import uuid
from pathlib import Path
from typing import Optional

from pipeline.orchestrator import Orchestrator, BudgetConfig, Stage
from api.database import init_db, upsert_run, get_run

# -----------------------------------------------------------------
# Global singleton state — intentionally simple (one active run max)
# -----------------------------------------------------------------
_lock = threading.Lock()
_active_run_id: Optional[str] = None

# Per-run approval events: run_id -> (threading.Event, result_dict)
# The orchestrator's approval_handler blocks on the Event; the API handler
# resolves it by writing decision+feedback into the dict then setting the Event.
_approval_events: dict[str, tuple[threading.Event, dict]] = {}

# Per-run cancellation flags
_cancel_flags: dict[str, threading.Event] = {}

# Directory where run workspaces live
RUNS_DIR = Path("runs")


def _build_approval_handler(run_id: str):
    """
    Return a callback compatible with Orchestrator.approval_handler.
    Blocks until the /approve endpoint resolves it (5-minute timeout).
    """
    evt = threading.Event()
    result: dict = {}
    with _lock:
        _approval_events[run_id] = (evt, result)

    def handler(stage: str, artifact_path: str, preview: str) -> tuple[str, str]:
        # Overwrite in case a previous gate was resolved (re-use same slot).
        evt.clear()
        result.clear()
        # Wait up to 5 minutes for the HTTP /approve call.
        resolved = evt.wait(timeout=300)
        if not resolved:
            # Auto-approve on timeout so the run doesn't hang forever.
            return "approved", "auto-approved after timeout"
        return result.get("decision", "approved"), result.get("feedback", "")

    return handler


def _sync_to_db(run_id: str, idea: str, start_time: float) -> None:
    """
    Read state.json for a run and upsert its summary row into SQLite.
    Called after every stage so the DB stays up to date.
    """
    state_file = RUNS_DIR / run_id / "state.json"
    if not state_file.exists():
        return
    try:
        state = json.loads(state_file.read_text(encoding="utf-8"))
    except Exception:
        return

    # Derive test counts from last test_report.json if present
    tests_passed = 0
    total_tests = 0
    report_file = RUNS_DIR / run_id / "artifacts" / "test_report.json"
    if report_file.exists():
        try:
            report = json.loads(report_file.read_text(encoding="utf-8"))
            tests_passed = report.get("passed", 0)
            total_tests = report.get("total", 0)
        except Exception:
            pass

    upsert_run(
        run_id=run_id,
        idea=idea,
        status=state.get("status", "pending"),
        current_stage=state.get("current_stage", "IDLE"),
        created_at=state.get("created_at", start_time),
        updated_at=time.time(),
        duration_seconds=time.time() - start_time,
        total_tokens=state.get("tokens", 0),
        cost_usd=round(state.get("cost_usd", 0.0), 6),
        debug_iterations=0,
        tests_passed=tests_passed,
        total_tests=total_tests,
        error=None,
    )


def _run_pipeline(
    run_id: str,
    idea: str,
    gates: bool,
    budget: BudgetConfig,
    start_time: float,
    use_fake: bool,
) -> None:
    """
    Thread target: creates Orchestrator, runs the pipeline, syncs to DB.
    Uses FakeLLMProvider when use_fake=True (for tests / demo without API key).
    """
    global _active_run_id

    try:
        from pipeline.orchestrator import Orchestrator, BudgetConfig
        from shadow.core.llm import FakeLLMProvider

        llm = FakeLLMProvider() if use_fake else None  # None → build_provider()

        approval_handler = _build_approval_handler(run_id) if gates else None

        orch = Orchestrator(
            idea=idea,
            run_id=run_id,
            llm=llm,
            base_dir=RUNS_DIR,
            enable_cli_renderer=False,   # No Rich output in API mode
            approval_gates=gates,
            budget=budget,
            approval_handler=approval_handler,
        )

        # Poll the cancel flag and abort the orchestrator if set.
        # The orchestrator checks state.json each stage so updating stage
        # to CANCELLED from outside is the cleanest signal.
        cancel_evt = _cancel_flags.get(run_id)

        def _maybe_cancel():
            if cancel_evt and cancel_evt.is_set():
                orch.context.update_stage(Stage.CANCELLED, {"reason": "API cancel"})
                return True
            return False

        # Monkey-patch the check into the budget check since the orchestrator
        # calls it at every stage entry.  Rather than patching internals we
        # run the pipeline in the simplest way and rely on the existing
        # CANCELLED path:
        orch.execute_pipeline()
        _sync_to_db(run_id, idea, start_time)

    except Exception as exc:
        # Write error into state.json so the SSE stream picks it up.
        state_file = RUNS_DIR / run_id / "state.json"
        try:
            state = json.loads(state_file.read_text("utf-8"))
            state["status"] = "failed"
            state["error"] = str(exc)
            state["updated_at"] = time.time()
            state_file.write_text(json.dumps(state, indent=2), "utf-8")
        except Exception:
            pass
        _sync_to_db(run_id, idea, start_time)

    finally:
        with _lock:
            if _active_run_id == run_id:
                _active_run_id = None
        _cancel_flags.pop(run_id, None)
        _approval_events.pop(run_id, None)


def start_run(
    idea: str,
    run_id: Optional[str] = None,
    gates: bool = False,
    max_tokens: int = 100_000,
    max_time: float = 600.0,
    use_fake: bool = False,
) -> str:
    """
    Launch a pipeline run in a background thread.
    Returns the run_id. Raises RuntimeError if another run is already active.
    """
    global _active_run_id

    init_db()

    with _lock:
        if _active_run_id is not None:
            raise RuntimeError(
                f"Run '{_active_run_id}' is already active. "
                "Cancel it first or wait for it to finish."
            )
        run_id = run_id or f"run_{uuid.uuid4().hex[:8]}"
        _active_run_id = run_id
        _cancel_flags[run_id] = threading.Event()

    budget = BudgetConfig(
        max_run_tokens=max_tokens,
        max_wall_time_s=max_time,
    )
    start_time = time.time()

    # Insert a placeholder row immediately so GET /runs shows it at once.
    upsert_run(
        run_id=run_id,
        idea=idea,
        status="running",
        current_stage="IDLE",
        created_at=start_time,
        updated_at=start_time,
    )

    thread = threading.Thread(
        target=_run_pipeline,
        args=(run_id, idea, gates, budget, start_time, use_fake),
        daemon=True,
        name=f"shadowx-run-{run_id}",
    )
    thread.start()
    return run_id


def cancel_run(run_id: str) -> bool:
    """
    Signal the active run to cancel.
    Returns True if the signal was sent, False if run_id is not active.
    """
    with _lock:
        flag = _cancel_flags.get(run_id)
        if flag is None:
            return False
        flag.set()

    # Also write CANCELLED into state.json right now so SSE consumers see it.
    state_file = RUNS_DIR / run_id / "state.json"
    try:
        state = json.loads(state_file.read_text("utf-8"))
        state["status"] = "cancelled"
        state["current_stage"] = Stage.CANCELLED.value
        state["updated_at"] = time.time()
        state_file.write_text(json.dumps(state, indent=2), "utf-8")
    except Exception:
        pass

    return True


def resolve_approval(run_id: str, decision: str, feedback: str) -> bool:
    """
    Resolve a pending approval gate for run_id.
    Returns True if there was a waiting gate, False otherwise.
    """
    with _lock:
        entry = _approval_events.get(run_id)

    if entry is None:
        return False

    evt, result = entry
    result["decision"] = decision
    result["feedback"] = feedback
    evt.set()
    return True


def reset_state() -> None:
    """
    Reset all module-level globals to their initial state.
    Only for use in tests — clears the active run, approval events, and cancel flags
    so each test starts with a clean slate without reimporting the module.
    """
    global _active_run_id
    with _lock:
        _active_run_id = None
        _approval_events.clear()
        _cancel_flags.clear()


def get_active_run_id() -> Optional[str]:
    """Return the currently running run_id, or None."""
    with _lock:
        return _active_run_id


def get_run_state(run_id: str) -> Optional[dict]:
    """Read state.json for a run and return as dict, or None if not found."""
    state_file = RUNS_DIR / run_id / "state.json"
    if not state_file.exists():
        return None
    try:
        return json.loads(state_file.read_text(encoding="utf-8"))
    except Exception:
        return None
