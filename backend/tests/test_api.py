"""
test_api.py — Tests for the ShadowX Factory FastAPI backend.

Uses the HTTPX test client (synchronous) with the FastAPI app.
All tests use FakeLLMProvider so no real API key is required.

Coverage:
  - POST /runs            → returns 201 with run_id
  - GET  /runs            → lists runs
  - GET  /runs/{id}       → returns run details
  - POST /runs/{id}/cancel → cancels a run
  - POST /runs/{id}/approve → resolves approval gate (gate not pending → 404)
  - GET  /runs/{id}/files → lists workspace files (or 404 if not yet created)
  - GET  /metrics/compare → returns aggregated stats
  - GET  /runs/{id}/events → SSE stream starts and contains run_started event
  - POST /runs            → 409 when another run is already active
"""

from __future__ import annotations
import json
import time
import threading
import tempfile
import shutil
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

# Redirect RUNS_DIR and DB_PATH to a temporary directory for isolation.
import backend.run_manager as rm_mod
import backend.sse as sse_mod
import backend.database as db_mod

# We'll patch these paths before importing the app.
_tmp_dir: Path = None


def _make_tmp() -> Path:
    return Path(tempfile.mkdtemp(prefix="shadowx_api_test_"))


@pytest.fixture(autouse=True)
def isolated_dirs(tmp_path, monkeypatch):
    """Redirect RUNS_DIR and DB to tmp_path for each test, and reset global state."""
    monkeypatch.setattr(rm_mod, "RUNS_DIR", tmp_path / "runs")
    monkeypatch.setattr(sse_mod, "RUNS_DIR", tmp_path / "runs")
    monkeypatch.setattr(db_mod, "DB_PATH", tmp_path / "test.db")
    # Also patch the import inside main.py
    import backend.main as main_mod
    monkeypatch.setattr(main_mod, "RUNS_DIR", tmp_path / "runs")
    db_mod.init_db()
    # Clear module-level active_run_id so tests are independent.
    rm_mod.reset_state()
    yield
    # Clean up any lingering active run after each test.
    rm_mod.reset_state()


@pytest.fixture()
def client():
    """Return a synchronous HTTPX test client for the FastAPI app."""
    from backend.main import app
    with TestClient(app, raise_server_exceptions=False) as c:
        yield c


# ---------------------------------------------------------------------------
# Helper: start a fake run and return the run_id
# ---------------------------------------------------------------------------

def _start_fake_run(client) -> str:
    resp = client.post("/runs", json={"idea": "Build a simple calculator", "use_fake": True})
    assert resp.status_code == 201
    return resp.json()["run_id"]


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

class TestCreateRun:
    def test_returns_201_with_run_id(self, client):
        resp = client.post("/runs", json={"idea": "CLI todo app", "use_fake": True})
        assert resp.status_code == 201
        body = resp.json()
        assert "run_id" in body
        assert body["status"] == "running"

    def test_custom_run_id(self, client):
        resp = client.post("/runs", json={"idea": "CLI todo app", "use_fake": True, "run_id": "my-run-42"})
        assert resp.status_code == 201
        assert resp.json()["run_id"] == "my-run-42"

    def test_idea_too_short_returns_422(self, client):
        resp = client.post("/runs", json={"idea": "hi"})
        assert resp.status_code == 422

    def test_409_when_run_already_active(self, client):
        # Start first run
        r1 = client.post("/runs", json={"idea": "First idea here", "use_fake": True})
        assert r1.status_code == 201
        # Second run should be blocked
        r2 = client.post("/runs", json={"idea": "Second idea here", "use_fake": True})
        assert r2.status_code == 409


class TestListRuns:
    def test_empty_list_initially(self, client):
        resp = client.get("/runs")
        assert resp.status_code == 200
        assert isinstance(resp.json(), list)

    def test_run_appears_after_creation(self, client):
        _start_fake_run(client)
        resp = client.get("/runs")
        assert resp.status_code == 200
        assert len(resp.json()) == 1


class TestGetRun:
    def test_returns_run_details(self, client):
        rid = _start_fake_run(client)
        resp = client.get(f"/runs/{rid}")
        assert resp.status_code == 200
        body = resp.json()
        assert body["run_id"] == rid

    def test_404_for_unknown_run(self, client):
        resp = client.get("/runs/nonexistent-run")
        assert resp.status_code == 404


class TestCancelRun:
    def test_cancel_active_run(self, client):
        rid = _start_fake_run(client)
        time.sleep(0.1)  # Give thread a moment to register
        resp = client.post(f"/runs/{rid}/cancel")
        # Either 200 (was active) or 404 (already finished — fast fake provider)
        assert resp.status_code in (200, 404)

    def test_cancel_unknown_run_returns_404(self, client):
        resp = client.post("/runs/ghost-run/cancel")
        assert resp.status_code == 404


class TestApprove:
    def test_approve_no_pending_gate_returns_404(self, client):
        rid = _start_fake_run(client)
        resp = client.post(f"/runs/{rid}/approve", json={"decision": "approved"})
        # No gate is pending (fake provider, no approval_gates=True)
        assert resp.status_code == 404

    def test_invalid_decision_returns_422(self, client):
        rid = _start_fake_run(client)
        resp = client.post(f"/runs/{rid}/approve", json={"decision": "maybe"})
        assert resp.status_code == 422


class TestListFiles:
    def test_no_workspace_returns_404(self, client):
        resp = client.get("/runs/nonexistent/files")
        assert resp.status_code == 404

    def test_workspace_files_listed(self, client, tmp_path, monkeypatch):
        """Create a minimal workspace and confirm listing works."""
        ws = tmp_path / "runs" / "run_abc" / "workspace"
        ws.mkdir(parents=True)
        (ws / "hello.txt").write_text("hi")
        import backend.main as main_mod
        monkeypatch.setattr(main_mod, "RUNS_DIR", tmp_path / "runs")
        resp = client.get("/runs/run_abc/files")
        assert resp.status_code == 200
        assert "hello.txt" in resp.json()


class TestMetricsCompare:
    def test_returns_summary(self, client):
        resp = client.get("/metrics/compare")
        assert resp.status_code == 200
        body = resp.json()
        assert "total_runs" in body
        assert "aggregates" in body

    def test_success_rate_after_run(self, client):
        _start_fake_run(client)
        resp = client.get("/metrics/compare")
        assert resp.status_code == 200
        assert resp.json()["total_runs"] >= 1

    def test_compare_with_run_ids(self, client):
        rid = _start_fake_run(client)
        resp = client.get(f"/metrics/compare?run_ids={rid}")
        assert resp.status_code == 200
        data = resp.json()
        assert len(data["selected_runs"]) == 1
        assert data["selected_runs"][0]["run_id"] == rid
        assert data["selected_aggregates"] is not None


class TestSSEStream:
    def test_sse_unknown_run_returns_error_event(self, client):
        """SSE stream for unknown run should emit an error event."""
        with client.stream("GET", "/runs/no-such-run/events") as resp:
            # Collect up to the first SSE chunk
            chunks = []
            for line in resp.iter_lines():
                chunks.append(line)
                if len(chunks) >= 5:
                    break
        full = "\n".join(chunks)
        assert "error" in full.lower() or "not found" in full.lower()

    def test_sse_emits_events_for_running_run(self, client, tmp_path, monkeypatch):
        """
        Write a fake events.jsonl with a run_started event and confirm the
        SSE stream replays it back without needing a real pipeline.
        """
        import backend.main as main_mod
        run_id = "sse-test-run"
        run_dir = tmp_path / "runs" / run_id
        run_dir.mkdir(parents=True)
        # Write a terminal state.json so the stream ends quickly
        state = {
            "run_id": run_id,
            "status": "done",
            "current_stage": "DONE",
            "idea": "test",
            "created_at": time.time(),
            "updated_at": time.time(),
            "tokens": 0,
            "artifacts": {},
            "checkpoints": {},
            "history": [],
        }
        (run_dir / "state.json").write_text(json.dumps(state))
        # Write a single fake event
        event_line = json.dumps({"type": "run_started", "run_id": run_id, "idea": "test"})
        (run_dir / "events.jsonl").write_text(event_line + "\n")

        monkeypatch.setattr(sse_mod, "RUNS_DIR", tmp_path / "runs")
        monkeypatch.setattr(main_mod, "RUNS_DIR", tmp_path / "runs")

        # Consume a few chunks of the SSE stream
        chunks = []
        with client.stream("GET", f"/runs/{run_id}/events") as resp:
            for line in resp.iter_lines():
                chunks.append(line)
                if len(chunks) >= 10:
                    break

        full = "\n".join(chunks)
        assert "run_started" in full


class TestRollbackRun:
    def test_rollback_unknown_run_returns_400(self, client):
        resp = client.post("/runs/nonexistent/rollback", json={"stage": "ANALYSIS"})
        assert resp.status_code == 400

    def test_rollback_invalid_stage_returns_400(self, client):
        resp = client.post("/runs/some-id/rollback", json={"stage": "INVALID_STAGE"})
        assert resp.status_code == 400


class TestPerRunMetrics:
    def test_per_run_metrics_404_for_unknown(self, client):
        resp = client.get("/runs/unknown-run-id/metrics")
        assert resp.status_code == 404

    def test_per_run_metrics_returns_details(self, client):
        rid = _start_fake_run(client)
        resp = client.get(f"/runs/{rid}/metrics")
        assert resp.status_code == 200
        data = resp.json()
        assert data["run_id"] == rid
        assert "stage_durations" in data
        assert "stage_tokens" in data


class TestZipExport:
    def test_zip_unknown_run_returns_404(self, client):
        resp = client.get("/runs/unknown-run-id/zip")
        assert resp.status_code == 404

    def test_zip_export_success(self, client, tmp_path, monkeypatch):
        import backend.main as main_mod
        rid = "zip-test-run"
        ws = tmp_path / "runs" / rid / "workspace"
        ws.mkdir(parents=True)
        (ws / "app.py").write_text("print('hello')")

        monkeypatch.setattr(main_mod, "RUNS_DIR", tmp_path / "runs")
        resp = client.get(f"/runs/{rid}/zip")
        assert resp.status_code == 200
        assert resp.headers["content-type"] == "application/zip"
        assert len(resp.content) > 0

