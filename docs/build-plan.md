# ShadowX Factory — 20-Day Build Plan

This build plan defines the chronological roadmap for building **ShadowX Factory**: an Agentic Software Factory where multiple specialised AI agents collaborate across the software development lifecycle.

---

## Phase A: Core Foundation & Tool Hardening (Days 1–5)

### Day 1: Event Bus & LLM Provider Abstraction
- **Goal**: Decouple the agent loop from terminal printing and API volatility.
- **Deliverables**:
  - `shadow/core/events.py`: Typed event dataclasses (`RunStarted`, `StageStarted`, `LLMCallEvent`, `ToolCallEvent`, `ToolResultEvent`, `ArtifactCreated`, `TestResultEvent`, `ApprovalRequested`, `ApprovalResolved`, `StageFinished`, `LoopDetected`, `RunFinished`, `ErrorEvent`).
  - `shadow/core/event_bus.py`: In-process publisher-subscriber bus supporting sync and async handlers with JSONL file logging.
  - `shadow/core/llm.py`: Abstract `LLMProvider` interface, `GeminiProvider` with exponential backoff on HTTP 429 and 5xx errors, token and latency tracking, and `FakeLLMProvider` with scripted responses for offline testing.
- **Tests**: `tests/test_events.py`, `tests/test_llm_provider.py`.

### Day 2: Reusable Spec-Driven Agent Class
- **Goal**: Refactor single-file agent logic into a reusable `Agent` engine.
- **Deliverables**:
  - `shadow/core/agent.py`: `AgentSpec` dataclass (role, system prompt, allowed tools, max steps, temperature, token budget) and `Agent` class.
  - Preserve Gemini `thought_signature` handling using dual-track memory (`live_contents` holding native SDK objects, `history` storing clean JSON).
  - Built-in `finish(summary, artifacts)` tool required for stage termination.
  - Context budget manager: monitors running token estimates and trims/summarises older tool outputs.
- **Tests**: `tests/test_agent_core.py`.

### Day 3: Backward-Compatible Single-Agent ShadowX CLI
- **Goal**: Maintain the existing single-agent CLI while utilizing the new core.
- **Deliverables**:
  - Refactor `shadow/agent.py` to route through `shadow/core/`.
  - Ensure `python -m shadow.cli` and `shadowx.bat` work seamlessly.
  - Add tests validating single-agent behavior without regressions.

### Day 4: Hardened Workspace Tools & Path Sandboxing
- **Goal**: Secure tool execution strictly within the run workspace.
- **Deliverables**:
  - `shadow/tools/filesystem.py`: `read_file`, `write_file`, `list_files`, `glob_files`, `grep_search`.
  - Path traversal guard: Rejects `../` escapes, absolute path escapes, and symlink breakouts.
  - Surgical `edit_file`: Returns error if `old_text` is missing or not unique; returns a unified diff on success.
- **Tests**: `tests/test_tools_filesystem.py`.

### Day 5: Shell Sandboxing, Structured Pytest Runner & Git Checkpointing
- **Goal**: Secure command execution, structured test feedback, and rollback capability.
- **Deliverables**:
  - `shadow/tools/shell.py`: `run_command` with 30s–120s configurable timeout, output truncation preserving head and tail, command blocklist defense-in-depth, scrubbed environment (no API keys), `cwd` set to workspace.
  - `shadow/tools/testing.py`: `run_tests` running pytest in workspace, returning structured JSON (passed, failed, errors, failure message per test).
  - `shadow/tools/git_helpers.py`: Workspace git initialization and stage checkpoint commits for rollback.
- **Tests**: `tests/test_tools_shell.py`.

---

## Phase B: Role Prompts & State Machine Orchestrator (Days 6–10)

### Day 6: Specialized Agent Role Prompts & Validation Schemas
- **Goal**: Define prompt contracts and artifact validation schemas.
- **Deliverables**:
  - `shadow/agents/prompts/`: Markdown prompt files for Analyst, Architect, Developer, Tester, Debugger, Reviewer, and Documenter.
  - `pipeline/schemas.py`: Pydantic models for `RequirementsArtifact`, `DesignArtifact`, `TestReportArtifact`, `ReviewReportArtifact`.
  - Re-prompt mechanism (max 2 retries) if `finish()` produces invalid or missing artifacts.
- **Tests**: `tests/test_schemas.py`.

### Day 7: Run Directory Architecture & State Management
- **Goal**: Establish isolated run directories for deterministic execution.
- **Deliverables**:
  - `pipeline/run_context.py`: `runs/<run_id>/` structure (`workspace/`, `artifacts/`, `events.jsonl`, `state.json`).
  - Artifact store and atomic JSON state updates.
- **Tests**: `tests/test_run_context.py`.

### Day 8: Explicit State Machine Orchestrator
- **Goal**: Deterministic stage transitions without LLM routing ambiguity.
- **Deliverables**:
  - `pipeline/orchestrator.py`: State machine transitioning through `ANALYSIS` → `DESIGN` → `CODING` → `TESTING` → `REVIEW` → `DOCS` → `DONE` (plus `FAILED` and `CANCELLED`).
  - Stage execution runner: loads role prompt, assigns allowed tools, runs agent, validates output artifacts.
- **Tests**: `tests/test_orchestrator_states.py`.

### Day 9: Tester-Debugger Feedback Loop & Loop Guards
- **Goal**: Autonomous test-driven repair with anti-hallucination guards.
- **Deliverables**:
  - Cyclic transition: `TESTING` → `DEBUGGING` → `TESTING` (up to $N=4$ iterations).
  - Failure signature hashing (failing test names + error types).
  - Escalation rule: If failure signature is identical twice in a row, escalate to Developer with re-plan prompt; if still repeating, stop with `FAILED`.
  - Repetitive tool call detector (flags 3 identical tool calls).
- **Tests**: `tests/test_loop_guard.py`.

### Day 10: Human-in-the-Loop (HITL) Gates, Budgets & Resumption
- **Goal**: Human oversight, token/time budgets, and stage resumption.
- **Deliverables**:
  - Configurable approval gates after requirements and design (Approve, Reject with feedback, Edit artifact).
  - Wall-clock time budget, per-stage token budgets, and step limits.
  - Resume functionality: reload state from `state.json` and resume from the last completed stage.
- **Tests**: `tests/test_hitl_and_resume.py`.

---

## Phase C: Backend API & Observability (Days 11–15)

### Day 11: FastAPI Application & SQLite Run Index
- **Goal**: Expose the factory engine via a modern REST API.
- **Deliverables**:
  - `api/app.py`: FastAPI server started with `python -m uvicorn api.app:app`.
  - `api/db.py`: SQLite index for runs, metrics, and state history.
  - Endpoints: `POST /runs`, `GET /runs`, `GET /runs/{id}`, `POST /runs/{id}/cancel`.
- **Tests**: `tests/test_api_runs.py`.

### Day 12: Real-Time Event Streaming (Server-Sent Events)
- **Goal**: Live streaming of run events to external clients.
- **Deliverables**:
  - `GET /runs/{id}/events`: Server-Sent Events (SSE) with `Last-Event-ID` support for reconnection and replay.
  - Event streaming connector from `event_bus` to active HTTP connections.
- **Tests**: `tests/test_api_events_sse.py`.

### Day 13: Artifact, Workspace & File Inspection Endpoints
- **Goal**: Enable web UI to browse source code, diffs, and artifacts.
- **Deliverables**:
  - `GET /runs/{id}/artifacts`: List and fetch generated Markdown and JSON artifacts.
  - `GET /runs/{id}/files` and `GET /runs/{id}/files/{path}`: Workspace directory tree and file contents.
  - `GET /runs/{id}/zip`: Download the entire workspace and artifacts as a ZIP archive.
- **Tests**: `tests/test_api_files.py`.

### Day 14: Human Approval & Interactive Control Endpoints
- **Goal**: Endpoints for human approval gates and interactive decisions.
- **Deliverables**:
  - `POST /runs/{id}/approve`: Submit decision (`approved`, `rejected`), user feedback, or edited content.
  - Background task worker coordination for paused and resumed execution.
- **Tests**: `tests/test_api_approval.py`.

### Day 15: Run Metrics & Comparative Evaluation Engine
- **Goal**: Compute, store, and serve run performance metrics.
- **Deliverables**:
  - Per-run metrics aggregation: success rate, stage durations, token counts, cost estimate, debug loop count, test pass percentage.
  - `GET /metrics/compare`: API endpoint serving performance comparison between ShadowX Single-Agent and ShadowX Factory.
- **Tests**: `tests/test_metrics.py`.

---

## Phase D: Web UI, Benchmarks, Documentation & Final Polish (Days 16–20)

### Day 16: Interactive Web UI Dashboard
- **Goal**: High-impact browser UI for running and monitoring the factory.
- **Deliverables**:
  - Launch Screen: Idea input, example presets, configuration toggles (approval gates, max iterations, model selection).
  - Pipeline Graph: Live state machine visualization showing active agent, completed stages, and the Tester-Debugger cycle.
  - Live Console & Agent Panel: Real-time event timeline, token and elapsed time counters, collapsible tool calls.
  - Monaco Viewer & Artifact Viewer: Syntax-highlighted code tree, per-file diffs, rendered requirements, and Mermaid design diagrams.

### Day 17: Offline Replay Mode & Test Viewer
- **Goal**: Flawless, quota-free offline presentations and test inspection.
- **Deliverables**:
  - Replay Mode: Reads saved `events.jsonl` files at variable speeds (0.5x, 1x, 2x, 5x) to demonstrate complex runs without API tokens or network.
  - Test Results View: Breakdown of acceptance criteria vs. passing unit tests across debug iterations.
  - Dark and Light mode theme toggle with responsive layout.

### Day 18: Benchmark Suite & Empirical Evaluation
- **Goal**: Objective proof of multi-agent superiority over single-agent baselines.
- **Deliverables**:
  - `evals/tasks/*.yaml`: 8 diverse benchmark tasks (CLI todo app, URL shortener API, bank account library, markdown-to-HTML converter, rate limiter, expense tracker with SQLite, CSV cleaner script, text adventure game).
  - Hidden test suites for each benchmark.
  - `evals/run_evals.py`: Automated benchmarking runner testing both Single-Agent and Factory modes $N$ times.
  - `evals/comparison_table.md` & `eval_results.json`: Output comparison of success rate, debug cycles, tokens, and wall time.

### Day 19: Architecture Decision Records (ADRs) & Comprehensive Documentation
- **Goal**: Clear technical documentation explaining every engineering choice.
- **Deliverables**:
  - `docs/adr/`: Architecture Decision Records:
    - ADR-001: Explicit State-Machine Orchestrator vs. LLM Routing.
    - ADR-002: Filesystem Artifacts as Shared Inter-Agent Memory.
    - ADR-003: Server-Sent Events (SSE) vs. WebSockets for Observability.
    - ADR-004: Principle of Least Privilege for Role Tool Permissions.
    - ADR-005: Zero-Framework Native Architecture vs. LangChain/CrewAI.
  - `docs/architecture.md`: System diagram, sequence of a run, state machine diagram, and event flow.
  - `.env.example`, updated `README.md`, and `.gitignore`.

### Day 20: Full Verification, Failure Analysis & Interview Presentation Kit
- **Goal**: Flawless project submission and video demonstration readiness.
- **Deliverables**:
  - Complete end-to-end test execution with `pytest`.
  - Codebase linting and formatting with `ruff`.
  - Failure analysis report documenting real edge cases caught during development.
  - 8-minute explainer video script and presentation cheat sheet with common interview defense questions.
