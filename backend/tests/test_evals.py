"""
test_evals.py — Unit and integration tests for the benchmark evaluation suite.

Covers:
  - Task YAML loading, schema verification for all 8 required tasks
  - Hidden acceptance test grading engine (passing, failing, and error paths)
  - run_benchmark end-to-end execution with FakeLLMProvider
  - Deliverable generation: JSON results and Markdown comparison table
"""

from __future__ import annotations
import json
from pathlib import Path

import pytest
from evals.run_evals import (
    load_all_tasks,
    load_task_from_file,
    grade_workspace,
    run_benchmark,
    generate_comparison_table_md,
    generate_eval_results_json,
    TaskEvalResult,
    TASKS_DIR,
)

EXPECTED_EIGHT_TASKS = {
    "bank_account_lib",
    "cli_todo_app",
    "csv_summary_cleaner",
    "expense_tracker_sqlite",
    "markdown_to_html",
    "rate_limiter",
    "text_adventure_game",
    "url_shortener_api",
}


class TestTaskDefinitions:
    def test_all_eight_tasks_exist(self):
        tasks = load_all_tasks()
        loaded_ids = {t.id for t in tasks}
        missing = EXPECTED_EIGHT_TASKS - loaded_ids
        assert not missing, f"Missing expected task YAMLs: {missing}"
        assert len(tasks) >= 8

    @pytest.mark.parametrize("task_id", sorted(list(EXPECTED_EIGHT_TASKS)))
    def test_task_schema_and_hidden_tests_valid(self, task_id):
        yaml_file = TASKS_DIR / f"{task_id}.yaml"
        assert yaml_file.exists(), f"File {yaml_file} must exist"
        task = load_task_from_file(yaml_file)

        assert task.id == task_id
        assert len(task.name) > 0
        assert len(task.idea) >= 10, "Task idea must be descriptive"
        assert task.timeout_seconds > 0
        assert "def test_" in task.hidden_tests, "hidden_tests must define at least one pytest test function"


class TestGradingEngine:
    def test_grade_workspace_passes_valid_implementation(self, tmp_path: Path):
        ws = tmp_path / "workspace"
        src = ws / "src"
        src.mkdir(parents=True)
        (src / "math_mod.py").write_text("def add(a, b): return a + b\n", encoding="utf-8")

        hidden_code = (
            "import sys\nfrom pathlib import Path\n"
            "src = Path(__file__).resolve().parent.parent / 'src'\n"
            "sys.path.insert(0, str(src))\n"
            "from math_mod import add\n"
            "def test_addition():\n"
            "    assert add(2, 3) == 5\n"
        )

        grade = grade_workspace(ws, hidden_code)
        assert grade["success"] is True
        assert grade["passed"] == 1
        assert grade["failed"] == 0

    def test_grade_workspace_fails_broken_implementation(self, tmp_path: Path):
        ws = tmp_path / "workspace"
        src = ws / "src"
        src.mkdir(parents=True)
        (src / "math_mod.py").write_text("def add(a, b): return a - b\n", encoding="utf-8")

        hidden_code = (
            "import sys\nfrom pathlib import Path\n"
            "src = Path(__file__).resolve().parent.parent / 'src'\n"
            "sys.path.insert(0, str(src))\n"
            "from math_mod import add\n"
            "def test_addition():\n"
            "    assert add(2, 3) == 5\n"
        )

        grade = grade_workspace(ws, hidden_code)
        assert grade["success"] is False
        assert grade["failed"] >= 1


class TestBenchmarkExecution:
    def test_run_benchmark_dry_run_with_fake(self, tmp_path: Path):
        out_json = tmp_path / "eval_results.json"
        out_md = tmp_path / "comparison_table.md"
        eval_runs = tmp_path / "eval_runs"

        results = run_benchmark(
            task_ids=["bank_account_lib"],
            mode="both",
            runs_per_task=1,
            use_fake=True,
            output_json=out_json,
            output_md=out_md,
            eval_dir=eval_runs,
        )

        assert len(results) == 1
        res = results[0]
        assert res.task_id == "bank_account_lib"
        assert res.factory_passed is True
        assert res.single_passed is True

        # Check output files
        assert out_json.exists()
        assert out_md.exists()

        data = json.loads(out_json.read_text(encoding="utf-8"))
        assert data["tasks_tested"] == 1
        assert "results" in data

        md_content = out_md.read_text(encoding="utf-8")
        assert "| `bank_account_lib` |" in md_content
        assert "Summary Metrics" in md_content
