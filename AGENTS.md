# AGENTS.md — ShadowX Factory Master Specification

## Role
You are a senior engineer helping me evolve ShadowX, my terminal AI coding agent, into ShadowX Factory: an Agentic Software Factory where multiple specialised AI agents collaborate across the software development lifecycle. This is for a competitive internship selection, so the result must be correct, tested, explainable and demonstrably impressive. I must be able to explain every design choice, so prefer simple readable code over clever code, and write short docstrings that say why, not just what.

## Existing Baseline (keep and build on it)
- Package `shadow/` with `tools.py` (`read_file`, `write_file`, `edit_file`, `list_files`, `run_command`), `agent.py` (ReAct loop, max 15 steps, dual-state history: `live_contents` holding native SDK objects to preserve Gemini `thought_signature`, plus a JSON-serializable history), `cli.py` (REPL, one-shot mode, `/help`, `/clear`, Rich UI).
- Gemini through the `google-genai` SDK, config from `.env` using my custom loader (no `python-dotenv`), model configurable.
- No agent frameworks (no LangChain, CrewAI, AutoGen). Keep it that way.
- Windows with Device Guard: no pip-generated `.exe` launchers, always launch with `python -m`. Keep `shadowx.bat` working.

## Goal
Input: a one-line product idea plus optional constraints. Output, inside an isolated run workspace: requirements, design, working source code, passing tests, a review report and documentation, produced by cooperating agents, observable live in a web UI, with metrics.

---

## 1. AGENT CORE
- Refactor the loop into a reusable `Agent` class configured by an `AgentSpec`: name, system prompt (loaded from `shadow/agents/prompts/<role>.md`), allowed tools, max steps, model override, temperature, token budget.
- Every agent ends by calling a `finish(summary, artifacts)` tool. The orchestrator validates it; if an expected artifact is missing or invalid, re-prompt the agent with the error (max 2 retries).
- LLM provider interface (`llm.py`) wrapping `google-genai` with retry and exponential backoff for 429 and 5xx, graceful handling of malformed tool calls, token usage captured per call, and a fake provider with scripted responses so the whole pipeline can be unit tested without the API.
- Preserve `thought_signature` handling. Add context management: token estimate per agent, and summarise or trim old tool outputs when over budget.
- The loop emits structured events (section 5) instead of printing. The CLI and the UI are both subscribers.

---

## 2. TOOLS (shared registry, per-role permissions)
- Filesystem: `read_file`, `write_file`, `edit_file` (must return an error if the old text is missing or not unique, and return a short diff on success), `list_files`, `glob_files`, `grep_search`.
- Shell: `run_command` (30s default timeout, configurable per call up to 120s, output truncated keeping head and tail), `run_tests` (runs pytest in the workspace and returns structured results: passed, failed, errors, failure message per test).
- Every path must resolve inside the run workspace (reject `../` traversal and symlink escapes). Keep the command blocklist but document it as defense in depth only. Run commands with `cwd` set to the workspace and a scrubbed environment (no API keys).
- Git helpers: init the workspace and commit a checkpoint after every stage so a stage can be rolled back.

---

## 3. ROLES (system prompts live in files; each states mission, inputs, outputs, rules and what not to do)
- **Analyst**: read, and write to `docs/` only. Produces `requirements.md` and `requirements.json`: user stories, functional and non-functional requirements, numbered acceptance criteria (AC-1, AC-2...), out-of-scope list, assumptions. Does not ask questions; states assumptions.
- **Architect**: read, and write to `docs/` only. Produces `design.md` and `design.json`: tech choices, file layout, module interfaces with signatures, data models, a Mermaid diagram, and a mapping from each requirement to a module.
- **Developer**: read, write, edit, search, run_command. Implements exactly the design under `src/` and must run the code at least once. Does not write tests.
- **Tester**: read, write to `tests/` only, run_tests. Writes tests derived from the acceptance criteria (not from reading the implementation), each tagged with its AC id, runs them, and writes `test_report.json`. Cannot edit `src/`.
- **Debugger**: read, edit `src/` only, search, run_command, run_tests. Receives the failing report, diagnoses the root cause, makes the smallest fix, re-runs. Cannot edit `tests/` (prevents weakening tests to pass). Records every fix in `debug_log.md` with cause and change.
- **Reviewer**: read and search only. Checks code against design and requirements, flags security and quality issues, produces `review.md` with a traceability matrix (AC to test to pass/fail).
- **Documenter**: read, and write to `README.md` and `docs/`. Produces README (install, usage, examples), module docs and a changelog, and verifies the instructions by actually running them.

---

## 4. ORCHESTRATOR
- Explicit state machine in `pipeline/orchestrator.py`, not decided by an LLM: `ANALYSIS`, `DESIGN`, `CODING`, `TESTING`, then (`DEBUGGING`, `TESTING`) repeated, `REVIEW`, `DOCS`, `DONE`, with `FAILED` and `CANCELLED`. Every transition is recorded.
- Shared state is the run directory: `runs/<run_id>/workspace/`, `artifacts/`, `events.jsonl`, `state.json`. Agents communicate only through artifacts (files) and pydantic-validated JSON schemas (`pipeline/schemas.py`).
- Feedback loop: Tester then Debugger then Tester, up to $N=4$ iterations (configurable). Loop guard: hash the failure signature (failing test names plus error types). If it is identical twice in a row, escalate once to the Developer with a re-plan prompt; if it still repeats, stop with `FAILED` and a clear report. Also detect an agent repeating the same tool call 3 times.
- Optional human-in-the-loop gates after requirements and after design (config and UI toggle). The human can approve, reject with feedback (fed back to the agent), or edit the artifact.
- Per-stage and per-run budgets for steps, tokens and wall time. Cancel support. Resume a failed run from the last completed stage.

---

## 5. EVENTS AND OBSERVABILITY
- Typed events: `run_started`, `stage_started`, `llm_call` (tokens, latency), `agent_message`, `tool_call`, `tool_result`, `file_changed` (path, diff), `artifact_created`, `test_result`, `approval_requested`, `approval_resolved`, `stage_finished`, `loop_detected`, `run_finished`, `error`.
- In-process event bus. Every event is appended to `runs/<id>/events.jsonl` and streamed to the UI.
- Per-run metrics: success, time per stage, tokens per stage, cost estimate, debug iterations, tool call counts, tests passed.

---

## 6. BACKEND API (FastAPI, started with python -m uvicorn)
- `POST /runs`, `GET /runs`, `GET /runs/{id}`, `POST /runs/{id}/cancel`, `POST /runs/{id}/approve` (decision, feedback), `GET /runs/{id}/events` (SSE with `Last-Event-ID` replay), `GET /runs/{id}/files` and `/files/{path}`, `GET /runs/{id}/artifacts`, `GET /runs/{id}/zip`, `GET /metrics/compare`.
- SQLite for the run index and metrics; files and events stay on disk. Runs execute in the background; one active run at a time is acceptable.

---

## 7. UI (a demo centerpiece)
- Stack: React + Vite + TypeScript + Tailwind, React Flow for the pipeline graph, Monaco for code and diffs, Recharts for charts. Fallback to a FastAPI-served static single-page app with identical screens if Node toolchain is constrained.
- Screens:
  - (a) Launch: idea box, example ideas, options (approval gates, max iterations, model).
  - (b) Run view: live pipeline graph with node states (idle, running, done, failed, waiting for approval), the Tester-Debugger loop drawn as a cycle with an iteration counter, event timeline, live agent panel streaming messages and collapsible tool calls, token and time counters.
  - (c) Artifacts: rendered requirements, design with Mermaid diagram, review, README.
  - (d) Code: file tree plus Monaco viewer, per-file diffs and which agent changed them.
  - (e) Tests: pass/fail list mapped to acceptance criteria, history across debug iterations.
  - (f) Approvals inline.
  - (g) History: past runs with status, duration, tokens.
  - (h) Compare: factory versus single-agent charts from eval results.
- Replay mode: the UI can replay a saved `events.jsonl` at adjustable speed, so the demo never depends on API quota or network.
- Polished: dark and light mode, responsive, empty, loading and error states, no placeholder content.

---

## 8. BASELINE AND EVALS
- Keep the original single-agent ShadowX runnable as a baseline mode over the same task format.
- `evals/tasks/*.yaml`: 8 tasks, each with an idea, hidden acceptance tests and a timeout. Examples: CLI todo app, URL shortener API, bank account library, markdown to HTML converter, rate limiter, expense tracker with SQLite, CSV cleaning and summary script, text-based game.
- `evals/run_evals.py` runs both modes $N$ times, grades with the hidden tests (not the agents' own tests), and writes results JSON plus a markdown table: success rate, debug iterations, tokens, time, tests passed.

---

## 9. QUALITY BAR
- pytest suite covering: tools (traversal, blocklist, truncation, edit edge cases), loop guard, state machine transitions, schema validation, orchestrator with the fake provider (happy path, fails-then-fixed path, never-fixed path), API endpoints.
- Type hints, ruff formatting, no dead code, consistent logging.
- README with architecture diagram and quickstart (Windows and generic), `.env.example`, `.gitignore` covering `.env`, `runs/`, `shadowx_history.json`, `node_modules`.
- `docs/adr/`: one short decision record per major choice (state-machine orchestrator versus LLM-routed, files as shared state, SSE versus WebSocket, role permissions, no frameworks).
- `docs/architecture.md` with Mermaid diagrams: system, sequence of a run, state machine, event flow.

---

## 10. WORKING RULES
- Before each task: write an implementation plan, list the files to create or change, and wait for my approval.
- Small commits. Never break the existing CLI. Run the tests before declaring anything done. If something is ambiguous, state the assumption and continue.
- After each day, report: what changed, how to run it, how to verify it, and three questions I should be able to answer about it.
