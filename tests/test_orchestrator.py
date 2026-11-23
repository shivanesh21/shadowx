"""
test_orchestrator.py — Unit tests for state machine, run context, and Analyst stage.
"""

import json
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
    # Write a dummy file in workspace
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
    # Step 1: write requirements.md
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
    # Step 2: write requirements.json
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
    # Step 3: finish tool
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

    # Verify workspace files
    assert (orchestrator.context.workspace_dir / "docs" / "requirements.md").exists()
    assert (orchestrator.context.workspace_dir / "docs" / "requirements.json").exists()

    # Verify artifact store
    assert (orchestrator.context.artifacts_dir / "requirements.md").exists()
    assert (orchestrator.context.artifacts_dir / "requirements.json").exists()

    # Verify events
    assert orchestrator.context.events_file.exists()


def test_orchestrator_analyst_retry_on_invalid_json(tmp_path: Path):
    """Verify that an invalid schema triggers a re-prompt and succeeds on retry."""
    invalid_json = json.dumps({"bad": "structure"})
    valid_json = json.dumps({
        "project_name": "App",
        "summary": "Summary",
        "user_stories": [{"id": "US-1", "role": "Dev", "action": "run", "benefit": "ok"}],
        "functional_requirements": ["F1"],
        "acceptance_criteria": {"AC-1": "Condition 1"},
    })

    provider = FakeLLMProvider()
    # Attempt 1: writes md and invalid json, then finishes
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

    # Attempt 2 (Retry after error message from orchestrator): fixes json and finishes
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
