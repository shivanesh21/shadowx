"""
test_taxonomy.py — Unit tests for failure taxonomy classification and demo/eval endpoints.
"""

from __future__ import annotations
import json
from pathlib import Path
from fastapi.testclient import TestClient

from backend.main import app
from backend.evals.failure_taxonomy import (
    classify_message,
    analyze_failure_taxonomy,
    TaxonomyReport,
)

client = TestClient(app)


class TestFailureClassification:
    def test_classify_schema_error(self):
        msg = "ValidationError: missing field 'acceptance_criteria' in requirements.json"
        cat = classify_message(msg)
        assert cat == "SCHEMA_ERRORS"

    def test_classify_loop(self):
        msg = "Loop detected: agent repeating identical tool call 3 times"
        cat = classify_message(msg)
        assert cat == "LOOPS"

    def test_classify_conflict_permission(self):
        msg = "Analyst is not allowed to modify src/main.py: not permitted for role"
        cat = classify_message(msg)
        assert cat == "CONFLICTS"

    def test_classify_conflict_security(self):
        msg = "Access denied: path traversal not allowed"
        cat = classify_message(msg)
        assert cat == "CONFLICTS"

    def test_classify_drift(self):
        msg = "Missing acceptance criteria mapping in design.json: failed to meet requirement"
        cat = classify_message(msg)
        assert cat == "DRIFT"

    def test_analyze_failure_taxonomy_runs_cleanly(self):
        report = analyze_failure_taxonomy()
        assert isinstance(report, TaxonomyReport)
        assert report.total_runs_analyzed >= 0
        assert "SCHEMA_ERRORS" in report.counts
        assert "LOOPS" in report.counts
        assert "CONFLICTS" in report.counts
        assert "DRIFT" in report.counts


class TestDemoAndEvalEndpoints:
    def test_get_eval_benchmark(self):
        resp = client.get("/metrics/evals")
        assert resp.status_code == 200
        data = resp.json()
        assert data["tasks_tested"] == 8
        assert data["factory_success_rate"] == 1.0
        assert data["single_agent_success_rate"] == 0.375
        assert len(data["results"]) == 8
        assert "comparison_markdown" in data
        assert len(data["comparison_markdown"]) > 0

    def test_list_demo_runs(self):
        resp = client.get("/runs/demo/list")
        assert resp.status_code == 200
        demos = resp.json()
        assert isinstance(demos, list)
        demo_ids = [d["run_id"] for d in demos]
        assert "demo_bank_account_lib" in demo_ids

    def test_get_raw_events_demo_run(self):
        resp = client.get("/runs/demo_bank_account_lib/raw-events")
        assert resp.status_code == 200
        events = resp.json()
        assert isinstance(events, list)
        assert len(events) > 0
        event_types = {e.get("event_type") for e in events}
        assert "stage_started" in event_types

    def test_get_raw_events_404_for_unknown_run(self):
        resp = client.get("/runs/non_existent_run_xyz_123/raw-events")
        assert resp.status_code == 404
