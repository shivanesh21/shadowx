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


def test_tester_debugger_loop_seeded_bug_repaired(tmp_path: Path):
    """
    Verify that a deliberately seeded bug in src/ is detected by the Tester,
    repaired by the Debugger, and the loop successfully halts at pass.
    """
    req_json = json.dumps({
        "project_name": "Calculator",
        "summary": "Calculator module",
        "user_stories": [{"id": "US-1", "role": "User", "action": "add", "benefit": "sum"}],
        "functional_requirements": ["add(a, b)"],
        "non_functional_requirements": [],
        "acceptance_criteria": {"AC-1": "add(2, 3) == 5"},
        "assumptions": [],
        "out_of_scope": [],
    })

    design_json = json.dumps({
        "project_name": "Calculator",
        "tech_stack": ["Python"],
        "modules": [{"file_path": "src/calc.py", "description": "calc", "interfaces": ["def add(a, b)"]}],
        "data_models": [],
        "mermaid_diagram": "flowchart TD\n  A --> B",
        "ac_mapping": {"AC-1": ["src/calc.py"]},
    })

    # Deliberately seeded bug: return a - b instead of a + b
    buggy_code = "def add(a: int, b: int) -> int:\n    return a - b\n"
    test_code = "from src.calc import add\n\ndef test_ac1_add():\n    assert add(2, 3) == 5\n"

    failing_report = json.dumps({
        "passed": 0,
        "failed": 1,
        "errors": 0,
        "ac_coverage": {"AC-1": "test_ac1_add"},
        "failures": {"test_ac1_add": "assert -1 == 5"},
    })

    passing_report = json.dumps({
        "passed": 1,
        "failed": 0,
        "errors": 0,
        "ac_coverage": {"AC-1": "test_ac1_add"},
        "failures": {},
    })

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
                FunctionCallData(name="write_file", args={"path": "docs/design.md", "content": "# Design"}),
                FunctionCallData(name="write_file", args={"path": "docs/design.json", "content": design_json}),
                FunctionCallData(name="finish", args={"summary": "Architect done"}),
            ]
        )
    )

    # 3. Developer (seeds the bug)
    provider.queue_response(
        LLMResponse(
            function_calls=[
                FunctionCallData(name="write_file", args={"path": "src/calc.py", "content": buggy_code}),
                FunctionCallData(name="run_command", args={"command": "python -c \"import src.calc; print('imported')\""}),
                FunctionCallData(name="finish", args={"summary": "Developer done"}),
            ]
        )
    )

    # 4. Tester - Iteration 1 (writes test, runs, sees failure)
    provider.queue_response(
        LLMResponse(
            function_calls=[
                FunctionCallData(name="write_file", args={"path": "tests/test_calc.py", "content": test_code}),
                FunctionCallData(name="run_tests", args={"test_path": "tests"}),
                FunctionCallData(name="write_file", args={"path": "test_report.json", "content": failing_report}),
                FunctionCallData(name="finish", args={"summary": "Tests written, 1 failure"}),
            ]
        )
    )

    # 5. Debugger - Iteration 1 (inspects failure, fixes bug via edit_file, writes debug_log.md)
    provider.queue_response(
        LLMResponse(
            function_calls=[
                FunctionCallData(name="edit_file", args={"path": "src/calc.py", "old_text": "return a - b", "new_text": "return a + b"}),
                FunctionCallData(name="write_file", args={"path": "debug_log.md", "content": "# Fix: change minus to plus"}),
                FunctionCallData(name="run_tests", args={"test_path": "tests"}),
                FunctionCallData(name="finish", args={"summary": "Bug fixed"}),
            ]
        )
    )

    # 6. Tester - Iteration 2 (re-runs tests, writes passing report)
    provider.queue_response(
        LLMResponse(
            function_calls=[
                FunctionCallData(name="run_tests", args={"test_path": "tests"}),
                FunctionCallData(name="write_file", args={"path": "test_report.json", "content": passing_report}),
                FunctionCallData(name="finish", args={"summary": "All tests passed"}),
            ]
        )
    )

    orchestrator = Orchestrator(
        idea="Build a Calculator",
        run_id="run_seeded_bug_test",
        llm=provider,
        base_dir=tmp_path,
        enable_cli_renderer=False,
    )

    success = orchestrator.execute_pipeline(target_stage=Stage.TESTING)
    assert success is True
    assert orchestrator.context.get_stage() == Stage.DONE

    # Verify bug was repaired
    fixed_code = (orchestrator.context.workspace_dir / "src" / "calc.py").read_text()
    assert "return a + b" in fixed_code
    assert (orchestrator.context.workspace_dir / "debug_log.md").exists()

    # Verify git checkpoints captured both debugging and final testing
    git_res = subprocess.run(
        ["git", "log", "--oneline"],
        cwd=str(orchestrator.context.workspace_dir),
        capture_output=True,
        text=True,
        check=True,
    )
    log_text = git_res.stdout
    assert "checkpoint(debugging)" in log_text
    assert "checkpoint(testing)" in log_text


def test_tester_debugger_loop_limit_reached(tmp_path: Path):
    """Verify that an unresolvable test failure halts with FAILED when iteration limit is reached."""
    req_json = json.dumps({
        "project_name": "App",
        "summary": "App",
        "user_stories": [{"id": "US-1", "role": "User", "action": "run", "benefit": "ok"}],
        "functional_requirements": ["f1"],
        "acceptance_criteria": {"AC-1": "test passes"},
    })
    design_json = json.dumps({
        "project_name": "App",
        "tech_stack": ["Python"],
        "modules": [{"file_path": "src/app.py", "description": "app", "interfaces": []}],
        "mermaid_diagram": "flowchart TD\n  A-->B",
        "ac_mapping": {"AC-1": ["src/app.py"]},
    })

    # Code that will always fail
    bad_code = "def check(): return False\n"
    test_code = "from src.app import check\ndef test_ac1_check(): assert check() is True\n"

    failing_report = lambda msg: json.dumps({
        "passed": 0,
        "failed": 1,
        "errors": 0,
        "ac_coverage": {"AC-1": "test_ac1_check"},
        "failures": {"test_ac1_check": msg},
    })

    provider = FakeLLMProvider()

    # Analyst
    provider.queue_response(
        LLMResponse(function_calls=[
            FunctionCallData(name="write_file", args={"path": "docs/requirements.md", "content": "# R"}),
            FunctionCallData(name="write_file", args={"path": "docs/requirements.json", "content": req_json}),
            FunctionCallData(name="finish", args={"summary": "A"}),
        ])
    )
    # Architect
    provider.queue_response(
        LLMResponse(function_calls=[
            FunctionCallData(name="write_file", args={"path": "docs/design.md", "content": "# D"}),
            FunctionCallData(name="write_file", args={"path": "docs/design.json", "content": design_json}),
            FunctionCallData(name="finish", args={"summary": "D"}),
        ])
    )
    # Developer
    provider.queue_response(
        LLMResponse(function_calls=[
            FunctionCallData(name="write_file", args={"path": "src/app.py", "content": bad_code}),
            FunctionCallData(name="finish", args={"summary": "Dev"}),
        ])
    )

    # Queue repeating failures for Tester and no-op Debugger responses
    for i in range(5):
        # Tester
        provider.queue_response(
            LLMResponse(function_calls=[
                FunctionCallData(name="write_file", args={"path": "tests/test_app.py", "content": test_code}),
                FunctionCallData(name="run_tests", args={"test_path": "tests"}),
                FunctionCallData(name="write_file", args={"path": "test_report.json", "content": failing_report(f"error_{i}")}),
                FunctionCallData(name="finish", args={"summary": "Failing"}),
            ])
        )
        # Debugger
        provider.queue_response(
            LLMResponse(function_calls=[
                FunctionCallData(name="finish", args={"summary": "Could not fix"}),
            ])
        )

    orchestrator = Orchestrator(
        idea="Build an App",
        run_id="run_limit_test",
        llm=provider,
        base_dir=tmp_path,
        enable_cli_renderer=False,
    )

    success = orchestrator.execute_pipeline()
    assert success is False
    assert orchestrator.context.get_stage() == Stage.FAILED


def test_agent_repetitive_tool_call_guard():
    """Verify that calling the same tool 3 times consecutively with identical arguments triggers LoopDetected."""
    from shadow.core.agent import Agent, AgentSpec
    from shadow.core.event_bus import EventBus

    bus = EventBus()
    loops_detected = []
    bus.subscribe(lambda e: loops_detected.append(e), "loop_detected")

    tool_called_count = 0
    def mock_tool(arg: str) -> str:
        nonlocal tool_called_count
        tool_called_count += 1
        return f"result_{arg}"

    tools = {"test_tool": mock_tool}
    decls = [{
        "name": "test_tool",
        "description": "mock tool",
        "parameters": {"type": "object", "properties": {"arg": {"type": "string"}}},
    }]

    provider = FakeLLMProvider()
    # 3 consecutive identical tool calls
    for _ in range(3):
        provider.queue_response(
            LLMResponse(
                function_calls=[FunctionCallData(name="test_tool", args={"arg": "same_value"})]
            )
        )
    provider.queue_response(LLMResponse(text="Done"))

    spec = AgentSpec(name="LoopTester", system_prompt="Test loop", allowed_tools=["test_tool"], max_steps=5)
    agent = Agent(spec=spec, llm=provider, tool_registry=tools, tool_declarations=decls, event_bus=bus)

    result = agent.execute(task="Test identical tool loop")
    assert len(loops_detected) >= 1
    assert "repeated tool 'test_tool' 3 times" in loops_detected[0].reason
    # 3rd call was intercepted and blocked before executing the tool function
    assert tool_called_count == 2

