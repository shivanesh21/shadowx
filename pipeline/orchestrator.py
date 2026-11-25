"""
orchestrator.py — Deterministic State Machine Orchestrator for ShadowX Factory.

Coordinates the complete 6-stage multi-agent software development lifecycle:
ANALYSIS -> DESIGN -> CODING -> TESTING (↔ DEBUGGING) -> REVIEW -> DOCS -> DONE

Features:
- Strict Pydantic artifact validation with re-prompt retry limit
- Human-in-the-loop (HITL) approval gates after requirements and design
- Per-stage and per-run token and wall-clock time budget enforcement
- Graceful cancellation and stage-level resumption from checkpoints
- Automated Git snapshot checkpoints after every stage
"""

from __future__ import annotations
import os
import sys
import json
import time
import shutil
import hashlib
import argparse
from enum import Enum
from pathlib import Path
from dataclasses import dataclass, field
from typing import Optional, Union, Any, Callable

from rich.console import Console
from rich.panel import Panel
from rich.prompt import Prompt

from shadow.core.agent import Agent, AgentSpec, AgentResult
from shadow.core.events import (
    RunStarted,
    StageStarted,
    StageFinished,
    RunFinished,
    ErrorEvent,
    LoopDetected,
    TestResultEvent,
    ApprovalRequested,
    ApprovalResolved,
)
from shadow.core.event_bus import EventBus
from shadow.core.llm import LLMProvider, GeminiProvider
from shadow.tools.registry import ToolRegistry
from shadow.tools.testing import run_tests
from shadow.agent import build_provider, attach_cli_renderer
from pipeline.schemas import validate_requirements, validate_design, validate_test_report
from pipeline.git_checkpoints import init_workspace_git, create_checkpoint

console = Console()


@dataclass
class BudgetConfig:
    """Configurable budget guardrails for a factory run."""
    max_run_tokens: int = 100000
    max_stage_tokens: int = 40000
    max_wall_time_s: float = 600.0
    max_steps_per_stage: int = 20


def compute_failure_signature(failures: dict[str, str]) -> str:
    """Compute a deterministic SHA256 hash of failed test names and error types."""
    if not failures:
        return ""
    sorted_items = sorted(failures.items())
    signature_tokens = []
    for test_name, trace in sorted_items:
        lines = [line.strip() for line in trace.strip().splitlines() if line.strip()]
        last_line = lines[-1] if lines else "failed"
        signature_tokens.append(f"{test_name}:{last_line}")
    combined = "||".join(signature_tokens)
    return hashlib.sha256(combined.encode("utf-8")).hexdigest()[:16]


class Stage(str, Enum):
    IDLE = "IDLE"
    ANALYSIS = "ANALYSIS"
    DESIGN = "DESIGN"
    CODING = "CODING"
    TESTING = "TESTING"
    DEBUGGING = "DEBUGGING"
    REVIEW = "REVIEW"
    DOCS = "DOCS"
    DONE = "DONE"
    FAILED = "FAILED"
    CANCELLED = "CANCELLED"


class RunContext:
    """Manages files, workspace, artifacts, and state.json for a single run."""

    def __init__(self, run_id: str, base_dir: Union[str, Path] = "runs") -> None:
        self.run_id = run_id
        self.run_dir = Path(base_dir).resolve() / run_id
        self.workspace_dir = self.run_dir / "workspace"
        self.artifacts_dir = self.run_dir / "artifacts"
        self.events_file = self.run_dir / "events.jsonl"
        self.state_file = self.run_dir / "state.json"

        # Initialize directory tree
        self.workspace_dir.mkdir(parents=True, exist_ok=True)
        self.artifacts_dir.mkdir(parents=True, exist_ok=True)
        init_workspace_git(self.workspace_dir)

        if not self.state_file.exists():
            self._write_state({
                "run_id": self.run_id,
                "current_stage": Stage.IDLE.value,
                "history": [],
                "created_at": time.time(),
                "updated_at": time.time(),
                "status": "pending",
                "tokens": 0,
                "artifacts": {},
                "checkpoints": {},
                "idea": "",
            })

    def _read_state(self) -> dict[str, Any]:
        try:
            return json.loads(self.state_file.read_text(encoding="utf-8"))
        except Exception:
            return {}

    def _write_state(self, state: dict[str, Any]) -> None:
        state["updated_at"] = time.time()
        self.state_file.write_text(json.dumps(state, indent=2), encoding="utf-8")

    def get_stage(self) -> Stage:
        state = self._read_state()
        return Stage(state.get("current_stage", Stage.IDLE.value))

    def update_stage(self, new_stage: Stage, details: Optional[dict[str, Any]] = None) -> None:
        state = self._read_state()
        prev = state.get("current_stage", Stage.IDLE.value)
        state["current_stage"] = new_stage.value
        state.setdefault("history", []).append({
            "from": prev,
            "to": new_stage.value,
            "timestamp": time.time(),
            "details": details or {},
        })
        if new_stage in (Stage.DONE, Stage.FAILED, Stage.CANCELLED):
            state["status"] = new_stage.value.lower()
        self._write_state(state)

    def record_artifact(self, name: str, relative_path: str) -> None:
        state = self._read_state()
        state.setdefault("artifacts", {})[name] = relative_path
        self._write_state(state)

        # Copy to artifacts directory
        src_path = self.workspace_dir / relative_path
        if src_path.exists():
            dest_path = self.artifacts_dir / Path(relative_path).name
            shutil.copy2(src_path, dest_path)

    def add_tokens(self, tokens: int) -> None:
        state = self._read_state()
        state["tokens"] = state.get("tokens", 0) + tokens
        self._write_state(state)

    def get_tokens(self) -> int:
        state = self._read_state()
        return state.get("tokens", 0)

    def set_idea(self, idea: str) -> None:
        state = self._read_state()
        state["idea"] = idea
        self._write_state(state)

    def get_idea(self) -> str:
        state = self._read_state()
        return state.get("idea", "")

    def get_checkpoints(self) -> dict[str, str]:
        state = self._read_state()
        return state.get("checkpoints", {})

    def checkpoint_git(self, stage: Stage) -> str:
        """Create a git snapshot for the current stage and record in state.json."""
        commit_hash = create_checkpoint(self.workspace_dir, stage.value)
        if commit_hash:
            state = self._read_state()
            state.setdefault("checkpoints", {})[stage.value] = commit_hash
            self._write_state(state)
        return commit_hash


class Orchestrator:
    """
    Executes the deterministic state machine for a factory run across all 6 stages.
    """

    def __init__(
        self,
        idea: str,
        run_id: Optional[str] = None,
        llm: Optional[LLMProvider] = None,
        base_dir: Union[str, Path] = "runs",
        enable_cli_renderer: bool = True,
        approval_gates: bool = False,
        budget: Optional[BudgetConfig] = None,
        approval_handler: Optional[Callable[[str, str, str], tuple[str, str]]] = None,
    ) -> None:
        self.idea = idea
        self.run_id = run_id or f"run_{int(time.time())}"
        self.context = RunContext(self.run_id, base_dir=base_dir)
        self.context.set_idea(self.idea)
        self.event_bus = EventBus(log_path=self.context.events_file)
        self.llm = llm
        self.approval_gates = approval_gates
        self.budget = budget or BudgetConfig()
        self.approval_handler = approval_handler
        self.start_time = time.time()

        if enable_cli_renderer:
            attach_cli_renderer(self.event_bus)

    def _check_budget(self, stage_tokens: int = 0) -> tuple[bool, str]:
        """Verify token and wall-time limits."""
        elapsed = time.time() - self.start_time
        if elapsed > self.budget.max_wall_time_s:
            return False, f"Wall-clock budget exceeded ({elapsed:.1f}s > {self.budget.max_wall_time_s}s)"

        total_tokens = self.context.get_tokens()
        if total_tokens > self.budget.max_run_tokens:
            return False, f"Run token budget exceeded ({total_tokens} > {self.budget.max_run_tokens})"

        if stage_tokens > self.budget.max_stage_tokens:
            return False, f"Stage token budget exceeded ({stage_tokens} > {self.budget.max_stage_tokens})"

        return True, ""

    def _prompt_approval_gate(self, stage: str, artifact_path: str, preview_content: str) -> tuple[str, str]:
        """
        Human-in-the-loop approval gate.
        Returns: (decision, feedback) where decision in ('approved', 'rejected', 'edited').
        """
        self.event_bus.emit(
            ApprovalRequested(
                run_id=self.run_id,
                stage=stage,
                artifact_name=artifact_path,
                preview=preview_content[:500],
            )
        )

        if self.approval_handler:
            decision, feedback = self.approval_handler(stage, artifact_path, preview_content)
        else:
            console.print(Panel(
                f"[bold yellow]Approval Gate: {stage}[/bold yellow]\n\n"
                f"Artifact: [cyan]{artifact_path}[/cyan]\n"
                f"Preview:\n{preview_content[:400]}...",
                title="[yellow]Human-in-the-Loop Gate[/yellow]",
                border_style="yellow",
            ))
            choice = Prompt.ask(
                "[bold cyan]Action[/bold cyan] ([green]a[/green]pprove / [red]r[/red]eject with feedback / [yellow]e[/yellow]dit)",
                choices=["a", "r", "e", "approve", "reject", "edit"],
                default="a",
            ).lower()

            if choice in ("a", "approve"):
                decision = "approved"
                feedback = ""
            elif choice in ("r", "reject"):
                decision = "rejected"
                feedback = Prompt.ask("[bold red]Enter rejection feedback for the agent[/bold red]")
            else:
                decision = "edited"
                feedback = Prompt.ask("[bold yellow]Enter edit notes (or press Enter to confirm in-place edit)[/bold yellow]", default="")

        self.event_bus.emit(
            ApprovalResolved(
                run_id=self.run_id,
                decision=decision,
                feedback=feedback,
            )
        )
        return decision, feedback

    def _load_prompt(self, role: str) -> str:
        """Load role system prompt from shadow/agents/prompts/<role>.md."""
        prompt_path = Path("shadow") / "agents" / "prompts" / f"{role.lower()}.md"
        if prompt_path.exists():
            return prompt_path.read_text(encoding="utf-8")
        raise FileNotFoundError(f"Role prompt not found at {prompt_path}")

    # -----------------------------------------------------------------------
    # Stage 1: ANALYSIS
    # -----------------------------------------------------------------------
    def run_stage_analyst(self, max_retries: int = 2) -> bool:
        ok, reason = self._check_budget()
        if not ok:
            self.context.update_stage(Stage.FAILED, {"reason": reason})
            self.event_bus.emit(ErrorEvent(run_id=self.run_id, message=reason))
            return False

        self.context.update_stage(Stage.ANALYSIS)
        self.event_bus.emit(StageStarted(run_id=self.run_id, stage="ANALYSIS", agent_name="Analyst"))

        system_prompt = self._load_prompt("analyst")
        registry = ToolRegistry(
            workspace_root=self.context.workspace_dir,
            event_bus=self.event_bus,
            run_id=self.run_id,
        )

        tools = registry.get_tools_for_role("Analyst", agent_name="Analyst")
        declarations = registry.get_declarations_for_role("Analyst")

        spec = AgentSpec(
            name="Analyst",
            system_prompt=system_prompt,
            allowed_tools=list(tools.keys()),
            max_steps=self.budget.max_steps_per_stage,
            require_finish_tool=True,
        )

        llm_provider = self.llm or build_provider()
        agent = Agent(
            spec=spec,
            llm=llm_provider,
            tool_registry=tools,
            tool_declarations=declarations,
            event_bus=self.event_bus,
            run_id=self.run_id,
        )

        task_prompt = f"Product Idea: {self.idea}\n\nProduce docs/requirements.md and docs/requirements.json and conclude with finish()."
        current_history = None

        for attempt in range(max_retries + 1):
            result = agent.execute(task=task_prompt, initial_history=current_history)
            self.context.add_tokens(result.total_tokens)
            current_history = result.history

            md_path = self.context.workspace_dir / "docs" / "requirements.md"
            json_path = self.context.workspace_dir / "docs" / "requirements.json"

            errors = []
            if not md_path.exists() or len(md_path.read_text(encoding="utf-8").strip()) == 0:
                errors.append("docs/requirements.md was not created or is empty.")

            if not json_path.exists():
                errors.append("docs/requirements.json was not created.")
            else:
                is_valid, validation_err, _ = validate_requirements(json_path.read_text(encoding="utf-8"))
                if not is_valid:
                    errors.append(validation_err)

            if not errors and result.finished_via_tool:
                # HITL Approval Gate if enabled
                if self.approval_gates:
                    preview = md_path.read_text(encoding="utf-8")
                    decision, feedback = self._prompt_approval_gate("ANALYSIS", "docs/requirements.md", preview)
                    if decision == "rejected":
                        task_prompt = f"Human reviewer requested changes to requirements:\n{feedback}\nPlease revise docs/requirements.md and docs/requirements.json and call finish()."
                        continue

                self.context.record_artifact("requirements_md", "docs/requirements.md")
                self.context.record_artifact("requirements_json", "docs/requirements.json")
                self.event_bus.emit(
                    StageFinished(
                        run_id=self.run_id,
                        stage="ANALYSIS",
                        summary=result.summary,
                        artifacts={
                            "requirements_md": "docs/requirements.md",
                            "requirements_json": "docs/requirements.json",
                        },
                    )
                )
                self.context.checkpoint_git(Stage.ANALYSIS)
                return True

            err_msg = "\n".join(errors) or "Did not conclude with finish() tool."
            if attempt < max_retries:
                task_prompt = (
                    f"ATTENTION: Your requirements deliverables failed validation:\n{err_msg}\n\n"
                    f"Please correct the errors using write_file under docs/ and call finish() again."
                )
                self.event_bus.emit(
                    ErrorEvent(
                        run_id=self.run_id,
                        message=f"Analyst artifact validation attempt {attempt + 1} failed: {err_msg}",
                    )
                )
            else:
                self.context.update_stage(Stage.FAILED, {"reason": err_msg})
                self.event_bus.emit(
                    ErrorEvent(
                        run_id=self.run_id,
                        message=f"Analyst stage failed after {max_retries + 1} attempts: {err_msg}",
                    )
                )
                return False

        return False

    # -----------------------------------------------------------------------
    # Stage 2: DESIGN
    # -----------------------------------------------------------------------
    def run_stage_design(self, max_retries: int = 2) -> bool:
        ok, reason = self._check_budget()
        if not ok:
            self.context.update_stage(Stage.FAILED, {"reason": reason})
            self.event_bus.emit(ErrorEvent(run_id=self.run_id, message=reason))
            return False

        self.context.update_stage(Stage.DESIGN)
        self.event_bus.emit(StageStarted(run_id=self.run_id, stage="DESIGN", agent_name="Architect"))

        system_prompt = self._load_prompt("architect")
        registry = ToolRegistry(
            workspace_root=self.context.workspace_dir,
            event_bus=self.event_bus,
            run_id=self.run_id,
        )

        tools = registry.get_tools_for_role("Architect", agent_name="Architect")
        declarations = registry.get_declarations_for_role("Architect")

        spec = AgentSpec(
            name="Architect",
            system_prompt=system_prompt,
            allowed_tools=list(tools.keys()),
            max_steps=self.budget.max_steps_per_stage,
            require_finish_tool=True,
        )

        req_md = ""
        req_json = ""
        md_file = self.context.workspace_dir / "docs" / "requirements.md"
        json_file = self.context.workspace_dir / "docs" / "requirements.json"
        if md_file.exists():
            req_md = md_file.read_text(encoding="utf-8")
        if json_file.exists():
            req_json = json_file.read_text(encoding="utf-8")

        llm_provider = self.llm or build_provider()
        agent = Agent(
            spec=spec,
            llm=llm_provider,
            tool_registry=tools,
            tool_declarations=declarations,
            event_bus=self.event_bus,
            run_id=self.run_id,
        )

        task_prompt = (
            f"Requirements Specification:\n\n=== docs/requirements.md ===\n{req_md}\n\n"
            f"=== docs/requirements.json ===\n{req_json}\n\n"
            f"Design the architecture for this system. Produce docs/design.md (with a Mermaid diagram) "
            f"and docs/design.json, mapping all AC criteria to implementing modules, and conclude with finish()."
        )
        current_history = None

        for attempt in range(max_retries + 1):
            result = agent.execute(task=task_prompt, initial_history=current_history)
            self.context.add_tokens(result.total_tokens)
            current_history = result.history

            design_md_path = self.context.workspace_dir / "docs" / "design.md"
            design_json_path = self.context.workspace_dir / "docs" / "design.json"

            errors = []
            if not design_md_path.exists() or len(design_md_path.read_text(encoding="utf-8").strip()) == 0:
                errors.append("docs/design.md was not created or is empty.")

            if not design_json_path.exists():
                errors.append("docs/design.json was not created.")
            else:
                is_valid, validation_err, _ = validate_design(design_json_path.read_text(encoding="utf-8"))
                if not is_valid:
                    errors.append(validation_err)

            if not errors and result.finished_via_tool:
                # HITL Approval Gate if enabled
                if self.approval_gates:
                    preview = design_md_path.read_text(encoding="utf-8")
                    decision, feedback = self._prompt_approval_gate("DESIGN", "docs/design.md", preview)
                    if decision == "rejected":
                        task_prompt = f"Human reviewer requested changes to architecture design:\n{feedback}\nPlease revise docs/design.md and docs/design.json and call finish()."
                        continue

                self.context.record_artifact("design_md", "docs/design.md")
                self.context.record_artifact("design_json", "docs/design.json")
                self.event_bus.emit(
                    StageFinished(
                        run_id=self.run_id,
                        stage="DESIGN",
                        summary=result.summary,
                        artifacts={
                            "design_md": "docs/design.md",
                            "design_json": "docs/design.json",
                        },
                    )
                )
                self.context.checkpoint_git(Stage.DESIGN)
                return True

            err_msg = "\n".join(errors) or "Did not conclude with finish() tool."
            if attempt < max_retries:
                task_prompt = (
                    f"ATTENTION: Your design deliverables failed validation:\n{err_msg}\n\n"
                    f"Please correct the errors using write_file under docs/ and call finish() again."
                )
                self.event_bus.emit(
                    ErrorEvent(
                        run_id=self.run_id,
                        message=f"Architect artifact validation attempt {attempt + 1} failed: {err_msg}",
                    )
                )
            else:
                self.context.update_stage(Stage.FAILED, {"reason": err_msg})
                self.event_bus.emit(
                    ErrorEvent(
                        run_id=self.run_id,
                        message=f"Architect stage failed after {max_retries + 1} attempts: {err_msg}",
                    )
                )
                return False

        return False

    # -----------------------------------------------------------------------
    # Stage 3: CODING
    # -----------------------------------------------------------------------
    def run_stage_coding(self, max_retries: int = 2) -> bool:
        ok, reason = self._check_budget()
        if not ok:
            self.context.update_stage(Stage.FAILED, {"reason": reason})
            self.event_bus.emit(ErrorEvent(run_id=self.run_id, message=reason))
            return False

        self.context.update_stage(Stage.CODING)
        self.event_bus.emit(StageStarted(run_id=self.run_id, stage="CODING", agent_name="Developer"))

        system_prompt = self._load_prompt("developer")
        registry = ToolRegistry(
            workspace_root=self.context.workspace_dir,
            event_bus=self.event_bus,
            run_id=self.run_id,
        )

        tools = registry.get_tools_for_role("Developer", agent_name="Developer")
        declarations = registry.get_declarations_for_role("Developer")

        spec = AgentSpec(
            name="Developer",
            system_prompt=system_prompt,
            allowed_tools=list(tools.keys()),
            max_steps=self.budget.max_steps_per_stage,
            require_finish_tool=True,
        )

        context_files = {}
        for p in ["docs/requirements.md", "docs/requirements.json", "docs/design.md", "docs/design.json"]:
            fp = self.context.workspace_dir / p
            if fp.exists():
                context_files[p] = fp.read_text(encoding="utf-8")

        context_str = "\n\n".join(f"=== {k} ===\n{v}" for k, v in context_files.items())

        llm_provider = self.llm or build_provider()
        agent = Agent(
            spec=spec,
            llm=llm_provider,
            tool_registry=tools,
            tool_declarations=declarations,
            event_bus=self.event_bus,
            run_id=self.run_id,
        )

        task_prompt = (
            f"Specifications:\n\n{context_str}\n\n"
            f"Implement all source modules specified in docs/design.json under src/.\n"
            f"Execute your code using run_command to verify it runs without errors.\n"
            f"Do not write tests. Conclude with finish() when verified."
        )
        current_history = None

        for attempt in range(max_retries + 1):
            result = agent.execute(task=task_prompt, initial_history=current_history)
            self.context.add_tokens(result.total_tokens)
            current_history = result.history

            src_dir = self.context.workspace_dir / "src"
            py_files = list(src_dir.rglob("*.py")) if src_dir.exists() else []
            valid_py_files = [f for f in py_files if f.stat().st_size > 0]

            errors = []
            if not src_dir.exists() or len(valid_py_files) == 0:
                errors.append("No non-empty Python files were found under src/.")

            if not errors and result.finished_via_tool:
                artifacts_map = {}
                for f in valid_py_files:
                    rel = str(f.relative_to(self.context.workspace_dir)).replace("\\", "/")
                    name = f.stem
                    artifacts_map[name] = rel
                    self.context.record_artifact(name, rel)

                self.event_bus.emit(
                    StageFinished(
                        run_id=self.run_id,
                        stage="CODING",
                        summary=result.summary,
                        artifacts=artifacts_map,
                    )
                )
                self.context.checkpoint_git(Stage.CODING)
                return True

            err_msg = "\n".join(errors) or "Did not conclude with finish() tool."
            if attempt < max_retries:
                task_prompt = (
                    f"ATTENTION: Your implementation failed validation:\n{err_msg}\n\n"
                    f"Please write working Python files under src/, verify them with run_command, and call finish()."
                )
                self.event_bus.emit(
                    ErrorEvent(
                        run_id=self.run_id,
                        message=f"Developer implementation attempt {attempt + 1} failed: {err_msg}",
                    )
                )
            else:
                self.context.update_stage(Stage.FAILED, {"reason": err_msg})
                self.event_bus.emit(
                    ErrorEvent(
                        run_id=self.run_id,
                        message=f"Developer stage failed after {max_retries + 1} attempts: {err_msg}",
                    )
                )
                return False

        return False

    # -----------------------------------------------------------------------
    # Stage 4: TESTING (↔ DEBUGGING feedback loop)
    # -----------------------------------------------------------------------
    def run_stage_testing(self, iteration: int = 1, max_retries: int = 2) -> tuple[bool, dict[str, Any]]:
        self.context.update_stage(Stage.TESTING, {"iteration": iteration})
        self.event_bus.emit(
            StageStarted(run_id=self.run_id, stage=f"TESTING (iter {iteration})", agent_name="Tester")
        )

        system_prompt = self._load_prompt("tester")
        registry = ToolRegistry(
            workspace_root=self.context.workspace_dir,
            event_bus=self.event_bus,
            run_id=self.run_id,
        )

        tools = registry.get_tools_for_role("Tester", agent_name="Tester")
        declarations = registry.get_declarations_for_role("Tester")

        spec = AgentSpec(
            name="Tester",
            system_prompt=system_prompt,
            allowed_tools=list(tools.keys()),
            max_steps=self.budget.max_steps_per_stage,
            require_finish_tool=True,
        )

        req_md = ""
        req_json = ""
        md_file = self.context.workspace_dir / "docs" / "requirements.md"
        json_file = self.context.workspace_dir / "docs" / "requirements.json"
        if md_file.exists():
            req_md = md_file.read_text(encoding="utf-8")
        if json_file.exists():
            req_json = json_file.read_text(encoding="utf-8")

        llm_provider = self.llm or build_provider()
        agent = Agent(
            spec=spec,
            llm=llm_provider,
            tool_registry=tools,
            tool_declarations=declarations,
            event_bus=self.event_bus,
            run_id=self.run_id,
        )

        task_prompt = (
            f"Requirements:\n=== docs/requirements.md ===\n{req_md}\n\n"
            f"=== docs/requirements.json ===\n{req_json}\n\n"
            f"Derive pytest unit tests for each Acceptance Criterion (AC-1, AC-2...) under tests/.\n"
            f"Tag each test function with its AC id (e.g. def test_ac1_...).\n"
            f"Execute run_tests('tests') and compile test_report.json matching the schema. Conclude with finish()."
        )
        current_history = None

        for attempt in range(max_retries + 1):
            result = agent.execute(task=task_prompt, initial_history=current_history)
            self.context.add_tokens(result.total_tokens)
            current_history = result.history

            report_file = self.context.workspace_dir / "test_report.json"
            report_data: dict[str, Any] = {}
            if report_file.exists():
                try:
                    report_data = json.loads(report_file.read_text(encoding="utf-8"))
                except Exception:
                    pass

            raw_test_output = run_tests("tests", workspace_root=self.context.workspace_dir, event_bus=self.event_bus, run_id=self.run_id)

            passed = "TEST RUN RESULT: PASSED" in raw_test_output or (
                report_data.get("passed", 0) > 0 and report_data.get("failed", 0) == 0 and report_data.get("errors", 0) == 0
            )

            if not report_data.get("failures") and not passed:
                failures_map = {}
                import re
                blocks = re.findall(r"_{3,}\s*(.*?)\s*_{3,}(.*?)(?=\n_{3,}|\n={3,}|\Z)", raw_test_output, re.DOTALL)
                for name, trace in blocks:
                    failures_map[name.strip()] = trace.strip()[:500]
                report_data.setdefault("failures", failures_map)
                report_data.setdefault("failed", len(failures_map) or 1)

            if report_file.exists():
                self.context.record_artifact("test_report", "test_report.json")

            if passed:
                self.context.checkpoint_git(Stage.TESTING)
                self.event_bus.emit(
                    StageFinished(
                        run_id=self.run_id,
                        stage="TESTING",
                        summary=f"Iteration {iteration}: All tests passed.",
                        artifacts={"test_report": "test_report.json"},
                    )
                )
                return True, report_data

            return False, report_data

        return False, {}

    def run_stage_debugging(
        self,
        test_report: dict[str, Any],
        iteration: int = 1,
        max_retries: int = 2,
    ) -> bool:
        self.context.update_stage(Stage.DEBUGGING, {"iteration": iteration})
        self.event_bus.emit(
            StageStarted(run_id=self.run_id, stage=f"DEBUGGING (iter {iteration})", agent_name="Debugger")
        )

        system_prompt = self._load_prompt("debugger")
        registry = ToolRegistry(
            workspace_root=self.context.workspace_dir,
            event_bus=self.event_bus,
            run_id=self.run_id,
        )

        tools = registry.get_tools_for_role("Debugger", agent_name="Debugger")
        declarations = registry.get_declarations_for_role("Debugger")

        spec = AgentSpec(
            name="Debugger",
            system_prompt=system_prompt,
            allowed_tools=list(tools.keys()),
            max_steps=self.budget.max_steps_per_stage,
            require_finish_tool=True,
        )

        failures_str = json.dumps(test_report.get("failures", {}), indent=2)

        task_prompt = (
            f"Test Failures in Iteration {iteration}:\n{failures_str}\n\n"
            f"Diagnose the root cause in src/, apply minimal surgical fixes using edit_file, "
            f"record your diagnosis in debug_log.md, run_tests('tests') to verify, and conclude with finish()."
        )

        llm_provider = self.llm or build_provider()
        agent = Agent(
            spec=spec,
            llm=llm_provider,
            tool_registry=tools,
            tool_declarations=declarations,
            event_bus=self.event_bus,
            run_id=self.run_id,
        )

        result = agent.execute(task=task_prompt)
        self.context.add_tokens(result.total_tokens)

        debug_log_path = self.context.workspace_dir / "debug_log.md"
        if debug_log_path.exists():
            self.context.record_artifact("debug_log", "debug_log.md")

        self.context.checkpoint_git(Stage.DEBUGGING)
        self.event_bus.emit(
            StageFinished(
                run_id=self.run_id,
                stage="DEBUGGING",
                summary=result.summary,
                artifacts={"debug_log": "debug_log.md"} if debug_log_path.exists() else {},
            )
        )
        return True

    def run_developer_replan(self, test_report: dict[str, Any]) -> bool:
        self.context.update_stage(Stage.CODING, {"escalation": True})
        self.event_bus.emit(
            StageStarted(run_id=self.run_id, stage="CODING (escalation)", agent_name="Developer")
        )

        system_prompt = self._load_prompt("developer")
        registry = ToolRegistry(
            workspace_root=self.context.workspace_dir,
            event_bus=self.event_bus,
            run_id=self.run_id,
        )

        tools = registry.get_tools_for_role("Developer", agent_name="Developer")
        declarations = registry.get_declarations_for_role("Developer")

        spec = AgentSpec(
            name="Developer",
            system_prompt=system_prompt,
            allowed_tools=list(tools.keys()),
            max_steps=self.budget.max_steps_per_stage,
            require_finish_tool=True,
        )

        task_prompt = (
            f"ESCALATION: The autonomous debugger encountered repeating test failures:\n"
            f"{json.dumps(test_report.get('failures', {}), indent=2)}\n\n"
            f"Please re-examine and revise your implementation under src/. "
            f"Execute the code with run_command to verify and call finish()."
        )

        llm_provider = self.llm or build_provider()
        agent = Agent(
            spec=spec,
            llm=llm_provider,
            tool_registry=tools,
            tool_declarations=declarations,
            event_bus=self.event_bus,
            run_id=self.run_id,
        )

        result = agent.execute(task=task_prompt)
        self.context.add_tokens(result.total_tokens)
        self.context.checkpoint_git(Stage.CODING)
        return True

    def run_testing_debugging_loop(self, max_iterations: int = 4) -> bool:
        failure_signature_history: list[str] = []
        escalated_to_developer = False

        for iteration in range(1, max_iterations + 1):
            ok, reason = self._check_budget()
            if not ok:
                self.context.update_stage(Stage.FAILED, {"reason": reason})
                self.event_bus.emit(ErrorEvent(run_id=self.run_id, message=reason))
                return False

            passed, report = self.run_stage_testing(iteration=iteration)
            if passed:
                return True

            if iteration == max_iterations:
                err_msg = f"Testing-Debugging loop exceeded {max_iterations} iterations without all tests passing."
                self.context.update_stage(Stage.FAILED, {"reason": err_msg})
                self.event_bus.emit(ErrorEvent(run_id=self.run_id, message=err_msg))
                return False

            failures = report.get("failures", {})
            sig = compute_failure_signature(failures)
            failure_signature_history.append(sig)

            # Loop Guard: Check if identical failure signature occurs twice in a row
            if len(failure_signature_history) >= 2 and failure_signature_history[-1] == failure_signature_history[-2]:
                self.event_bus.emit(
                    LoopDetected(
                        run_id=self.run_id,
                        iteration=iteration,
                        failure_hash=sig,
                        reason=f"Identical test failure signature detected twice consecutively in iteration {iteration}",
                    )
                )

                if not escalated_to_developer:
                    self.run_developer_replan(report)
                    escalated_to_developer = True
                else:
                    err_msg = "Identical test failure signature unresolvable after Developer escalation; halting run."
                    self.context.update_stage(Stage.FAILED, {"reason": err_msg})
                    self.event_bus.emit(ErrorEvent(run_id=self.run_id, message=err_msg))
                    return False
            else:
                self.run_stage_debugging(report, iteration=iteration)

        return False

    # -----------------------------------------------------------------------
    # Stage 5: REVIEW
    # -----------------------------------------------------------------------
    def run_stage_review(self, max_retries: int = 2) -> bool:
        ok, reason = self._check_budget()
        if not ok:
            self.context.update_stage(Stage.FAILED, {"reason": reason})
            self.event_bus.emit(ErrorEvent(run_id=self.run_id, message=reason))
            return False

        self.context.update_stage(Stage.REVIEW)
        self.event_bus.emit(StageStarted(run_id=self.run_id, stage="REVIEW", agent_name="Reviewer"))

        system_prompt = self._load_prompt("reviewer")
        registry = ToolRegistry(
            workspace_root=self.context.workspace_dir,
            event_bus=self.event_bus,
            run_id=self.run_id,
        )

        tools = registry.get_tools_for_role("Reviewer", agent_name="Reviewer")
        declarations = registry.get_declarations_for_role("Reviewer")

        spec = AgentSpec(
            name="Reviewer",
            system_prompt=system_prompt,
            allowed_tools=list(tools.keys()),
            max_steps=self.budget.max_steps_per_stage,
            require_finish_tool=True,
        )

        llm_provider = self.llm or build_provider()
        agent = Agent(
            spec=spec,
            llm=llm_provider,
            tool_registry=tools,
            tool_declarations=declarations,
            event_bus=self.event_bus,
            run_id=self.run_id,
        )

        task_prompt = (
            "Review the codebase against docs/requirements.json, docs/design.json, and test_report.json.\n"
            "Produce docs/review.md with the full Requirements Traceability Matrix and security assessment.\n"
            "Conclude with finish()."
        )
        current_history = None

        for attempt in range(max_retries + 1):
            result = agent.execute(task=task_prompt, initial_history=current_history)
            self.context.add_tokens(result.total_tokens)
            current_history = result.history

            review_path = self.context.workspace_dir / "docs" / "review.md"
            if not review_path.exists():
                # Check root review.md
                review_path = self.context.workspace_dir / "review.md"

            if review_path.exists() and len(review_path.read_text(encoding="utf-8").strip()) > 0 and result.finished_via_tool:
                rel = str(review_path.relative_to(self.context.workspace_dir)).replace("\\", "/")
                self.context.record_artifact("review_md", rel)
                self.event_bus.emit(
                    StageFinished(
                        run_id=self.run_id,
                        stage="REVIEW",
                        summary=result.summary,
                        artifacts={"review_md": rel},
                    )
                )
                self.context.checkpoint_git(Stage.REVIEW)
                return True

            if attempt < max_retries:
                task_prompt = "ATTENTION: docs/review.md was not written or is empty. Please write docs/review.md and call finish()."
            else:
                self.context.update_stage(Stage.FAILED, {"reason": "Reviewer failed to write docs/review.md"})
                return False

        return False

    # -----------------------------------------------------------------------
    # Stage 6: DOCS
    # -----------------------------------------------------------------------
    def run_stage_docs(self, max_retries: int = 2) -> bool:
        ok, reason = self._check_budget()
        if not ok:
            self.context.update_stage(Stage.FAILED, {"reason": reason})
            self.event_bus.emit(ErrorEvent(run_id=self.run_id, message=reason))
            return False

        self.context.update_stage(Stage.DOCS)
        self.event_bus.emit(StageStarted(run_id=self.run_id, stage="DOCS", agent_name="Documenter"))

        system_prompt = self._load_prompt("documenter")
        registry = ToolRegistry(
            workspace_root=self.context.workspace_dir,
            event_bus=self.event_bus,
            run_id=self.run_id,
        )

        tools = registry.get_tools_for_role("Documenter", agent_name="Documenter")
        declarations = registry.get_declarations_for_role("Documenter")

        spec = AgentSpec(
            name="Documenter",
            system_prompt=system_prompt,
            allowed_tools=list(tools.keys()),
            max_steps=self.budget.max_steps_per_stage,
            require_finish_tool=True,
        )

        llm_provider = self.llm or build_provider()
        agent = Agent(
            spec=spec,
            llm=llm_provider,
            tool_registry=tools,
            tool_declarations=declarations,
            event_bus=self.event_bus,
            run_id=self.run_id,
        )

        task_prompt = (
            "Produce comprehensive user documentation for the project:\n"
            "1. Write README.md in the workspace root with Quickstart, Installation, and Usage examples.\n"
            "2. Write docs/changelog.md.\n"
            "3. Execute run_command to verify your usage instructions work.\n"
            "4. Conclude with finish()."
        )
        current_history = None

        for attempt in range(max_retries + 1):
            result = agent.execute(task=task_prompt, initial_history=current_history)
            self.context.add_tokens(result.total_tokens)
            current_history = result.history

            readme_path = self.context.workspace_dir / "README.md"
            changelog_path = self.context.workspace_dir / "docs" / "changelog.md"

            if readme_path.exists() and len(readme_path.read_text(encoding="utf-8").strip()) > 0 and result.finished_via_tool:
                self.context.record_artifact("readme", "README.md")
                if changelog_path.exists():
                    self.context.record_artifact("changelog", "docs/changelog.md")

                self.event_bus.emit(
                    StageFinished(
                        run_id=self.run_id,
                        stage="DOCS",
                        summary=result.summary,
                        artifacts={"readme": "README.md"},
                    )
                )
                self.context.checkpoint_git(Stage.DOCS)
                return True

            if attempt < max_retries:
                task_prompt = "ATTENTION: README.md was not written or is empty. Please create README.md and call finish()."
            else:
                self.context.update_stage(Stage.FAILED, {"reason": "Documenter failed to write README.md"})
                return False

        return False

    # -----------------------------------------------------------------------
    # Full Lifecycle Pipeline Execution
    # -----------------------------------------------------------------------
    def execute_pipeline(self, target_stage: Stage = Stage.DONE, start_from_stage: Optional[Stage] = None) -> bool:
        """
        Execute the factory pipeline sequentially across all stages up to target_stage.
        Supports cancellation and resuming from a specified stage.
        """
        self.event_bus.emit(RunStarted(run_id=self.run_id, idea=self.idea))

        stages_sequence = [
            (Stage.ANALYSIS, self.run_stage_analyst),
            (Stage.DESIGN, self.run_stage_design),
            (Stage.CODING, self.run_stage_coding),
            (Stage.TESTING, lambda: self.run_testing_debugging_loop(max_iterations=4)),
            (Stage.REVIEW, self.run_stage_review),
            (Stage.DOCS, self.run_stage_docs),
        ]

        skipping = start_from_stage is not None

        try:
            for stage_enum, stage_fn in stages_sequence:
                if skipping:
                    if stage_enum == start_from_stage:
                        skipping = False
                    else:
                        continue

                # Run stage
                success = stage_fn()
                if not success:
                    self.context.update_stage(Stage.FAILED)
                    self.event_bus.emit(RunFinished(run_id=self.run_id, status="failed"))
                    return False

                if target_stage == stage_enum:
                    self.context.update_stage(Stage.DONE)
                    self.event_bus.emit(RunFinished(run_id=self.run_id, status="success"))
                    return True

            self.context.update_stage(Stage.DONE)
            self.event_bus.emit(RunFinished(run_id=self.run_id, status="success"))
            return True

        except KeyboardInterrupt:
            console.print("\n[yellow]Run cancelled by user.[/yellow]")
            self.context.update_stage(Stage.CANCELLED)
            self.event_bus.emit(RunFinished(run_id=self.run_id, status="cancelled"))
            return False
        except Exception as e:
            self.context.update_stage(Stage.FAILED, {"error": str(e)})
            self.event_bus.emit(ErrorEvent(run_id=self.run_id, message=f"Fatal pipeline error: {e}"))
            self.event_bus.emit(RunFinished(run_id=self.run_id, status="failed"))
            return False


def resume_run(
    run_id: str,
    base_dir: Union[str, Path] = "runs",
    llm: Optional[LLMProvider] = None,
    approval_gates: bool = False,
    budget: Optional[BudgetConfig] = None,
) -> bool:
    """Resume an existing run from the earliest unfinished stage."""
    ctx = RunContext(run_id=run_id, base_dir=base_dir)
    idea = ctx.get_idea() or "Resumed Project"
    checkpoints = ctx.get_checkpoints()

    console.print(Panel(
        f"[bold cyan]🔄 Resuming ShadowX Factory Run:[/bold cyan] {run_id}\n"
        f"[dim]Idea:[/dim] {idea}\n"
        f"[dim]Completed Checkpoints:[/dim] {list(checkpoints.keys())}",
        border_style="cyan",
    ))

    # Stage order mapping
    ordered_stages = [
        Stage.ANALYSIS,
        Stage.DESIGN,
        Stage.CODING,
        Stage.TESTING,
        Stage.REVIEW,
        Stage.DOCS,
    ]

    resume_stage = None
    for s in ordered_stages:
        if s.value not in checkpoints:
            resume_stage = s
            break

    if not resume_stage:
        console.print("[green]All stages for this run have already completed successfully.[/green]")
        return True

    console.print(f"[bold yellow]Resuming pipeline from stage:[/bold yellow] [bold cyan]{resume_stage.value}[/bold cyan]")
    orchestrator = Orchestrator(
        idea=idea,
        run_id=run_id,
        llm=llm,
        base_dir=base_dir,
        approval_gates=approval_gates,
        budget=budget,
    )
    return orchestrator.execute_pipeline(start_from_stage=resume_stage)


def run_factory(
    idea: str,
    run_id: Optional[str] = None,
    approval_gates: bool = False,
    resume_id: Optional[str] = None,
    budget: Optional[BudgetConfig] = None,
) -> bool:
    """Entry point for running the ShadowX Factory pipeline."""
    if resume_id:
        return resume_run(run_id=resume_id, approval_gates=approval_gates, budget=budget)

    console.print(Panel(
        f"[bold cyan]🏭 ShadowX Factory[/bold cyan]\n[dim]Idea:[/dim] [yellow]{idea}[/yellow]\n"
        f"[dim]Approval Gates:[/dim] {'Enabled' if approval_gates else 'Disabled'}",
        border_style="cyan",
    ))
    orchestrator = Orchestrator(
        idea=idea,
        run_id=run_id,
        approval_gates=approval_gates,
        budget=budget,
    )
    return orchestrator.execute_pipeline()


def main() -> None:
    parser = argparse.ArgumentParser(
        prog="pipeline.orchestrator",
        description="ShadowX Factory — Agentic Software Pipeline Orchestrator",
    )
    parser.add_argument("idea", nargs="?", default="", help="One-line product idea to develop")
    parser.add_argument("--run-id", default=None, help="Custom run identifier")
    parser.add_argument("--resume", default=None, help="Resume an existing run by run_id")
    parser.add_argument("--gates", action="store_true", help="Enable human approval gates after requirements and design")
    parser.add_argument("--max-tokens", type=int, default=100000, help="Maximum total token budget")
    parser.add_argument("--max-time", type=float, default=600.0, help="Maximum wall-clock time in seconds")
    parser.add_argument(
        "--target-stage",
        choices=[s.value for s in Stage],
        default=Stage.DONE.value,
        help="Target stage to run up to",
    )

    args = parser.parse_args()

    if not args.idea and not args.resume:
        parser.error("Either an idea or --resume <run_id> must be specified.")

    budget = BudgetConfig(
        max_run_tokens=args.max_tokens,
        max_wall_time_s=args.max_time,
    )

    success = run_factory(
        idea=args.idea,
        run_id=args.run_id,
        approval_gates=args.gates,
        resume_id=args.resume,
        budget=budget,
    )
    sys.exit(0 if success else 1)


if __name__ == "__main__":
    main()
