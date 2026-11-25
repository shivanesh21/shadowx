"""
test_full_lifecycle.py — End-to-end integration tests for the full 6-stage factory lifecycle,
approval gates, budgets, cancellation, and resume.
"""

import json
import time
import subprocess
from pathlib import Path
import pytest

from pipeline.orchestrator import (
    Stage,
    RunContext,
    Orchestrator,
    BudgetConfig,
    resume_run,
)
from shadow.core.llm import FakeLLMProvider, LLMResponse, FunctionCallData, TokenUsage
from shadow.core.events import ApprovalRequested, ApprovalResolved


def test_full_six_stage_lifecycle_e2e(tmp_path: Path):
    """
    Test full execution across all 6 stages:
    ANALYSIS -> DESIGN -> CODING -> TESTING -> REVIEW -> DOCS -> DONE.
    """
    req_json = json.dumps({
        "project_name": "URL Shortener",
        "summary": "Fast URL shortening service",
        "user_stories": [{"id": "US-1", "role": "User", "action": "shorten URL", "benefit": "share easily"}],
        "functional_requirements": ["shorten(url) -> code", "expand(code) -> url"],
        "non_functional_requirements": ["In-memory storage"],
        "acceptance_criteria": {
            "AC-1": "shorten('https://example.com') returns 6-char code",
            "AC-2": "expand(code) returns original url",
        },
        "assumptions": ["Valid URLs only"],
        "out_of_scope": ["Analytics"],
    })

    design_json = json.dumps({
        "project_name": "URL Shortener",
        "tech_stack": ["Python 3.10+"],
        "modules": [
            {
                "file_path": "src/shortener.py",
                "description": "Shortener service",
                "interfaces": ["def shorten(url: str) -> str", "def expand(code: str) -> str"],
            }
        ],
        "data_models": [],
        "mermaid_diagram": "flowchart TD\n  Client --> Shortener[src/shortener.py]",
        "ac_mapping": {
            "AC-1": ["src/shortener.py"],
            "AC-2": ["src/shortener.py"],
        },
    })

    code_content = """\
_db = {}
def shorten(url: str) -> str:
    code = f"u{len(_db) + 1:05d}"
    _db[code] = url
    return code

def expand(code: str) -> str:
    return _db.get(code, "")
"""

    test_content = """\
from src.shortener import shorten, expand

def test_ac1_shorten():
    code = shorten("https://example.com")
    assert len(code) == 6

def test_ac2_expand():
    code = shorten("https://google.com")
    assert expand(code) == "https://google.com"
"""

    test_report_json = json.dumps({
        "passed": 2,
        "failed": 0,
        "errors": 0,
        "ac_coverage": {
            "AC-1": "test_ac1_shorten",
            "AC-2": "test_ac2_expand",
        },
        "failures": {},
    })

    review_content = """\
# Code Review: URL Shortener
## 1. Executive Summary & Verdict
STATUS: APPROVED

## 2. Requirements Traceability Matrix
| Requirement ID | Description | Implementing Module | Test Function | Status |
|---|---|---|---|---|
| AC-1 | Shorten url | src/shortener.py | test_ac1_shorten | PASS |
| AC-2 | Expand code | src/shortener.py | test_ac2_expand | PASS |
"""

    readme_content = """\
# URL Shortener
A fast in-memory URL shortener.
## Quickstart
```python
from src.shortener import shorten, expand
code = shorten("https://example.com")
print(expand(code))
```
"""

    provider = FakeLLMProvider()

    # 1. Analyst
    provider.queue_response(
        LLMResponse(
            function_calls=[
                FunctionCallData(name="write_file", args={"path": "docs/requirements.md", "content": "# Requirements"}),
                FunctionCallData(name="write_file", args={"path": "docs/requirements.json", "content": req_json}),
                FunctionCallData(name="finish", args={"summary": "Analyst done"}),
            ]
        )
    )

    # 2. Architect
    provider.queue_response(
        LLMResponse(
            function_calls=[
                FunctionCallData(name="write_file", args={"path": "docs/design.md", "content": "# Design\nflowchart TD\n A-->B"}),
                FunctionCallData(name="write_file", args={"path": "docs/design.json", "content": design_json}),
                FunctionCallData(name="finish", args={"summary": "Architect done"}),
            ]
        )
    )

    # 3. Developer
    provider.queue_response(
        LLMResponse(
            function_calls=[
                FunctionCallData(name="write_file", args={"path": "src/shortener.py", "content": code_content}),
                FunctionCallData(name="run_command", args={"command": "python -c \"import src.shortener as s; print('OK')\""}),
                FunctionCallData(name="finish", args={"summary": "Developer done"}),
            ]
        )
    )

    # 4. Tester
    provider.queue_response(
        LLMResponse(
            function_calls=[
                FunctionCallData(name="write_file", args={"path": "tests/test_shortener.py", "content": test_content}),
                FunctionCallData(name="run_tests", args={"test_path": "tests"}),
                FunctionCallData(name="write_file", args={"path": "test_report.json", "content": test_report_json}),
                FunctionCallData(name="finish", args={"summary": "All tests passed"}),
            ]
        )
    )

    # 5. Reviewer
    provider.queue_response(
        LLMResponse(
            function_calls=[
                FunctionCallData(name="write_file", args={"path": "docs/review.md", "content": review_content}),
                FunctionCallData(name="finish", args={"summary": "Review approved"}),
            ]
        )
    )

    # 6. Documenter
    provider.queue_response(
        LLMResponse(
            function_calls=[
                FunctionCallData(name="write_file", args={"path": "README.md", "content": readme_content}),
                FunctionCallData(name="write_file", args={"path": "docs/changelog.md", "content": "# Changelog\n- Initial release"}),
                FunctionCallData(name="run_command", args={"command": "python -c \"from src.shortener import shorten; print(shorten('http://a.com'))\""}),
                FunctionCallData(name="finish", args={"summary": "Documentation complete"}),
            ]
        )
    )

    orchestrator = Orchestrator(
        idea="Build a URL Shortener",
        run_id="run_e2e_all_six_stages",
        llm=provider,
        base_dir=tmp_path,
        enable_cli_renderer=False,
    )

    success = orchestrator.execute_pipeline(target_stage=Stage.DONE)
    assert success is True
    assert orchestrator.context.get_stage() == Stage.DONE

    # Verify all artifacts on disk
    ws = orchestrator.context.workspace_dir
    assert (ws / "docs" / "requirements.md").exists()
    assert (ws / "docs" / "requirements.json").exists()
    assert (ws / "docs" / "design.md").exists()
    assert (ws / "docs" / "design.json").exists()
    assert (ws / "src" / "shortener.py").exists()
    assert (ws / "tests" / "test_shortener.py").exists()
    assert (ws / "test_report.json").exists()
    assert (ws / "docs" / "review.md").exists()
    assert (ws / "README.md").exists()
    assert (ws / "docs" / "changelog.md").exists()

    # Verify Git checkpoints for all stages
    git_res = subprocess.run(
        ["git", "log", "--oneline"],
        cwd=str(ws),
        capture_output=True,
        text=True,
        check=True,
    )
    log_text = git_res.stdout
    assert "checkpoint(analysis)" in log_text
    assert "checkpoint(design)" in log_text
    assert "checkpoint(coding)" in log_text
    assert "checkpoint(testing)" in log_text
    assert "checkpoint(review)" in log_text
    assert "checkpoint(docs)" in log_text


def test_approval_gates_rejection_and_approval(tmp_path: Path):
    """
    Test approval gate rejecting requirements with feedback, agent revising, and then approving.
    """
    req_json_1 = json.dumps({
        "project_name": "App",
        "summary": "Initial draft",
        "user_stories": [{"id": "US-1", "role": "User", "action": "use", "benefit": "benefit"}],
        "functional_requirements": ["f1"],
        "acceptance_criteria": {"AC-1": "test 1"},
    })

    req_json_2 = json.dumps({
        "project_name": "App",
        "summary": "Revised draft with expiration",
        "user_stories": [{"id": "US-1", "role": "User", "action": "use", "benefit": "benefit"}],
        "functional_requirements": ["f1", "f2 expiration"],
        "acceptance_criteria": {"AC-1": "test 1", "AC-2": "expiration works"},
    })

    provider = FakeLLMProvider()
    # Attempt 1: writes initial req
    provider.queue_response(
        LLMResponse(function_calls=[
            FunctionCallData(name="write_file", args={"path": "docs/requirements.md", "content": "# Requirements 1"}),
            FunctionCallData(name="write_file", args={"path": "docs/requirements.json", "content": req_json_1}),
            FunctionCallData(name="finish", args={"summary": "Draft 1"}),
        ])
    )
    # Attempt 2 (after human rejection): writes revised req
    provider.queue_response(
        LLMResponse(function_calls=[
            FunctionCallData(name="write_file", args={"path": "docs/requirements.md", "content": "# Requirements 2 with expiration"}),
            FunctionCallData(name="write_file", args={"path": "docs/requirements.json", "content": req_json_2}),
            FunctionCallData(name="finish", args={"summary": "Draft 2 with expiration"}),
        ])
    )

    gate_calls = []
    def custom_gate_handler(stage: str, artifact_path: str, preview: str) -> tuple[str, str]:
        gate_calls.append(stage)
        if len(gate_calls) == 1:
            return "rejected", "Please add expiration requirement AC-2."
        return "approved", ""

    orchestrator = Orchestrator(
        idea="Build an App",
        run_id="run_gate_test",
        llm=provider,
        base_dir=tmp_path,
        enable_cli_renderer=False,
        approval_gates=True,
        approval_handler=custom_gate_handler,
    )

    success = orchestrator.run_stage_analyst()
    assert success is True
    assert len(gate_calls) == 2
    # Verify final requirements content has AC-2
    final_req = (orchestrator.context.workspace_dir / "docs" / "requirements.md").read_text()
    assert "Requirements 2 with expiration" in final_req


def test_budget_token_exceeded(tmp_path: Path):
    """Verify that exceeding total token budget halts with FAILED."""
    provider = FakeLLMProvider()
    # Queue response that claims 100 tokens
    provider.queue_response(
        LLMResponse(
            text="Thinking...",
            token_usage=TokenUsage(prompt_tokens=50, completion_tokens=50, total_tokens=100),
            function_calls=[
                FunctionCallData(name="write_file", args={"path": "docs/requirements.md", "content": "# R"}),
                FunctionCallData(name="finish", args={"summary": "Done"}),
            ]
        )
    )

    budget = BudgetConfig(max_run_tokens=50)  # Cap at 50 tokens

    orchestrator = Orchestrator(
        idea="Build an App",
        run_id="run_budget_tokens_test",
        llm=provider,
        base_dir=tmp_path,
        enable_cli_renderer=False,
        budget=budget,
    )

    success = orchestrator.execute_pipeline()
    assert success is False
    assert orchestrator.context.get_stage() == Stage.FAILED


def test_budget_wall_time_exceeded(tmp_path: Path):
    """Verify that exceeding wall-clock budget halts execution."""
    budget = BudgetConfig(max_wall_time_s=0.001)  # 1 millisecond timeout

    orchestrator = Orchestrator(
        idea="Build an App",
        run_id="run_budget_time_test",
        llm=FakeLLMProvider(),
        base_dir=tmp_path,
        enable_cli_renderer=False,
        budget=budget,
    )
    time.sleep(0.01)

    success = orchestrator.execute_pipeline()
    assert success is False
    assert orchestrator.context.get_stage() == Stage.FAILED


def test_resume_from_saved_state(tmp_path: Path):
    """
    Verify that resume picks up from the first uncompleted stage.
    """
    run_id = "run_to_resume"
    ctx = RunContext(run_id=run_id, base_dir=tmp_path)
    ctx.set_idea("Build a Library")

    # Simulate completed ANALYSIS and DESIGN stages
    doc_dir = ctx.workspace_dir / "docs"
    doc_dir.mkdir(parents=True)
    (doc_dir / "requirements.md").write_text("# Req")
    (doc_dir / "requirements.json").write_text("{}")
    (doc_dir / "design.md").write_text("# Design")
    (doc_dir / "design.json").write_text("{}")

    ctx.checkpoint_git(Stage.ANALYSIS)
    ctx.checkpoint_git(Stage.DESIGN)

    # Provider only needs responses for CODING onward
    provider = FakeLLMProvider()
    provider.queue_response(
        LLMResponse(
            function_calls=[
                FunctionCallData(name="write_file", args={"path": "src/lib.py", "content": "x = 1"}),
                FunctionCallData(name="finish", args={"summary": "Code written"}),
            ]
        )
    )

    # Resume targeting Stage.CODING
    orchestrator = Orchestrator(
        idea="Build a Library",
        run_id=run_id,
        llm=provider,
        base_dir=tmp_path,
        enable_cli_renderer=False,
    )

    success = orchestrator.execute_pipeline(target_stage=Stage.CODING, start_from_stage=Stage.CODING)
    assert success is True
    assert (ctx.workspace_dir / "src" / "lib.py").exists()
