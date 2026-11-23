# Project 1 Technical Report: Hardened Autonomous Agent Core & Event-Driven Engine

**Author**: Shivanesh  
**Project**: ShadowX Factory (Phase 1 / Project 1 Milestone)  
**Date**: November 2026  
**Status**: Completed & Verified  

---

## 1. Executive Summary
ShadowX has been transitioned from a single-file prototype into an enterprise-grade, spec-driven autonomous agent engine. This milestone establishes:
1. **Workspace Sandboxing & Defense-in-Depth**: Strict confinement of all file operations inside a designated root, complete rejection of path traversal (`../`) and symlink attacks, and automated environment scrubbing to prevent credential leakage.
2. **Surgical Tooling**: Zero-hallucination file edits via strict 1-occurrence uniqueness validation with unified diff emission; structured test execution (`run_tests`) translating raw `pytest` output into actionable pass/fail metrics.
3. **Role-Based Access Control (RBAC)**: A centralized `ToolRegistry` enforcing the principle of least privilege across specialized software factory roles (`Analyst`, `Architect`, `Developer`, `Tester`, `Debugger`, `Reviewer`, `Documenter`).
4. **Decoupled Event-Driven Architecture**: Total separation of agent reasoning from UI rendering. All actions stream across an in-process `EventBus` into persistent `events.jsonl` audit logs, while the CLI renders purely as a subscriber.

---

## 2. Architecture & Design Decisions

### 2.1 The Decoupled Event-Driven ReAct Loop
Traditional AI terminal agents tightly couple LLM calls with direct terminal printing (`print()` statements inside tool functions). This creates brittle code that cannot be reused in headless environments, web servers, or multi-agent pipelines.

ShadowX implements an in-process `EventBus`. The `Agent` engine and `ToolRegistry` emit strongly-typed dataclass events (`RunStarted`, `LLMCallEvent`, `ToolCallEvent`, `ToolResultEvent`, `FileChanged`, `TestResultEvent`, `StageFinished`). The terminal UI (`CLIEventRenderer`) and the persistent JSONL audit logger (`events.jsonl`) are independent subscribers.

```
+--------------------+        +---------------------+        +--------------------+
|  Agent Loop        | -----> |      EventBus       | -----> |  events.jsonl      |
|  (shadow.core)     |        |                     |        |  (Disk Audit Log)  |
+--------------------+        +----------+----------+        +--------------------+
          |                              |
          v                              v
+--------------------+        +---------------------+
|  ToolRegistry      |        |  CLI Event Renderer |
|  (Sandboxed Tools) |        |  (Rich Terminal UI) |
+--------------------+        +---------------------+
```

### 2.2 Workspace Sandboxing & Threat Model
Autonomous agents capable of executing shell commands and writing files introduce severe security risks:
- **Directory Traversal**: Relative path escapes (`../../.ssh/authorized_keys`, `..\\Windows\\System32`).
- **Absolute Path Breakouts**: Passing absolute paths to overwrite host system binaries.
- **Credential Harvesting**: Shell subprocesses inheriting sensitive API keys (`GEMINI_API_KEY`, tokens).

**Mitigation Implemented**:
- `resolve_workspace_path`: All filesystem tools resolve paths strictly against `workspace_root.resolve()` and verify `resolved.relative_to(root)`. Any escape immediately raises `PermissionError` and reports an error back to the agent without modifying disk.
- `scrub_environment`: Subprocess execution scrubs `os.environ`, stripping tokens matching sensitive keywords (`KEY`, `SECRET`, `TOKEN`, `AUTH`, `CREDENTIAL`).

### 2.3 Surgical `edit_file` with Uniqueness Validation
A frequent failure mode in LLM code modification is replacing ambiguous text. If `old_text` appears multiple times, naïve replacements modify the wrong function or create syntax errors.

ShadowX enforces:
1. `count == 0`: Fails with `ERROR: old_text not found in <path>`.
2. `count > 1`: Fails with `ERROR: old_text is not unique in <path> (found N occurrences). Include more surrounding context lines.`
3. `count == 1`: Performs replacement, calculates standard unified diff using `difflib.unified_diff`, writes to disk, emits `FileChanged`, and returns the diff to the model for visual verification.

---

## 3. Role-Based Access Control (RBAC) Matrix

To prevent agents from modifying unintended files or corrupting evaluation results, the `ToolRegistry` restricts tools and filesystem paths per role:

| Role | Allowed Tools | Filesystem Write Boundaries | Blocked Write Boundaries |
|---|---|---|---|
| **Analyst** | `read_file`, `write_file`, `list_files`, `glob_files`, `grep_search` | `docs/` | `src/`, `tests/` |
| **Architect** | `read_file`, `write_file`, `list_files`, `glob_files`, `grep_search` | `docs/` | `src/`, `tests/` |
| **Developer** | `read`, `write`, `edit`, `list`, `glob`, `grep`, `run_command` | `src/`, root config | `tests/` (cannot write tests) |
| **Tester** | `read`, `write`, `list`, `glob`, `grep`, `run_tests` | `tests/` only | `src/` (cannot modify code) |
| **Debugger** | `read`, `edit`, `list`, `glob`, `grep`, `run_command`, `run_tests` | `src/`, `debug_log.md` | `tests/` (cannot weaken tests) |
| **Reviewer** | `read_file`, `list_files`, `glob_files`, `grep_search` | `docs/review.md` | All code files |
| **Documenter** | `read`, `write`, `edit`, `list`, `glob`, `grep`, `run_command` | `README.md`, `docs/` | `src/`, `tests/` |
| **CLI / Default** | Full Toolset (8 tools) | Workspace Root | Traversal Escapes |

---

## 4. Verification & Testing

The milestone is validated with a dedicated automated test suite in `tests/`:
- `tests/test_tools.py`: 19 unit tests validating path traversal rejection, symlink guards, environment scrubbing, `edit_file` uniqueness errors, unified diffs, `glob_files`, `grep_search`, shell timeouts, blocklist enforcement, and RBAC role boundaries.
- `tests/test_agent_core.py`: 3 unit tests verifying ReAct loop execution, token budgeting, role constraints, and `finish()` handoffs.
- `tests/test_events.py`: 3 unit tests validating event serialization, publisher-subscriber routing, and `events.jsonl` streaming.
- `tests/test_llm_provider.py`: 2 unit tests verifying offline mock generation and simulated retry logic.

**Test Execution Result**:
```
27 passed, 1 warning in 5.13s (100% green)
```

---

## 5. Architectural Defense Questions & Answers

### Q1: Why did you decouple event emission from UI rendering instead of logging in tool functions?
**Answer**: In an Agentic Software Factory, the consumer of agent actions changes depending on the execution context. In terminal mode, it's a Rich CLI; in production, it's a Server-Sent Events (SSE) stream to a React frontend; in headless evals, it's a JSONL file. By routing all agent decisions and tool outputs through a typed `EventBus`, the core ReAct loop remains 100% pure and reusable, enabling plug-and-play UI adapters without touching agent logic.

### Q2: Why is strict uniqueness enforced in `edit_file` instead of using fuzzy matching or multi-replace?
**Answer**: Autonomous agents often experience hallucinations when modifying large source files if line numbers shift or variable names repeat. Multi-replace risks corrupting unrelated methods. Strict 1-occurrence enforcement forces the agent to provide sufficient surrounding lines as context, ensuring deterministic replacements. If the snippet is ambiguous, the tool immediately provides feedback prompting the agent to expand its context window rather than corrupting the file.

### Q3: How does the tool sandboxing prevent prompt injection from compromising the host?
**Answer**: Defense in depth. First, `resolve_workspace_path` strictly binds file I/O to the workspace directory tree, preventing directory traversal escapes (`../`). Second, `run_command` scrubs the process environment, ensuring sensitive API keys and secrets cannot be exfiltrated via outbound curl commands or environment dumping. Third, execution timeouts and a command blocklist prevent common sabotage vectors such as fork bombs or disk formatting.
