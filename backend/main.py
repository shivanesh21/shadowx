"""
main.py — FastAPI application for ShadowX Factory.

Endpoints:
  POST   /runs                       Start a new pipeline run
  GET    /runs                       List all runs (from SQLite)
  GET    /runs/{id}                  Full run state (state.json + SQLite)
  POST   /runs/{id}/cancel           Cancel the active run
  POST   /runs/{id}/approve          Resolve a human-in-the-loop approval gate
  GET    /runs/{id}/events           SSE stream with Last-Event-ID replay
  GET    /runs/{id}/files            List workspace files
  GET    /runs/{id}/files/{path}     Read a workspace file
  GET    /runs/{id}/artifacts        List validated stage artifacts
  GET    /runs/{id}/zip              Download workspace as ZIP
  GET    /metrics/compare            Compare factory vs single-agent metrics

Launch with:  python -m uvicorn api.main:app --reload
"""

from __future__ import annotations
import io
import json
import zipfile
import time
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Optional, Any

from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field
from sse_starlette.sse import EventSourceResponse

from backend.database import init_db, list_runs, get_run, upsert_run
from backend.run_manager import (
    start_run,
    cancel_run,
    rollback_run,
    resolve_approval,
    get_run_state,
    get_active_run_id,
    RUNS_DIR,
)
from backend.sse import event_stream

# ---------------------------------------------------------------------------
# App setup
# ---------------------------------------------------------------------------


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Initialise SQLite schema on startup (modern lifespan pattern)."""
    init_db()
    yield


app = FastAPI(
    title="ShadowX Factory API",
    version="1.0.0",
    description=(
        "Multi-agent AI software factory: idea → requirements → design → "
        "code → tests → review → docs, observable live via SSE."
    ),
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ---------------------------------------------------------------------------
# Request / response models
# ---------------------------------------------------------------------------

class StartRunRequest(BaseModel):
    idea: str = Field(..., description="One-line product idea", min_length=5)
    run_id: Optional[str] = Field(None, description="Custom run ID (auto-generated if omitted)")
    gates: bool = Field(False, description="Enable human-in-the-loop approval gates")
    max_tokens: int = Field(100_000, description="Per-run token budget", gt=0)
    max_time: float = Field(600.0, description="Wall-clock timeout in seconds", gt=0)
    use_fake: bool = Field(False, description="Use FakeLLMProvider (no API key needed; for demos/tests)")


class ApproveRequest(BaseModel):
    decision: str = Field(..., description="'approved', 'rejected', or 'edited'")
    feedback: str = Field("", description="Feedback text sent back to the agent (for rejected/edited)")


class RollbackRequest(BaseModel):
    stage: str = Field(..., description="Target stage to rollback to (e.g. 'ANALYSIS', 'DESIGN', 'CODING')")


# ---------------------------------------------------------------------------
# Run lifecycle
# ---------------------------------------------------------------------------

@app.post("/runs", status_code=201)
def create_run(body: StartRunRequest) -> dict:
    """Start a new pipeline run. Returns the run_id immediately; pipeline runs async."""
    try:
        rid = start_run(
            idea=body.idea,
            run_id=body.run_id,
            gates=body.gates,
            max_tokens=body.max_tokens,
            max_time=body.max_time,
            use_fake=body.use_fake,
        )
    except RuntimeError as exc:
        raise HTTPException(status_code=409, detail=str(exc))

    return {
        "run_id": rid,
        "status": "running",
        "message": f"Pipeline started. Stream events at /runs/{rid}/events",
    }


@app.get("/runs")
def get_runs() -> list[dict]:
    """List all runs ordered by creation time descending."""
    return list_runs()


@app.get("/runs/{run_id}")
def get_run_detail(run_id: str) -> dict:
    """
    Return the merged view: SQLite summary + full state.json.
    state.json is the authoritative source for in-flight runs.
    """
    state = get_run_state(run_id)
    db_row = get_run(run_id)

    if state is None and db_row is None:
        raise HTTPException(status_code=404, detail=f"Run '{run_id}' not found")

    merged: dict[str, Any] = {}
    if db_row:
        merged.update(db_row)
    if state:
        # state.json fields take precedence for live accuracy
        merged.update(state)
    return merged


@app.post("/runs/{run_id}/cancel")
def cancel(run_id: str) -> dict:
    """Cancel the active run. No-op if the run is already finished."""
    sent = cancel_run(run_id)
    if not sent:
        raise HTTPException(
            status_code=404,
            detail=f"Run '{run_id}' is not active (already finished or not found)",
        )
    return {"run_id": run_id, "status": "cancelling"}


@app.post("/runs/{run_id}/approve")
def approve(run_id: str, body: ApproveRequest) -> dict:
    """Resolve a human-in-the-loop approval gate that the pipeline is waiting on."""
    if body.decision not in ("approved", "rejected", "edited"):
        raise HTTPException(
            status_code=422,
            detail="decision must be 'approved', 'rejected', or 'edited'",
        )
    resolved = resolve_approval(run_id, body.decision, body.feedback)
    if not resolved:
        raise HTTPException(
            status_code=404,
            detail=f"No pending approval gate for run '{run_id}'",
        )
    return {"run_id": run_id, "decision": body.decision, "status": "resolved"}


@app.post("/runs/{run_id}/rollback")
def rollback_stage(run_id: str, body: RollbackRequest) -> dict:
    """Roll back the run workspace to the checkpoint of a previous stage."""
    success = rollback_run(run_id, body.stage)
    if not success:
        raise HTTPException(
            status_code=400,
            detail=f"Rollback failed: either run '{run_id}' not found, stage '{body.stage}' invalid, or no checkpoint exists for that stage.",
        )
    return {"run_id": run_id, "stage": body.stage.upper(), "status": "rolled_back"}


# ---------------------------------------------------------------------------
# SSE event stream
# ---------------------------------------------------------------------------

@app.get("/runs/{run_id}/events")
async def sse_events(run_id: str, request: Request) -> EventSourceResponse:
    """
    Server-Sent Events stream for a run.

    Supports Last-Event-ID header for replay: the client can reconnect and
    receive only events after the last one it saw.
    """
    # Parse Last-Event-ID header (line number into events.jsonl).
    raw_last = request.headers.get("last-event-id", "-1")
    try:
        last_id = int(raw_last)
    except ValueError:
        last_id = -1

    async def generator():
        async for ev in event_stream(run_id, last_event_id=last_id):
            yield ev

    return EventSourceResponse(generator())


# ---------------------------------------------------------------------------
# File browser
# ---------------------------------------------------------------------------

@app.get("/runs/{run_id}/files")
def list_files(run_id: str) -> list[str]:
    """Return all file paths in the run workspace (relative to workspace root)."""
    workspace = RUNS_DIR / run_id / "workspace"
    if not workspace.exists():
        raise HTTPException(status_code=404, detail=f"Workspace for run '{run_id}' not found")

    paths = []
    for p in workspace.rglob("*"):
        if p.is_file():
            # Return unix-style relative paths for portability
            paths.append(p.relative_to(workspace).as_posix())
    return sorted(paths)


@app.get("/runs/{run_id}/files/{file_path:path}")
def read_file(run_id: str, file_path: str) -> dict:
    """Read a file from the run workspace. Returns content as a string."""
    workspace = RUNS_DIR / run_id / "workspace"
    if not workspace.exists():
        raise HTTPException(status_code=404, detail=f"Workspace for run '{run_id}' not found")

    # Prevent path traversal
    target = (workspace / file_path).resolve()
    if not str(target).startswith(str(workspace.resolve())):
        raise HTTPException(status_code=400, detail="Path traversal not allowed")

    if not target.exists() or not target.is_file():
        raise HTTPException(status_code=404, detail=f"File '{file_path}' not found")

    try:
        content = target.read_text(encoding="utf-8", errors="replace")
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))

    return {
        "run_id": run_id,
        "path": file_path,
        "size_bytes": target.stat().st_size,
        "content": content,
    }


# ---------------------------------------------------------------------------
# Artifacts
# ---------------------------------------------------------------------------

@app.get("/runs/{run_id}/artifacts")
def list_artifacts(run_id: str) -> dict:
    """
    Return the validated stage artifacts recorded in state.json.
    Keys are artifact names; values are relative paths in the workspace.
    """
    state = get_run_state(run_id)
    if state is None:
        raise HTTPException(status_code=404, detail=f"Run '{run_id}' not found")
    artifacts = state.get("artifacts", {})

    # Enrich with file size and existence
    result = {}
    workspace = RUNS_DIR / run_id / "workspace"
    for name, rel_path in artifacts.items():
        full = workspace / rel_path
        result[name] = {
            "path": rel_path,
            "exists": full.exists(),
            "size_bytes": full.stat().st_size if full.exists() else 0,
        }
    return {"run_id": run_id, "artifacts": result}


# ---------------------------------------------------------------------------
# ZIP download
# ---------------------------------------------------------------------------

@app.get("/runs/{run_id}/zip")
def download_zip(run_id: str) -> StreamingResponse:
    """Stream the entire run workspace as a ZIP archive."""
    workspace = RUNS_DIR / run_id / "workspace"
    if not workspace.exists():
        raise HTTPException(status_code=404, detail=f"Workspace for run '{run_id}' not found")

    buf = io.BytesIO()
    with zipfile.ZipFile(buf, mode="w", compression=zipfile.ZIP_DEFLATED) as zf:
        for p in workspace.rglob("*"):
            if p.is_file():
                arcname = p.relative_to(workspace).as_posix()
                zf.write(p, arcname)
    buf.seek(0)

    return StreamingResponse(
        buf,
        media_type="application/zip",
        headers={"Content-Disposition": f'attachment; filename="{run_id}_workspace.zip"'},
    )


# ---------------------------------------------------------------------------
# Metrics comparison
# ---------------------------------------------------------------------------

@app.get("/metrics/compare")
def compare_metrics(run_ids: Optional[str] = None) -> dict:
    """
    Aggregate run metrics. When ``run_ids`` (comma-separated) is supplied,
    returns only those runs for a side-by-side comparison view.
    Always returns the global aggregates over ALL runs for the dashboard.
    """
    all_rows = list_runs()

    # Side-by-side selection (used by Compare screen)
    selected: list[dict] = []
    if run_ids:
        ids = [i.strip() for i in run_ids.split(",") if i.strip()]
        selected = [r for r in all_rows if r.get("run_id") in ids]

    def _aggregates(rows: list[dict]) -> dict:
        if not rows:
            return {
                "avg_tokens": 0,
                "avg_duration_seconds": 0.0,
                "total_cost_usd": 0.0,
                "avg_cost_usd": 0.0,
                "success_rate": 0.0,
                "total_done": 0,
                "total_failed": 0,
                "total_cancelled": 0,
                "avg_tests_passed": 0,
                "avg_debug_iterations": 0,
            }
        n = len(rows)
        done = sum(1 for r in rows if r.get("status") == "done")
        return {
            "avg_tokens": sum(r.get("total_tokens", 0) for r in rows) // n,
            "avg_duration_seconds": round(sum(r.get("duration_seconds", 0.0) for r in rows) / n, 1),
            "total_cost_usd": round(sum(r.get("cost_usd", 0.0) or 0.0 for r in rows), 4),
            "avg_cost_usd": round(sum(r.get("cost_usd", 0.0) or 0.0 for r in rows) / n, 4),
            "success_rate": round(done / n, 2),
            "total_done": done,
            "total_failed": sum(1 for r in rows if r.get("status") == "failed"),
            "total_cancelled": sum(1 for r in rows if r.get("status") == "cancelled"),
            "avg_tests_passed": sum(r.get("tests_passed", 0) for r in rows) // n,
            "avg_debug_iterations": round(sum(r.get("debug_iterations", 0) for r in rows) / n, 1),
        }

    return {
        "total_runs": len(all_rows),
        "runs": all_rows,
        "aggregates": _aggregates(all_rows),
        # Non-empty only when run_ids filter is active
        "selected_runs": selected,
        "selected_aggregates": _aggregates(selected) if selected else None,
    }


@app.get("/runs/{run_id}/metrics")
def per_run_metrics(run_id: str) -> dict:
    """
    Detailed per-run metrics card — combines SQLite summary with per-stage
    timing extracted from state.json history.
    """
    db_row = get_run(run_id)
    state = get_run_state(run_id)

    if db_row is None and state is None:
        raise HTTPException(status_code=404, detail=f"Run '{run_id}' not found")

    merged: dict[str, Any] = {}
    if db_row:
        merged.update(db_row)
    if state:
        merged.update(state)

    # Build per-stage timing from state history transitions
    stage_durations: dict[str, float] = {}
    history = merged.get("history", [])
    if history:
        for i, entry in enumerate(history):
            stage = entry.get("to", "")
            ts = entry.get("timestamp", 0)
            if i + 1 < len(history):
                next_ts = history[i + 1].get("timestamp", ts)
                stage_durations[stage] = round(next_ts - ts, 1)

    # Token / cost breakdown from events.jsonl if available
    events_file = RUNS_DIR / run_id / "events.jsonl"
    stage_tokens: dict[str, int] = {}
    if events_file.exists():
        try:
            current_stage = "ANALYSIS"
            for line in events_file.read_text(encoding="utf-8").splitlines():
                if not line.strip():
                    continue
                ev = json.loads(line)
                et = ev.get("event_type", "")
                if et == "stage_started":
                    current_stage = ev.get("stage", current_stage)
                elif et == "llm_call":
                    toks = ev.get("total_tokens", 0) or 0
                    stage_tokens[current_stage] = stage_tokens.get(current_stage, 0) + toks
        except Exception:
            pass

    return {
        **merged,
        "stage_durations": stage_durations,
        "stage_tokens": stage_tokens,
    }


# ---------------------------------------------------------------------------
# Static frontend mount
# ---------------------------------------------------------------------------

STATIC_DIR = Path(__file__).parent / "static"
if not STATIC_DIR.exists():
    STATIC_DIR = Path("static")
if STATIC_DIR.exists():
    app.mount("/", StaticFiles(directory=str(STATIC_DIR), html=True), name="static")
