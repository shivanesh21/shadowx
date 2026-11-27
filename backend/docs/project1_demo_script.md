# Project 1 Walkthrough & Video Demonstration Script

**Title**: ShadowX Factory — Hardened Core, Tool Sandboxing & Event Bus Architecture  
**Duration**: 3 – 5 minutes  
**Presenter**: Shivanesh  
**Objective**: Demonstrate how ShadowX operates as an autonomous, sandboxed, and observable coding agent ready for multi-agent pipeline orchestration.

---

## Act 1: The Vision & Problem Statement (0:00 – 0:45)
- **Visual**: Start with the terminal open showing the ShadowX ASCII banner.
- **Narrative**:
  > *"Hi everyone, this is ShadowX Factory — an agentic software development environment. In traditional AI coding agents, agents are built as monolithic scripts with unrestricted shell access, fragile string replacements, and direct console printing. For enterprise and multi-agent factory workflows, this is unsafe, non-deterministic, and impossible to observe in production. Today, I'm showcasing Project 1: our hardened agent core, workspace-root sandboxing, role-based tool registry, and decoupled event-driven architecture."*

---

## Act 2: Tool Sandboxing & Defense-in-Depth (0:45 – 1:45)
- **Visual**: Run unit test command in terminal:
  ```bash
  python -m pytest tests/test_tools.py -k "traversal or scrub" -v
  ```
- **Narrative**:
  > *"First, security. ShadowX implements strict workspace confinement. All file paths are validated against the workspace root with `resolve_workspace_path`, catching and rejecting any path traversal (`../`) or symlink escapes before any disk operation occurs.
  > Furthermore, when the agent invokes commands using `run_command`, we execute inside an isolated subprocess with a scrubbed environment that removes sensitive API keys like `GEMINI_API_KEY` so credentials can never be leaked or exfiltrated."*

---

## Act 3: Surgical Editing & Structured Testing (1:45 – 2:45)
- **Visual**: Run tests demonstrating uniqueness validation and pytest parsing:
  ```bash
  python -m pytest tests/test_tools.py -k "edit_file or run_tests" -v
  ```
- **Narrative**:
  > *"Next, surgical precision in tools. One of the biggest failure modes of LLMs is corrupting code during edits. Our `edit_file` tool requires strict 1-occurrence uniqueness. If a target text appears zero times or more than once, it halts and gives the model clear guidance to add surrounding context lines. On success, it generates a real unified diff.
  > We've also built `run_tests`, a structured test runner that executes pytest and parses passed, failed, and error counts into a structured data model, emitting `TestResultEvent` directly to our pipeline."*

---

## Act 4: Event Bus & Decoupled Observability (2:45 – 3:45)
- **Visual**: Launch ShadowX CLI in one-shot mode or interactive mode:
  ```bash
  python -m shadow.cli --help
  python -m pytest tests/ -v
  ```
- **Narrative**:
  > *"Finally, notice how clean the architecture is. The agent ReAct loop never calls `print()` or accesses the console. Instead, it emits typed events over an in-process `EventBus`—from `RunStarted`, to `ToolCallEvent`, `ToolResultEvent`, and `FileChanged`.
  > The terminal UI you see is merely a subscriber to this stream, and every single event is concurrently recorded to `events.jsonl` for replay, auditing, and real-time streaming to our upcoming React web dashboard.
  > All 27 tests across the core, events, LLM abstraction, and tools pass with 100% green status. ShadowX is now ready for multi-agent pipeline orchestration!"*
