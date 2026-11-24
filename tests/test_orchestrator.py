"""
test_orchestrator.py — Unit tests for state machine, run context, and multi-agent pipeline.
"""

import json
import subprocess
from pathlib import Path
import pytest

from pipeline.orchestrator import (
    Stage,
    RunContext,
    Orchestrator,
)
from shadow.core.llm import FakeLLMProvider, LLMResponse, FunctionCallData


def test_run_context_initialization(tmp_path: Path):
    ctx = RunContext(run_id="test_run_1", base_dir=tmp_path)
    assert ctx.workspace_dir.exists()
    assert ctx.artifacts_dir.exists()
    assert ctx.state_file.exists()
    assert (ctx.workspace_dir / ".git").exists()

    state = ctx._read_state()
    assert state["run_id"] == "test_run_1"
    assert state["current_stage"] == Stage.IDLE.value


def test_run_context_stage_updates(tmp_path: Path):
    ctx = RunContext(run_id="test_run_2", base_dir=tmp_path)
    ctx.update_stage(Stage.ANALYSIS, {"detail": "starting analysis"})
    assert ctx.get_stage() == Stage.ANALYSIS

    ctx.update_stage(Stage.DONE)
    assert ctx.get_stage() == Stage.DONE

    state = ctx._read_state()
    assert len(state["history"]) == 2
    assert state["status"] == "done"


def test_run_context_artifact_recording(tmp_path: Path):
    ctx = RunContext(run_id="test_run_3", base_dir=tmp_path)
    doc_dir = ctx.workspace_dir / "docs"
    doc_dir.mkdir(parents=True)
    req_file = doc_dir / "requirements.md"
    req_file.write_text("# Requirements\n- AC-1: Pass")

    ctx.record_artifact("requirements", "docs/requirements.md")
    assert (ctx.artifacts_dir / "requirements.md").exists()

    state = ctx._read_state()
    assert state["artifacts"]["requirements"] == "docs/requirements.md"


def test_orchestrator_analyst_stage_happy_path(tmp_path: Path):
    valid_json = json.dumps({
        "project_name": "Markdown Parser",
        "summary": "Parses markdown into HTML AST",
        "user_stories": [{"id": "US-1", "role": "Dev", "action": "parse", "benefit": "render"}],
        "functional_requirements": ["Parse headers and lists"],
        "non_functional_requirements": ["Fast"],
        "acceptance_criteria": {"AC-1": "Header # converts to <h1>"},
        "assumptions": ["UTF-8 input"],
        "out_of_scope": ["Markdown tables"],
    })

    provider = FakeLLMProvider()
    provider.queue_response(
        LLMResponse(
            text="Writing requirements.md",
            function_calls=[
                FunctionCallData(
                    name="write_file",
                    args={"path": "docs/requirements.md", "content": "# Markdown Parser\n## AC-1: Header"},
                )
            ],
        )
    )
    provider.queue_response(
        LLMResponse(
            text="Writing requirements.json",
            function_calls=[
                FunctionCallData(
                    name="write_file",
                    args={"path": "docs/requirements.json", "content": valid_json},
                )
            ],
        )
    )
    provider.queue_response(
        LLMResponse(
            text="Requirements complete.",
            function_calls=[
                FunctionCallData(
                    name="finish",
                    args={
                        "summary": "Completed requirements definition",
                        "artifacts": {
                            "requirements_md": "docs/requirements.md",
                            "requirements_json": "docs/requirements.json",
                        },
                    },
                )
            ],
        )
    )

    orchestrator = Orchestrator(
        idea="Build a Markdown Parser",
        run_id="run_analyst_test",
        llm=provider,
        base_dir=tmp_path,
        enable_cli_renderer=False,
    )

    success = orchestrator.execute_pipeline(target_stage=Stage.ANALYSIS)
    assert success is True
    assert orchestrator.context.get_stage() == Stage.DONE
    assert (orchestrator.context.workspace_dir / "docs" / "requirements.md").exists()
    assert (orchestrator.context.workspace_dir / "docs" / "requirements.json").exists()


def test_orchestrator_analyst_retry_on_invalid_json(tmp_path: Path):
    invalid_json = json.dumps({"bad": "structure"})
    valid_json = json.dumps({
        "project_name": "App",
        "summary": "Summary",
        "user_stories": [{"id": "US-1", "role": "Dev", "action": "run", "benefit": "ok"}],
        "functional_requirements": ["F1"],
        "acceptance_criteria": {"AC-1": "Condition 1"},
    })

    provider = FakeLLMProvider()
    provider.queue_response(
        LLMResponse(
            function_calls=[
                FunctionCallData(
                    name="write_file",
                    args={"path": "docs/requirements.md", "content": "# Requirements"},
                )
            ]
        )
    )
    provider.queue_response(
        LLMResponse(
            function_calls=[
                FunctionCallData(
                    name="write_file",
                    args={"path": "docs/requirements.json", "content": invalid_json},
                )
            ]
        )
    )
    provider.queue_response(
        LLMResponse(
            function_calls=[
                FunctionCallData(
                    name="finish",
                    args={"summary": "Done"},
                )
            ]
        )
    )

    provider.queue_response(
        LLMResponse(
            text="Fixing requirements.json",
            function_calls=[
                FunctionCallData(
                    name="write_file",
                    args={"path": "docs/requirements.json", "content": valid_json},
                )
            ],
        )
    )
    provider.queue_response(
        LLMResponse(
            function_calls=[
                FunctionCallData(
                    name="finish",
                    args={"summary": "Fixed"},
                )
            ]
        )
    )

    orchestrator = Orchestrator(
        idea="Build a Test App",
        run_id="run_retry_test",
        llm=provider,
        base_dir=tmp_path,
        enable_cli_renderer=False,
    )

    success = orchestrator.execute_pipeline(target_stage=Stage.ANALYSIS)
    assert success is True
    assert (orchestrator.context.workspace_dir / "docs" / "requirements.json").exists()


def test_orchestrator_end_to_end_idea_to_code(tmp_path: Path):
    """
    Test full progression: Idea -> Requirements -> Design (Mermaid) -> Runnable Code.
    Verifies git checkpoints after every stage.
    """
    req_json = json.dumps({
        "project_name": "Math Library",
        "summary": "Basic math operations library",
        "user_stories": [{"id": "US-1", "role": "User", "action": "add numbers", "benefit": "get sum"}],
        "functional_requirements": ["Implement add(a, b)"],
        "non_functional_requirements": ["Pure Python"],
        "acceptance_criteria": {"AC-1": "add(2, 3) returns 5"},
        "assumptions": ["Inputs are numeric"],
        "out_of_scope": ["Complex numbers"],
    })

    design_json = json.dumps({
        "project_name": "Math Library",
        "tech_stack": ["Python 3.10+"],
        "modules": [
            {
                "file_path": "src/math_ops.py",
                "description": "Math arithmetic operations",
                "interfaces": ["def add(a: float, b: float) -> float"],
            }
        ],
        "data_models": [],
        "mermaid_diagram": "flowchart TD\n  Client --> MathOps[src/math_ops.py]",
        "ac_mapping": {"AC-1": ["src/math_ops.py"]},
    })

    code_content = "def add(a: float, b: float) -> float:\n    return a + b\n"

    provider = FakeLLMProvider()

    # 1. Analyst responses
    provider.queue_response(
        LLMResponse(
            function_calls=[
                FunctionCallData(name="write_file", args={"path": "docs/requirements.md", "content": "# Math Library\nAC-1"}),
                FunctionCallData(name="write_file", args={"path": "docs/requirements.json", "content": req_json}),
                FunctionCallData(name="finish", args={"summary": "Analyst done", "artifacts": {"req": "docs/requirements.json"}}),
            ]
        )
    )

    # 2. Architect responses
    provider.queue_response(
        LLMResponse(
            function_calls=[
                FunctionCallData(name="write_file", args={"path": "docs/design.md", "content": "# Design\n```mermaid\nflowchart TD\n  A-->B\n```"}),
                FunctionCallData(name="write_file", args={"path": "docs/design.json", "content": design_json}),
                FunctionCallData(name="finish", args={"summary": "Architect done", "artifacts": {"design": "docs/design.json"}}),
            ]
        )
    )

    # 3. Developer responses
    provider.queue_response(
        LLMResponse(
            function_calls=[
                FunctionCallData(name="write_file", args={"path": "src/math_ops.py", "content": code_content}),
                FunctionCallData(name="run_command", args={"command": "python -c \"import src.math_ops as m; assert m.add(2, 3) == 5; print('OK')\""}),
                FunctionCallData(name="finish", args={"summary": "Developer done", "artifacts": {"code": "src/math_ops.py"}}),
            ]
        )
    )

    orchestrator = Orchestrator(
        idea="Build a Math Library",
        run_id="run_e2e_test",
        llm=provider,
        base_dir=tmp_path,
        enable_cli_renderer=False,
    )

    success = orchestrator.execute_pipeline(target_stage=Stage.CODING)
    assert success is True
    assert orchestrator.context.get_stage() == Stage.DONE

    # Verify deliverables
    ws = orchestrator.context.workspace_dir
    assert (ws / "docs" / "requirements.md").exists()
    assert (ws / "docs" / "requirements.json").exists()
    assert (ws / "docs" / "design.md").exists()
    assert (ws / "docs" / "design.json").exists()
    assert (ws / "src" / "math_ops.py").exists()

    # Verify git checkpoints in git log
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

    # Verify state.json
    state = orchestrator.context._read_state()
    assert "ANALYSIS" in state.get("checkpoints", {})
    assert "DESIGN" in state.get("checkpoints", {})
    assert "CODING" in state.get("checkpoints", {})
    assert state.get("status") == "done"


def test_orchestrator_design_retry_on_invalid_mermaid(tmp_path: Path):
    """Verify that an invalid Mermaid diagram triggers a re-prompt and succeeds on retry."""
    req_json = json.dumps({
        "project_name": "App",
        "summary": "Summary",
        "user_stories": [{"id": "US-1", "role": "Dev", "action": "run", "benefit": "ok"}],
        "functional_requirements": ["F1"],
        "acceptance_criteria": {"AC-1": "Condition 1"},
    })

    bad_design_json = json.dumps({
        "project_name": "App",
        "tech_stack": ["Python"],
        "modules": [{"file_path": "src/app.py", "description": "main", "interfaces": []}],
        "mermaid_diagram": "invalid diagram header",
        "ac_mapping": {"AC-1": ["src/app.py"]},
    })

    good_design_json = json.dumps({
        "project_name": "App",
        "tech_stack": ["Python"],
        "modules": [{"file_path": "src/app.py", "description": "main", "interfaces": []}],
        "mermaid_diagram": "flowchart TD\n  Start --> Stop",
        "ac_mapping": {"AC-1": ["src/app.py"]},
    })

    provider = FakeLLMProvider()

    # Analyst
    provider.queue_response(
        LLMResponse(
            function_calls=[
                FunctionCallData(name="write_file", args={"path": "docs/requirements.md", "content": "# Req"}),
                FunctionCallData(name="write_file", args={"path": "docs/requirements.json", "content": req_json}),
                FunctionCallData(name="finish", args={"summary": "Analyst done"}),
            ]
        )
    )

    # Architect attempt 1: bad mermaid
    provider.queue_response(
        LLMResponse(
            function_calls=[
                FunctionCallData(name="write_file", args={"path": "docs/design.md", "content": "# Design"}),
                FunctionCallData(name="write_file", args={"path": "docs/design.json", "content": bad_design_json}),
                FunctionCallData(name="finish", args={"summary": "Architect done"}),
            ]
        )
    )

    # Architect attempt 2: corrected good mermaid
    provider.queue_response(
        LLMResponse(
            function_calls=[
                FunctionCallData(name="write_file", args={"path": "docs/design.json", "content": good_design_json}),
                FunctionCallData(name="finish", args={"summary": "Architect fixed"}),
            ]
        )
    )

    orchestrator = Orchestrator(
        idea="Build a Test App",
        run_id="run_design_retry_test",
        llm=provider,
        base_dir=tmp_path,
        enable_cli_renderer=False,
    )

    success = orchestrator.execute_pipeline(target_stage=Stage.DESIGN)
    assert success is True
    assert (orchestrator.context.workspace_dir / "docs" / "design.json").exists()
