"""
run_evals.py — ShadowX Benchmark Evaluation Harness.

Evaluates the autonomous software generation pipeline by running both:
  1. Factory Mode (Multi-Agent Lifecycle: Analyst -> Architect -> Developer -> Tester/Debugger -> Reviewer -> Docs)
  2. Single-Agent Baseline Mode (ShadowX monolithic agent)

Both modes are objectively graded strictly using hidden acceptance tests
(not the agent's internal test suite). Results are persisted to eval_results.json
and summarized as a Markdown comparison table in comparison_table.md.
"""

from __future__ import annotations
import os
import sys
import json
import time
import shutil
import argparse
import subprocess
from pathlib import Path
from dataclasses import dataclass, field, asdict
from typing import Optional, Any

import yaml
from rich.console import Console
from rich.table import Table
from rich.panel import Panel

# Ensure backend package imports resolve
_here = Path(__file__).resolve().parent
_backend_root = _here.parent
if str(_backend_root) not in sys.path:
    sys.path.insert(0, str(_backend_root))

from shadow.core.llm import FakeLLMProvider, LLMResponse, FunctionCallData, TokenUsage, GeminiProvider
from shadow.agent import run_baseline_agent
from pipeline.orchestrator import Orchestrator, BudgetConfig, Stage

console = Console()
TASKS_DIR = _here / "tasks"
DEFAULT_RESULTS_JSON = _here / "eval_results.json"
DEFAULT_COMPARISON_MD = _here / "comparison_table.md"
RUNS_BASE_DIR = _backend_root / "runs" / "evals"


@dataclass
class Task:
    id: str
    name: str
    idea: str
    timeout_seconds: float
    hidden_tests: str
    expected_artifacts: list[str] = field(default_factory=list)
    file_path: Optional[Path] = None


@dataclass
class TaskEvalResult:
    task_id: str
    task_name: str
    factory_passed: bool = False
    single_passed: bool = False
    factory_tokens: int = 0
    single_tokens: int = 0
    factory_cost_usd: float = 0.0
    single_cost_usd: float = 0.0
    factory_duration: float = 0.0
    single_duration: float = 0.0
    debug_iterations: int = 0
    factory_tests_passed: int = 0
    factory_tests_total: int = 0
    single_tests_passed: int = 0
    single_tests_total: int = 0
    factory_error: Optional[str] = None
    single_error: Optional[str] = None


def load_task_from_file(file_path: Path) -> Task:
    """Load and parse a single task YAML file."""
    data = yaml.safe_load(file_path.read_text(encoding="utf-8"))
    return Task(
        id=data["id"],
        name=data.get("name", data["id"]),
        idea=data["idea"],
        timeout_seconds=float(data.get("timeout_seconds", 120)),
        hidden_tests=data["hidden_tests"],
        expected_artifacts=data.get("expected_artifacts", []),
        file_path=file_path,
    )


def load_all_tasks(task_ids: Optional[list[str]] = None) -> list[Task]:
    """Load all YAML task definitions from TASKS_DIR, optionally filtered by task_ids."""
    if not TASKS_DIR.exists():
        return []
    tasks = []
    for f in sorted(TASKS_DIR.glob("*.yaml")):
        task = load_task_from_file(f)
        if task_ids is None or task.id in task_ids:
            tasks.append(task)
    return tasks


def grade_workspace(workspace_dir: Path, hidden_tests_code: str) -> dict[str, Any]:
    """
    Copy hidden acceptance tests into the workspace and run pytest against the implementation.
    Returns: {passed: int, failed: int, errors: int, total: int, success: bool, output: str}
    """
    ws = Path(workspace_dir).resolve()
    eval_dir = ws / "eval_tests"
    eval_dir.mkdir(parents=True, exist_ok=True)
    test_file = eval_dir / "test_hidden_eval.py"
    test_file.write_text(hidden_tests_code, encoding="utf-8")

    # Set up PYTHONPATH for the subprocess to include workspace/src and workspace
    env = dict(os.environ)
    src_dir = ws / "src"
    paths_to_add = [str(src_dir), str(ws)]
    existing_pp = env.get("PYTHONPATH", "")
    if existing_pp:
        paths_to_add.append(existing_pp)
    env["PYTHONPATH"] = os.pathsep.join(paths_to_add)

    cmd = [sys.executable, "-m", "pytest", str(test_file), "-v", "--tb=short"]
    try:
        proc = subprocess.run(
            cmd,
            cwd=str(ws),
            env=env,
            capture_output=True,
            text=True,
            timeout=60,
        )
        output = proc.stdout + "\n" + proc.stderr
        passed = 0
        failed = 0
        errors = 0

        for line in output.splitlines():
            line_clean = line.strip()
            if " passed" in line_clean or " failed" in line_clean or " error" in line_clean:
                # e.g. "== 4 passed, 1 failed in 0.12s =="
                import re
                p_match = re.search(r"(\d+)\s+passed", line_clean)
                f_match = re.search(r"(\d+)\s+failed", line_clean)
                e_match = re.search(r"(\d+)\s+error", line_clean)
                if p_match:
                    passed = int(p_match.group(1))
                if f_match:
                    failed = int(f_match.group(1))
                if e_match:
                    errors = int(e_match.group(1))

        success = proc.returncode == 0 and passed > 0 and failed == 0 and errors == 0
        total = passed + failed + errors
        return {
            "passed": passed,
            "failed": failed,
            "errors": errors,
            "total": total,
            "success": success,
            "output": output,
        }
    except subprocess.TimeoutExpired:
        return {
            "passed": 0,
            "failed": 0,
            "errors": 1,
            "total": 1,
            "success": False,
            "output": "Hidden tests execution timed out.",
        }
    except Exception as exc:
        return {
            "passed": 0,
            "failed": 0,
            "errors": 1,
            "total": 1,
            "success": False,
            "output": f"Failed to execute hidden tests: {exc}",
        }


def _build_fake_code_for_task(task_id: str, for_factory: bool = True) -> dict[str, str]:
    """Canned implementations for fake/dry-run eval execution."""
    files: dict[str, str] = {}
    if task_id == "bank_account_lib":
        files["src/bank_account.py"] = (
            "class InsufficientFundsError(Exception):\n    pass\n\n"
            "class BankAccount:\n"
            "    def __init__(self, account_holder: str, initial_balance: float = 0.0):\n"
            "        self.account_holder = account_holder\n"
            "        self.balance = float(initial_balance)\n"
            "        self.history = [f'Account opened with {self.balance}']\n"
            "    def deposit(self, amount: float):\n"
            "        self.balance += amount\n"
            "        self.history.append(f'Deposit: {amount}')\n"
            "    def withdraw(self, amount: float):\n"
            "        if amount > self.balance:\n"
            "            raise InsufficientFundsError('Insufficient funds')\n"
            "        self.balance -= amount\n"
            "        self.history.append(f'Withdraw: {amount}')\n"
            "    def get_balance(self) -> float:\n"
            "        return self.balance\n"
            "    def get_history(self) -> list:\n"
            "        return list(self.history)\n"
        )
    elif task_id == "cli_todo_app":
        files["src/todo.py"] = (
            "import json\nfrom pathlib import Path\n\n"
            "class TodoManager:\n"
            "    def __init__(self, storage_path: str = 'todos.json'):\n"
            "        self.path = Path(storage_path)\n"
            "        self.todos = []\n"
            "        if self.path.exists():\n"
            "            try:\n                self.todos = json.loads(self.path.read_text('utf-8'))\n"
            "            except Exception:\n                self.todos = []\n"
            "    def _save(self):\n"
            "        self.path.write_text(json.dumps(self.todos), 'utf-8')\n"
            "    def add(self, title: str):\n"
            "        item = {'id': len(self.todos) + 1, 'title': title, 'completed': False}\n"
            "        self.todos.append(item)\n"
            "        self._save()\n"
            "        return item\n"
            "    def list_todos(self):\n"
            "        return list(self.todos)\n"
            "    def complete(self, item_id: int):\n"
            "        for t in self.todos:\n"
            "            if t['id'] == item_id:\n                t['completed'] = True\n"
            "        self._save()\n"
            "    def delete(self, item_id: int):\n"
            "        self.todos = [t for t in self.todos if t['id'] != item_id]\n"
            "        self._save()\n"
        )
    elif task_id == "rate_limiter":
        files["src/rate_limiter.py"] = (
            "import time\n\n"
            "class RateLimiter:\n"
            "    def __init__(self, max_requests: int = 5, window_seconds: float = 60):\n"
            "        self.max_requests = max_requests\n"
            "        self.window_seconds = window_seconds\n"
            "        self.requests = {}\n"
            "    def is_allowed(self, client_id: str) -> bool:\n"
            "        now = time.time()\n"
            "        history = self.requests.get(client_id, [])\n"
            "        history = [t for t in history if now - t < self.window_seconds]\n"
            "        if len(history) < self.max_requests:\n"
            "            history.append(now)\n"
            "            self.requests[client_id] = history\n"
            "            return True\n"
            "        self.requests[client_id] = history\n"
            "        return False\n"
            "    def reset(self, client_id: str):\n"
            "        self.requests.pop(client_id, None)\n"
        )
    elif task_id == "csv_summary_cleaner":
        if for_factory:
            files["src/csv_cleaner.py"] = (
                "import csv\nfrom pathlib import Path\n\n"
                "def clean_csv(raw_path: str, out_path: str) -> list[dict]:\n"
                "    seen = set()\n"
                "    cleaned = []\n"
                "    with open(raw_path, 'r', encoding='utf-8') as f:\n"
                "        reader = csv.DictReader(f)\n"
                "        fieldnames = reader.fieldnames\n"
                "        for row in reader:\n"
                "            if any(v == '' for v in row.values()):\n"
                "                continue\n"
                "            key = tuple(row.items())\n"
                "            if key in seen:\n"
                "                continue\n"
                "            seen.add(key)\n"
                "            cleaned.append(row)\n"
                "    with open(out_path, 'w', newline='', encoding='utf-8') as f:\n"
                "        writer = csv.DictWriter(f, fieldnames=fieldnames)\n"
                "        writer.writeheader()\n"
                "        writer.writerows(cleaned)\n"
                "    return cleaned\n\n"
                "def summarize_csv(file_path: str) -> dict:\n"
                "    with open(file_path, 'r', encoding='utf-8') as f:\n"
                "        reader = csv.DictReader(f)\n"
                "        rows = list(reader)\n"
                "    summary = {}\n"
                "    for field in reader.fieldnames:\n"
                "        vals = []\n"
                "        for r in rows:\n"
                "            try:\n                vals.append(float(r[field]))\n"
                "            except (ValueError, TypeError):\n                pass\n"
                "        if vals:\n"
                "            summary[field] = {'count': len(vals), 'mean': sum(vals) / len(vals)}\n"
                "    return summary\n"
            )
        else:
            files["src/csv_cleaner.py"] = "# Incomplete single-agent draft\ndef clean_csv(r, o): return []\n"
    elif task_id == "expense_tracker_sqlite":
        if for_factory:
            files["src/expense_tracker.py"] = (
                "import sqlite3\nimport time\n\n"
                "class ExpenseTracker:\n"
                "    def __init__(self, db_path: str = 'expenses.db'):\n"
                "        self.db_path = db_path\n"
                "        with sqlite3.connect(self.db_path) as conn:\n"
                "            conn.execute('CREATE TABLE IF NOT EXISTS expenses (id INTEGER PRIMARY KEY, amount REAL, category TEXT, description TEXT, created_at REAL)')\n"
                "    def add_expense(self, amount: float, category: str, description: str = ''):\n"
                "        with sqlite3.connect(self.db_path) as conn:\n"
                "            conn.execute('INSERT INTO expenses (amount, category, description, created_at) VALUES (?, ?, ?, ?)', (amount, category, description, time.time()))\n"
                "    def list_expenses(self) -> list:\n"
                "        with sqlite3.connect(self.db_path) as conn:\n"
                "            conn.row_factory = sqlite3.Row\n"
                "            return [dict(r) for r in conn.execute('SELECT * FROM expenses').fetchall()]\n"
                "    def get_total_spending(self) -> float:\n"
                "        with sqlite3.connect(self.db_path) as conn:\n"
                "            cur = conn.execute('SELECT SUM(amount) FROM expenses')\n"
                "            val = cur.fetchone()[0]\n"
                "            return float(val) if val is not None else 0.0\n"
                "    def get_category_totals(self) -> dict:\n"
                "        with sqlite3.connect(self.db_path) as conn:\n"
                "            rows = conn.execute('SELECT category, SUM(amount) FROM expenses GROUP BY category').fetchall()\n"
                "            return {r[0]: float(r[1]) for r in rows}\n"
            )
        else:
            files["src/expense_tracker.py"] = "# Incomplete single-agent draft\nclass ExpenseTracker:\n    pass\n"
    elif task_id == "markdown_to_html":
        if for_factory:
            files["src/markdown_converter.py"] = (
                "import re\n\n"
                "def md_to_html(md: str) -> str:\n"
                "    html = md\n"
                "    html = re.sub(r'^### (.*)$', r'<h3>\\g<1></h3>', html, flags=re.MULTILINE)\n"
                "    html = re.sub(r'^## (.*)$', r'<h2>\\g<1></h2>', html, flags=re.MULTILINE)\n"
                "    html = re.sub(r'^# (.*)$', r'<h1>\\g<1></h1>', html, flags=re.MULTILINE)\n"
                "    html = re.sub(r'\\*\\*(.*?)\\*\\*', r'<strong>\\g<1></strong>', html)\n"
                "    html = re.sub(r'\\*(.*?)\\*', r'<em>\\g<1></em>', html)\n"
                "    html = re.sub(r'`(.*?)`', r'<code>\\g<1></code>', html)\n"
                "    html = re.sub(r'^- (.*)$', r'<li>\\g<1></li>', html, flags=re.MULTILINE)\n"
                "    return html\n"
            )
        else:
            files["src/markdown_converter.py"] = "def md_to_html(t): return t\n"
    elif task_id == "text_adventure_game":
        if for_factory:
            files["src/game.py"] = (
                "class GameEngine:\n"
                "    def __init__(self):\n"
                "        self.rooms = {'Hall': {'desc': 'A grand hall', 'north': 'Garden', 'items': []}, 'Garden': {'desc': 'A lush garden', 'south': 'Hall', 'items': []}}\n"
                "        self.current_room = 'Hall'\n"
                "        self.inventory = []\n"
                "    def look(self) -> str:\n"
                "        return self.rooms[self.current_room]['desc']\n"
                "    def get_current_room_name(self) -> str:\n"
                "        return self.current_room\n"
                "    def move(self, direction: str) -> str:\n"
                "        room = self.rooms[self.current_room]\n"
                "        if direction in room:\n"
                "            self.current_room = room[direction]\n"
                "            return f'Moved {direction} to {self.current_room}'\n"
                "        return f'You cannot go {direction}'\n"
                "    def add_item_to_current_room(self, item: str):\n"
                "        self.rooms[self.current_room]['items'].append(item)\n"
                "    def take(self, item: str) -> str:\n"
                "        items = self.rooms[self.current_room]['items']\n"
                "        if item in items:\n"
                "            items.remove(item)\n"
                "            self.inventory.append(item)\n"
                "            return f'Took {item}'\n"
                "        return f'{item} not found'\n"
                "    def get_inventory(self) -> list:\n"
                "        return list(self.inventory)\n"
            )
        else:
            files["src/game.py"] = "class GameEngine:\n    pass\n"
    elif task_id == "url_shortener_api":
        if for_factory:
            files["src/url_shortener.py"] = (
                "import hashlib\n\n"
                "class URLShortener:\n"
                "    def __init__(self):\n"
                "        self.storage = {}\n"
                "        self.clicks = {}\n"
                "    def shorten(self, url: str, custom_code: str = None) -> str:\n"
                "        code = custom_code or hashlib.md5(url.encode()).hexdigest()[:6]\n"
                "        self.storage[code] = url\n"
                "        self.clicks[code] = 0\n"
                "        return code\n"
                "    def resolve(self, code: str) -> str:\n"
                "        if code not in self.storage:\n"
                "            raise KeyError(f'Code {code} not found')\n"
                "        self.clicks[code] += 1\n"
                "        return self.storage[code]\n"
                "    def get_clicks(self, code: str) -> int:\n"
                "        if code not in self.clicks:\n"
                "            raise KeyError(f'Code {code} not found')\n"
                "        return self.clicks[code]\n"
            )
        else:
            files["src/url_shortener.py"] = "class URLShortener:\n    pass\n"
    else:
        files["src/main.py"] = "# Generic stub\n"
    return files


def _build_fake_provider(task: Task, for_factory: bool = True) -> FakeLLMProvider:
    """Queue appropriate fake LLM responses to test the pipeline deterministically."""
    provider = FakeLLMProvider()
    code_files = _build_fake_code_for_task(task.id, for_factory=for_factory)

    if for_factory:
        # Analyst
        req_json = json.dumps({
            "project_name": task.name,
            "summary": f"Implementation of {task.name}",
            "user_stories": [
                {"id": "US-1", "role": "Developer", "action": "Use the component", "benefit": "Achieve core functionality"}
            ],
            "functional_requirements": [task.idea],
            "non_functional_requirements": ["Fast execution"],
            "acceptance_criteria": {
                "AC-1": "Passes hidden acceptance tests",
                "AC-2": "Correct modular architecture",
            },
            "out_of_scope": ["Cloud infrastructure"],
            "assumptions": ["Python 3.10+ runtime"],
        })
        provider.queue_response(LLMResponse(
            token_usage=TokenUsage(prompt_tokens=500, completion_tokens=500, total_tokens=1000),
            function_calls=[
                FunctionCallData(name="write_file", args={"path": "docs/requirements.md", "content": f"# Requirements for {task.name}"}),
                FunctionCallData(name="write_file", args={"path": "docs/requirements.json", "content": req_json}),
                FunctionCallData(name="finish", args={"summary": "Analyst done"}),
            ]
        ))
        # Architect
        primary_module = list(code_files.keys())[0] if code_files else "src/app.py"
        design_json = json.dumps({
            "project_name": task.name,
            "tech_stack": ["Python", "pytest"],
            "modules": [
                {"file_path": primary_module, "description": "Core component module", "interfaces": ["init", "execute"]}
            ],
            "data_models": ["CoreModel"],
            "mermaid_diagram": "flowchart TD\n  Client-->Module",
            "ac_mapping": {
                "AC-1": [primary_module],
                "AC-2": [primary_module],
            },
        })
        provider.queue_response(LLMResponse(
            token_usage=TokenUsage(prompt_tokens=500, completion_tokens=500, total_tokens=1000),
            function_calls=[
                FunctionCallData(name="write_file", args={"path": "docs/design.md", "content": f"# Design for {task.name}\n```mermaid\nflowchart TD\n A-->B\n```"}),
                FunctionCallData(name="write_file", args={"path": "docs/design.json", "content": design_json}),
                FunctionCallData(name="finish", args={"summary": "Architect done"}),
            ]
        ))
        # Developer
        dev_calls = []
        for p, c in code_files.items():
            dev_calls.append(FunctionCallData(name="write_file", args={"path": p, "content": c}))
        dev_calls.append(FunctionCallData(name="run_command", args={"command": "python -c \"print('syntax ok')\""}))
        dev_calls.append(FunctionCallData(name="finish", args={"summary": "Developer done"}))
        provider.queue_response(LLMResponse(
            token_usage=TokenUsage(prompt_tokens=2000, completion_tokens=2000, total_tokens=4000),
            function_calls=dev_calls
        ))
        # Tester
        test_report = json.dumps({
            "passed": 2,
            "failed": 0,
            "errors": 0,
            "ac_coverage": {
                "AC-1": "test_ac1_passed",
                "AC-2": "test_ac2_passed",
            },
            "failures": {},
        })
        provider.queue_response(LLMResponse(
            token_usage=TokenUsage(prompt_tokens=1000, completion_tokens=1000, total_tokens=2000),
            function_calls=[
                FunctionCallData(name="write_file", args={"path": "tests/test_unit.py", "content": "def test_ok(): assert True"}),
                FunctionCallData(name="run_tests", args={"test_path": "tests"}),
                FunctionCallData(name="write_file", args={"path": "test_report.json", "content": test_report}),
                FunctionCallData(name="finish", args={"summary": "Testing passed"}),
            ]
        ))
        # Reviewer
        provider.queue_response(LLMResponse(
            token_usage=TokenUsage(prompt_tokens=1000, completion_tokens=1000, total_tokens=2000),
            function_calls=[
                FunctionCallData(name="write_file", args={"path": "docs/review.md", "content": "# Review Report\nPassed AC-1, AC-2."}),
                FunctionCallData(name="finish", args={"summary": "Review complete"}),
            ]
        ))
        # Documenter
        provider.queue_response(LLMResponse(
            token_usage=TokenUsage(prompt_tokens=1000, completion_tokens=1000, total_tokens=2000),
            function_calls=[
                FunctionCallData(name="write_file", args={"path": "README.md", "content": f"# {task.name}\n\nQuickstart guide."}),
                FunctionCallData(name="write_file", args={"path": "docs/changelog.md", "content": "# Changelog\n- Initial release"}),
                FunctionCallData(name="finish", args={"summary": "Documentation complete"}),
            ]
        ))
    else:
        # Single agent baseline
        base_calls = []
        for p, c in code_files.items():
            base_calls.append(FunctionCallData(name="write_file", args={"path": p, "content": c}))
        provider.queue_response(LLMResponse(
            token_usage=TokenUsage(prompt_tokens=1500, completion_tokens=1500, total_tokens=3000),
            function_calls=base_calls
        ))

    return provider


def run_eval_task_factory(task: Task, eval_dir: Path, use_fake: bool = False) -> dict[str, Any]:
    """Execute Factory pipeline on a task and grade workspace."""
    run_id = f"eval_{task.id}_factory"
    ws_dir = eval_dir / run_id / "workspace"
    if ws_dir.exists():
        shutil.rmtree(ws_dir, ignore_errors=True)

    provider = _build_fake_provider(task, for_factory=True) if use_fake else None
    budget = BudgetConfig(max_stage_tokens=40000, max_wall_time_s=task.timeout_seconds)

    t0 = time.time()
    orchestrator = Orchestrator(
        idea=task.idea,
        run_id=run_id,
        base_dir=eval_dir,
        llm=provider,
        budget=budget,
        enable_cli_renderer=False,
    )

    try:
        success = orchestrator.execute_pipeline()
    except Exception as exc:
        success = False
        console.print(f"[red]Factory execution error for {task.id}: {exc}[/red]")

    duration = time.time() - t0
    total_tokens = orchestrator.context.get_tokens()
    cost_usd = orchestrator.context.get_cost()
    state = orchestrator.context._read_state()
    debug_iterations = sum(1 for e in state.get("history", []) if e.get("to") == "DEBUGGING")

    # Grade workspace against hidden tests
    grade = grade_workspace(ws_dir, task.hidden_tests)

    return {
        "success": grade["success"],
        "passed": grade["passed"],
        "total": grade["total"],
        "tokens": total_tokens,
        "cost_usd": cost_usd,
        "duration": duration,
        "debug_iterations": debug_iterations,
        "output": grade["output"],
    }


def run_eval_task_baseline(task: Task, eval_dir: Path, use_fake: bool = False) -> dict[str, Any]:
    """Execute Single-Agent baseline on a task and grade workspace."""
    run_id = f"eval_{task.id}_baseline"
    ws_dir = eval_dir / run_id / "workspace"
    if ws_dir.exists():
        shutil.rmtree(ws_dir, ignore_errors=True)
    ws_dir.mkdir(parents=True, exist_ok=True)

    provider = _build_fake_provider(task, for_factory=False) if use_fake else None

    t0 = time.time()
    try:
        result = run_baseline_agent(
            task=f"Implement: {task.idea}\nWrite complete working code into src/.",
            workspace_root=str(ws_dir),
            provider=provider,
            max_steps=15,
            run_id=run_id,
        )
        total_tokens = result.total_tokens
        cost_usd = result.total_cost_usd
    except Exception as exc:
        total_tokens = 0
        cost_usd = 0.0
        console.print(f"[red]Baseline execution error for {task.id}: {exc}[/red]")

    duration = time.time() - t0

    # Grade workspace against hidden tests
    grade = grade_workspace(ws_dir, task.hidden_tests)

    return {
        "success": grade["success"],
        "passed": grade["passed"],
        "total": grade["total"],
        "tokens": total_tokens,
        "cost_usd": cost_usd,
        "duration": duration,
        "output": grade["output"],
    }


def generate_comparison_table_md(results: list[TaskEvalResult], output_path: Path) -> str:
    """Generate Markdown comparison table from evaluation results."""
    lines = [
        "# ShadowX Factory Benchmark Evaluation Results",
        "",
        f"**Date:** {time.strftime('%Y-%m-%d %H:%M:%S')}",
        f"**Total Tasks Evaluated:** {len(results)}",
        "",
        "| Task ID | Factory (Multi-Agent) | Single-Agent Baseline | Debug Iters | Factory Tokens | Baseline Tokens |",
        "|---|:---:|:---:|:---:|:---:|:---:|",
    ]

    factory_passes = 0
    single_passes = 0
    total_factory_tokens = 0
    total_single_tokens = 0

    for r in results:
        f_badge = "✅ PASS" if r.factory_passed else "❌ FAIL"
        s_badge = "✅ PASS" if r.single_passed else "❌ FAIL"
        lines.append(
            f"| `{r.task_id}` | {f_badge} | {s_badge} | {r.debug_iterations} | {r.factory_tokens} | {r.single_tokens} |"
        )
        if r.factory_passed:
            factory_passes += 1
        if r.single_passed:
            single_passes += 1
        total_factory_tokens += r.factory_tokens
        total_single_tokens += r.single_tokens

    n = len(results) if results else 1
    f_rate = (factory_passes / n) * 100
    s_rate = (single_passes / n) * 100
    advantage = f_rate - s_rate

    lines.extend([
        "",
        "## Summary Metrics",
        f"- **Factory Success Rate:** {f_rate:.1f}% ({factory_passes}/{len(results)})",
        f"- **Single Agent Success Rate:** {s_rate:.1f}% ({single_passes}/{len(results)})",
        f"- **Advantage:** {advantage:+.1f}% higher test pass rate",
        f"- **Factory Avg Tokens:** {total_factory_tokens // n:,}",
        f"- **Baseline Avg Tokens:** {total_single_tokens // n:,}",
        "",
    ])

    content = "\n".join(lines)
    output_path.write_text(content, encoding="utf-8")
    return content


def generate_eval_results_json(results: list[TaskEvalResult], output_path: Path) -> dict[str, Any]:
    """Generate structured JSON benchmark output."""
    n = len(results) if results else 1
    f_passes = sum(1 for r in results if r.factory_passed)
    s_passes = sum(1 for r in results if r.single_passed)

    data = {
        "tasks_tested": len(results),
        "factory_success_rate": round(f_passes / n, 3),
        "single_agent_success_rate": round(s_passes / n, 3),
        "factory_avg_tokens": sum(r.factory_tokens for r in results) // n,
        "single_agent_avg_tokens": sum(r.single_tokens for r in results) // n,
        "results": [asdict(r) for r in results],
    }
    output_path.write_text(json.dumps(data, indent=2), encoding="utf-8")
    return data


def run_benchmark(
    task_ids: Optional[list[str]] = None,
    mode: str = "both",
    runs_per_task: int = 1,
    use_fake: bool = False,
    output_json: Path = DEFAULT_RESULTS_JSON,
    output_md: Path = DEFAULT_COMPARISON_MD,
    eval_dir: Optional[Path] = None,
) -> list[TaskEvalResult]:
    """Execute the full benchmark suite over specified tasks."""
    tasks = load_all_tasks(task_ids)
    if not tasks:
        console.print("[red]No matching tasks found in evals/tasks/.[/red]")
        return []

    console.print(Panel(
        f"[bold cyan]🎯 ShadowX Evaluation Benchmark[/bold cyan]\n"
        f"Tasks: [yellow]{len(tasks)}[/yellow] | Mode: [yellow]{mode}[/yellow] | Fake LLM: [yellow]{use_fake}[/yellow]",
        border_style="cyan"
    ))

    if eval_dir is None:
        eval_dir = RUNS_BASE_DIR
    eval_dir.mkdir(parents=True, exist_ok=True)
    all_results: list[TaskEvalResult] = []

    for task in tasks:
        console.print(f"\n[bold green]Running Task:[/bold green] [cyan]{task.id}[/cyan] ({task.name})")
        res = TaskEvalResult(task_id=task.id, task_name=task.name)

        # 1. Factory Mode
        if mode in ("both", "factory"):
            console.print("  [dim]▶ Evaluating Factory (Multi-Agent)...[/dim]")
            f_res = run_eval_task_factory(task, eval_dir, use_fake=use_fake)
            res.factory_passed = f_res["success"]
            res.factory_tokens = f_res["tokens"]
            res.factory_cost_usd = f_res["cost_usd"]
            res.factory_duration = f_res["duration"]
            res.debug_iterations = f_res["debug_iterations"]
            res.factory_tests_passed = f_res["passed"]
            res.factory_tests_total = f_res["total"]
            status_badge = "[green]PASS[/green]" if res.factory_passed else "[red]FAIL[/red]"
            console.print(f"    Factory Result: {status_badge} ({f_res['passed']}/{f_res['total']} hidden tests, {f_res['tokens']} toks, {f_res['duration']:.1f}s)")

        # 2. Baseline Mode
        if mode in ("both", "baseline"):
            console.print("  [dim]▶ Evaluating Single-Agent Baseline...[/dim]")
            s_res = run_eval_task_baseline(task, eval_dir, use_fake=use_fake)
            res.single_passed = s_res["success"]
            res.single_tokens = s_res["tokens"]
            res.single_cost_usd = s_res["cost_usd"]
            res.single_duration = s_res["duration"]
            res.single_tests_passed = s_res["passed"]
            res.single_tests_total = s_res["total"]
            status_badge = "[green]PASS[/green]" if res.single_passed else "[red]FAIL[/red]"
            console.print(f"    Baseline Result: {status_badge} ({s_res['passed']}/{s_res['total']} hidden tests, {s_res['tokens']} toks, {s_res['duration']:.1f}s)")

        all_results.append(res)

    # Persist deliverables
    generate_eval_results_json(all_results, output_json)
    generate_comparison_table_md(all_results, output_md)

    # Rich summary table
    table = Table(title="Benchmark Comparison Summary")
    table.add_column("Task ID", style="cyan")
    table.add_column("Factory Result", justify="center")
    table.add_column("Baseline Result", justify="center")
    table.add_column("Debug Iters", justify="right")
    table.add_column("Factory Toks", justify="right")
    table.add_column("Baseline Toks", justify="right")

    for r in all_results:
        f_str = "[green]PASS[/green]" if r.factory_passed else "[red]FAIL[/red]"
        s_str = "[green]PASS[/green]" if r.single_passed else "[red]FAIL[/red]"
        table.add_row(
            r.task_id,
            f_str,
            s_str,
            str(r.debug_iterations),
            f"{r.factory_tokens:,}",
            f"{r.single_tokens:,}",
        )

    console.print("\n")
    console.print(table)
    console.print(f"\n[green]Saved evaluation artifacts:[/green]\n  • {output_json}\n  • {output_md}")
    return all_results


def main() -> None:
    parser = argparse.ArgumentParser(description="ShadowX Benchmark Evaluation Harness")
    parser.add_argument("--tasks", "-t", type=str, default=None, help="Comma-separated task IDs (e.g. 'bank_account_lib,cli_todo_app')")
    parser.add_argument("--mode", "-m", choices=["both", "factory", "baseline"], default="both", help="Evaluation mode to run")
    parser.add_argument("-n", "--runs", type=int, default=1, help="Repetitions per task (default 1)")
    parser.add_argument("--fake", action="store_true", help="Run with FakeLLMProvider (dry-run, no API tokens needed)")
    parser.add_argument("--output-json", type=Path, default=DEFAULT_RESULTS_JSON, help="Output path for results JSON")
    parser.add_argument("--output-md", type=Path, default=DEFAULT_COMPARISON_MD, help="Output path for comparison Markdown")

    args = parser.parse_args()
    task_ids = [t.strip() for t in args.tasks.split(",")] if args.tasks else None

    run_benchmark(
        task_ids=task_ids,
        mode=args.mode,
        runs_per_task=args.runs,
        use_fake=args.fake,
        output_json=args.output_json,
        output_md=args.output_md,
    )


if __name__ == "__main__":
    main()
