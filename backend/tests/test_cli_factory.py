"""
test_cli_factory.py — Verification that two different ideas run all six stages from the CLI.
"""

import json
import subprocess
from pathlib import Path
import pytest

from pipeline.orchestrator import run_factory, Stage, RunContext
from shadow.core.llm import FakeLLMProvider, LLMResponse, FunctionCallData


def test_idea_1_cli_todo_app_all_six_stages(tmp_path: Path):
    """
    Idea 1: CLI Todo App with SQLite
    Executes all 6 stages through run_factory (the CLI entrypoint).
    """
    req_json = json.dumps({
        "project_name": "CLI Todo App",
        "summary": "Fast CLI todo manager with SQLite",
        "user_stories": [{"id": "US-1", "role": "User", "action": "add task", "benefit": "track work"}],
        "functional_requirements": ["add_task(desc)", "list_tasks()"],
        "non_functional_requirements": ["Fast startup"],
        "acceptance_criteria": {
            "AC-1": "add_task adds item",
            "AC-2": "list_tasks returns items",
        },
        "assumptions": ["Local SQLite"],
        "out_of_scope": ["Web interface"],
    })

    design_json = json.dumps({
        "project_name": "CLI Todo App",
        "tech_stack": ["Python", "sqlite3"],
        "modules": [{"file_path": "src/todo.py", "description": "Todo manager", "interfaces": ["def add_task(desc: str) -> int", "def list_tasks() -> list"]}],
        "data_models": ["Task(id, desc, done)"],
        "mermaid_diagram": "flowchart TD\n  CLI --> TodoService\n  TodoService --> DB[(SQLite)]",
        "ac_mapping": {"AC-1": ["src/todo.py"], "AC-2": ["src/todo.py"]},
    })

    code_content = """\
import sqlite3

def get_db():
    conn = sqlite3.connect(":memory:")
    conn.execute("CREATE TABLE IF NOT EXISTS tasks (id INTEGER PRIMARY KEY, desc TEXT)")
    return conn

_conn = get_db()

def add_task(desc: str) -> int:
    cur = _conn.cursor()
    cur.execute("INSERT INTO tasks (desc) VALUES (?)", (desc,))
    _conn.commit()
    return cur.lastrowid

def list_tasks() -> list:
    cur = _conn.cursor()
    cur.execute("SELECT desc FROM tasks")
    return [row[0] for row in cur.fetchall()]
"""

    test_content = """\
from src.todo import add_task, list_tasks

def test_ac1_add_task():
    tid = add_task("Buy bread")
    assert tid > 0

def test_ac2_list_tasks():
    add_task("Read book")
    tasks = list_tasks()
    assert "Read book" in tasks
"""

    test_report_json = json.dumps({
        "passed": 2, "failed": 0, "errors": 0,
        "ac_coverage": {"AC-1": "test_ac1_add_task", "AC-2": "test_ac2_list_tasks"},
        "failures": {},
    })

    review_content = "# Review: CLI Todo App\nSTATUS: APPROVED\n| AC-1 | add | src/todo.py | test_ac1_add_task | PASS |\n| AC-2 | list | src/todo.py | test_ac2_list_tasks | PASS |"
    readme_content = "# CLI Todo App\nA fast todo app with SQLite.\n## Usage\npython -m src.todo"

    provider = FakeLLMProvider()
    # 1. Analyst
    provider.queue_response(LLMResponse(function_calls=[
        FunctionCallData(name="write_file", args={"path": "docs/requirements.md", "content": "# Requirements"}),
        FunctionCallData(name="write_file", args={"path": "docs/requirements.json", "content": req_json}),
        FunctionCallData(name="finish", args={"summary": "Analyst done"}),
    ]))
    # 2. Architect
    provider.queue_response(LLMResponse(function_calls=[
        FunctionCallData(name="write_file", args={"path": "docs/design.md", "content": "# Design\nflowchart TD\n A-->B"}),
        FunctionCallData(name="write_file", args={"path": "docs/design.json", "content": design_json}),
        FunctionCallData(name="finish", args={"summary": "Architect done"}),
    ]))
    # 3. Developer
    provider.queue_response(LLMResponse(function_calls=[
        FunctionCallData(name="write_file", args={"path": "src/todo.py", "content": code_content}),
        FunctionCallData(name="run_command", args={"command": "python -c \"import src.todo as t; print(t.add_task('test'))\""}),
        FunctionCallData(name="finish", args={"summary": "Developer done"}),
    ]))
    # 4. Tester
    provider.queue_response(LLMResponse(function_calls=[
        FunctionCallData(name="write_file", args={"path": "tests/test_todo.py", "content": test_content}),
        FunctionCallData(name="run_tests", args={"test_path": "tests"}),
        FunctionCallData(name="write_file", args={"path": "test_report.json", "content": test_report_json}),
        FunctionCallData(name="finish", args={"summary": "Tests passed"}),
    ]))
    # 5. Reviewer
    provider.queue_response(LLMResponse(function_calls=[
        FunctionCallData(name="write_file", args={"path": "docs/review.md", "content": review_content}),
        FunctionCallData(name="finish", args={"summary": "Review complete"}),
    ]))
    # 6. Documenter
    provider.queue_response(LLMResponse(function_calls=[
        FunctionCallData(name="write_file", args={"path": "README.md", "content": readme_content}),
        FunctionCallData(name="write_file", args={"path": "docs/changelog.md", "content": "# Changelog"}),
        FunctionCallData(name="run_command", args={"command": "python -c \"import src.todo; print('verified')\""}),
        FunctionCallData(name="finish", args={"summary": "Docs complete"}),
    ]))

    from pipeline.orchestrator import Orchestrator
    orch = Orchestrator(
        idea="CLI Todo App with SQLite",
        run_id="idea1_todo_app",
        llm=provider,
        base_dir=tmp_path,
        enable_cli_renderer=False,
    )
    success = orch.execute_pipeline(target_stage=Stage.DONE)
    assert success is True

    # Validate all 6 stages produced deliverables
    ws = orch.context.workspace_dir
    assert (ws / "docs" / "requirements.md").exists()
    assert (ws / "docs" / "design.md").exists()
    assert (ws / "src" / "todo.py").exists()
    assert (ws / "tests" / "test_todo.py").exists()
    assert (ws / "docs" / "review.md").exists()
    assert (ws / "README.md").exists()

    # Check git log has 6 checkpoints
    git_log = subprocess.run(["git", "log", "--oneline"], cwd=str(ws), capture_output=True, text=True, check=True).stdout
    for stage_name in ["analysis", "design", "coding", "testing", "review", "docs"]:
        assert f"checkpoint({stage_name})" in git_log


def test_idea_2_expense_tracker_all_six_stages(tmp_path: Path):
    """
    Idea 2: Expense Tracker Library
    Executes all 6 stages through run_factory (the CLI entrypoint).
    """
    req_json = json.dumps({
        "project_name": "Expense Tracker",
        "summary": "Track expenses with categories",
        "user_stories": [{"id": "US-1", "role": "User", "action": "log expense", "benefit": "track spending"}],
        "functional_requirements": ["log_expense(amount, category)", "get_total()"],
        "non_functional_requirements": ["Accurate floats"],
        "acceptance_criteria": {
            "AC-1": "log_expense records amount",
            "AC-2": "get_total sums amounts",
        },
        "assumptions": ["EUR currency"],
        "out_of_scope": ["Tax calculation"],
    })

    design_json = json.dumps({
        "project_name": "Expense Tracker",
        "tech_stack": ["Python 3.10+"],
        "modules": [{"file_path": "src/tracker.py", "description": "Tracker module", "interfaces": ["def log_expense(amount: float, cat: str)", "def get_total() -> float"]}],
        "data_models": [],
        "mermaid_diagram": "flowchart TD\n  User --> Tracker[src/tracker.py]",
        "ac_mapping": {"AC-1": ["src/tracker.py"], "AC-2": ["src/tracker.py"]},
    })

    code_content = """\
_expenses = []

def log_expense(amount: float, category: str = "general") -> None:
    _expenses.append({"amount": float(amount), "category": category})

def get_total() -> float:
    return sum(item["amount"] for item in _expenses)
"""

    test_content = """\
from src.tracker import log_expense, get_total

def test_ac1_log_expense():
    log_expense(15.50, "food")
    assert get_total() >= 15.50

def test_ac2_get_total():
    log_expense(10.0, "transport")
    assert get_total() >= 25.50
"""

    test_report_json = json.dumps({
        "passed": 2, "failed": 0, "errors": 0,
        "ac_coverage": {"AC-1": "test_ac1_log_expense", "AC-2": "test_ac2_get_total"},
        "failures": {},
    })

    review_content = "# Review: Expense Tracker\nSTATUS: APPROVED\n| AC-1 | log | src/tracker.py | test_ac1_log_expense | PASS |\n| AC-2 | sum | src/tracker.py | test_ac2_get_total | PASS |"
    readme_content = "# Expense Tracker\nTrack expenses easily.\n## Example\n```python\nfrom src.tracker import log_expense, get_total\nlog_expense(50.0)\nprint(get_total())\n```"

    provider = FakeLLMProvider()
    provider.queue_response(LLMResponse(function_calls=[
        FunctionCallData(name="write_file", args={"path": "docs/requirements.md", "content": "# Requirements"}),
        FunctionCallData(name="write_file", args={"path": "docs/requirements.json", "content": req_json}),
        FunctionCallData(name="finish", args={"summary": "Analyst done"}),
    ]))
    provider.queue_response(LLMResponse(function_calls=[
        FunctionCallData(name="write_file", args={"path": "docs/design.md", "content": "# Design\nflowchart TD\n A-->B"}),
        FunctionCallData(name="write_file", args={"path": "docs/design.json", "content": design_json}),
        FunctionCallData(name="finish", args={"summary": "Architect done"}),
    ]))
    provider.queue_response(LLMResponse(function_calls=[
        FunctionCallData(name="write_file", args={"path": "src/tracker.py", "content": code_content}),
        FunctionCallData(name="run_command", args={"command": "python -c \"import src.tracker; print('OK')\""}),
        FunctionCallData(name="finish", args={"summary": "Developer done"}),
    ]))
    provider.queue_response(LLMResponse(function_calls=[
        FunctionCallData(name="write_file", args={"path": "tests/test_tracker.py", "content": test_content}),
        FunctionCallData(name="run_tests", args={"test_path": "tests"}),
        FunctionCallData(name="write_file", args={"path": "test_report.json", "content": test_report_json}),
        FunctionCallData(name="finish", args={"summary": "Tests passed"}),
    ]))
    provider.queue_response(LLMResponse(function_calls=[
        FunctionCallData(name="write_file", args={"path": "docs/review.md", "content": review_content}),
        FunctionCallData(name="finish", args={"summary": "Review complete"}),
    ]))
    provider.queue_response(LLMResponse(function_calls=[
        FunctionCallData(name="write_file", args={"path": "README.md", "content": readme_content}),
        FunctionCallData(name="write_file", args={"path": "docs/changelog.md", "content": "# Changelog"}),
        FunctionCallData(name="run_command", args={"command": "python -c \"from src.tracker import log_expense; log_expense(10); print('ok')\""}),
        FunctionCallData(name="finish", args={"summary": "Docs complete"}),
    ]))

    from pipeline.orchestrator import Orchestrator
    orch = Orchestrator(
        idea="Expense Tracker Library",
        run_id="idea2_expense_tracker",
        llm=provider,
        base_dir=tmp_path,
        enable_cli_renderer=False,
    )
    success = orch.execute_pipeline(target_stage=Stage.DONE)
    assert success is True

    # Validate all 6 stages produced deliverables
    ws = orch.context.workspace_dir
    assert (ws / "docs" / "requirements.md").exists()
    assert (ws / "docs" / "design.md").exists()
    assert (ws / "src" / "tracker.py").exists()
    assert (ws / "tests" / "test_tracker.py").exists()
    assert (ws / "docs" / "review.md").exists()
    assert (ws / "README.md").exists()

    # Check git log has 6 checkpoints
    git_log = subprocess.run(["git", "log", "--oneline"], cwd=str(ws), capture_output=True, text=True, check=True).stdout
    for stage_name in ["analysis", "design", "coding", "testing", "review", "docs"]:
        assert f"checkpoint({stage_name})" in git_log
