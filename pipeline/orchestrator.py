"""
orchestrator.py — Deterministic State Machine Orchestrator for ShadowX Factory.

Coordinates multi-agent software development lifecycle:
ANALYSIS -> DESIGN -> CODING -> TESTING -> (DEBUGGING -> TESTING)* -> REVIEW -> DOCS -> DONE

Agents communicate only through filesystem artifacts and validated Pydantic schemas.
Git checkpoints are captured after every stage completion.
"""

from __future__ import annotations
import os
import sys
import json
import time
import shutil
import argparse
from enum import Enum
from pathlib import Path
from typing import Optional, Union, Any

from rich.console import Console
from rich.panel import Panel

from shadow.core.agent import Agent, AgentSpec, AgentResult
from shadow.core.events import (
    RunStarted,
    StageStarted,
    StageFinished,
    RunFinished,
    ErrorEvent,
)
from shadow.core.event_bus import EventBus
from shadow.core.llm import LLMProvider, GeminiProvider
from shadow.tools.registry import ToolRegistry
from shadow.agent import build_provider, attach_cli_renderer
from pipeline.schemas import validate_requirements, validate_design
from pipeline.git_checkpoints import init_workspace_git, create_checkpoint

console = Console()


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
    Executes the deterministic state machine for a factory run.
    """

    def __init__(
        self,
        idea: str,
        run_id: Optional[str] = None,
        llm: Optional[LLMProvider] = None,
        base_dir: Union[str, Path] = "runs",
        enable_cli_renderer: bool = True,
    ) -> None:
        self.idea = idea
        self.run_id = run_id or f"run_{int(time.time())}"
        self.context = RunContext(self.run_id, base_dir=base_dir)
        self.event_bus = EventBus(log_path=self.context.events_file)
        self.llm = llm

        if enable_cli_renderer:
            attach_cli_renderer(self.event_bus)

    def _load_prompt(self, role: str) -> str:
        """Load role system prompt from shadow/agents/prompts/<role>.md."""
        prompt_path = Path("shadow") / "agents" / "prompts" / f"{role.lower()}.md"
        if prompt_path.exists():
            return prompt_path.read_text(encoding="utf-8")
        raise FileNotFoundError(f"Role prompt not found at {prompt_path}")

    def run_stage_analyst(self, max_retries: int = 2) -> bool:
        """
        Execute the ANALYSIS stage:
        Analyst agent transforms idea -> docs/requirements.md and docs/requirements.json.
        """
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
            max_steps=15,
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

            # Validate outputs
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
                # Success! Record artifacts and stage finish
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

    def run_stage_design(self, max_retries: int = 2) -> bool:
        """
        Execute the DESIGN stage:
        Architect agent reads requirements -> docs/design.md (with Mermaid) and docs/design.json.
        """
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
            max_steps=15,
            require_finish_tool=True,
        )

        # Load requirements as context
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

            # Validate outputs
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
                # Success! Record artifacts and stage finish
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

    def run_stage_coding(self, max_retries: int = 2) -> bool:
        """
        Execute the CODING stage:
        Developer agent implements all modules under src/ according to requirements and design,
        and runs the code at least once using run_command to verify it executes cleanly.
        """
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
            max_steps=20,
            require_finish_tool=True,
        )

        # Gather context
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

            # Validate outputs
            src_dir = self.context.workspace_dir / "src"
            py_files = list(src_dir.rglob("*.py")) if src_dir.exists() else []
            valid_py_files = [f for f in py_files if f.stat().st_size > 0]

            errors = []
            if not src_dir.exists() or len(valid_py_files) == 0:
                errors.append("No non-empty Python files were found under src/.")

            if not errors and result.finished_via_tool:
                # Record source artifacts
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

    def execute_pipeline(self, target_stage: Stage = Stage.DONE) -> bool:
        """
        Run the factory state machine through ANALYSIS -> DESIGN -> CODING up to target_stage.
        """
        self.event_bus.emit(RunStarted(run_id=self.run_id, idea=self.idea))

        # Stage 1: Analysis
        if not self.run_stage_analyst():
            self.context.update_stage(Stage.FAILED)
            self.event_bus.emit(RunFinished(run_id=self.run_id, status="failed"))
            return False

        if target_stage == Stage.ANALYSIS:
            self.context.update_stage(Stage.DONE)
            self.event_bus.emit(RunFinished(run_id=self.run_id, status="success"))
            return True

        # Stage 2: Design
        if not self.run_stage_design():
            self.context.update_stage(Stage.FAILED)
            self.event_bus.emit(RunFinished(run_id=self.run_id, status="failed"))
            return False

        if target_stage == Stage.DESIGN:
            self.context.update_stage(Stage.DONE)
            self.event_bus.emit(RunFinished(run_id=self.run_id, status="success"))
            return True

        # Stage 3: Coding
        if not self.run_stage_coding():
            self.context.update_stage(Stage.FAILED)
            self.event_bus.emit(RunFinished(run_id=self.run_id, status="failed"))
            return False

        if target_stage in (Stage.CODING, Stage.DONE):
            self.context.update_stage(Stage.DONE)
            self.event_bus.emit(RunFinished(run_id=self.run_id, status="success"))
            return True

        self.context.update_stage(Stage.DONE)
        self.event_bus.emit(RunFinished(run_id=self.run_id, status="success"))
        return True


def run_factory(idea: str, run_id: Optional[str] = None) -> bool:
    """Entry point for running the ShadowX Factory pipeline."""
    console.print(Panel(
        f"[bold cyan]🏭 ShadowX Factory[/bold cyan]\n[dim]Idea:[/dim] [yellow]{idea}[/yellow]",
        border_style="cyan",
    ))
    orchestrator = Orchestrator(idea=idea, run_id=run_id)
    return orchestrator.execute_pipeline()


def main() -> None:
    parser = argparse.ArgumentParser(
        prog="pipeline.orchestrator",
        description="ShadowX Factory — Agentic Software Pipeline Orchestrator",
    )
    parser.add_argument("idea", help="One-line product idea to develop")
    parser.add_argument("--run-id", default=None, help="Custom run identifier")
    parser.add_argument(
        "--target-stage",
        choices=[s.value for s in Stage],
        default=Stage.DONE.value,
        help="Target stage to run up to",
    )

    args = parser.parse_args()
    success = run_factory(idea=args.idea, run_id=args.run_id)
    sys.exit(0 if success else 1)


if __name__ == "__main__":
    main()
