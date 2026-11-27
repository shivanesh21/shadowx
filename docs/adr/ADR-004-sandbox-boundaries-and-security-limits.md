# ADR-004: Workspace Sandboxing Boundaries & Security Limits

## Status
Accepted

## Context
ShadowX Factory coordinates multiple autonomous agents that generate and execute software inside an isolated run workspace (`runs/<run_id>/workspace/`). During a run:
1. Agents read, write, and edit files across `docs/`, `src/`, and `tests/`.
2. Developer and Debugger agents execute shell commands (`run_command`) and test suites (`run_tests`).
3. External files (e.g. user ideas, third-party libraries, existing project files) may contain adversarial inputs, path traversal sequences, or prompt injection payloads.
4. Host environments frequently store valuable developer secrets (API keys for Gemini, OpenAI, GitHub, AWS).

We need an explicit decision on the sandboxing boundaries, credential protections, and rollback mechanisms, with honest documentation of what is protected in application code versus what requires OS-level virtualization.

## Decisions

### 1. In-Process Path Confinement (`resolve_workspace_path`)
- All filesystem tools must resolve targets relative to the run workspace root.
- All resolved paths are canonicalized via `Path.resolve()` and validated against `root` with `resolved.relative_to(root)`.
- Traversal sequences (`../`, `..\\`), absolute paths outside the workspace, null bytes (`\0`), and symlink escapes are strictly rejected with `PermissionError`.

### 2. Subprocess Environment Scrubbing (`scrub_environment`)
- When running shell commands or pytest, subprocesses must never inherit host API keys or credentials.
- `scrub_environment()` filters `os.environ` by stripping:
  - Explicit sensitive keys (`GEMINI_API_KEY`, `GOOGLE_API_KEY`, `OPENAI_API_KEY`, `ANTHROPIC_API_KEY`, `GITHUB_TOKEN`, `AWS_SECRET_ACCESS_KEY`, etc.).
  - Case-insensitive pattern substrings (`KEY`, `SECRET`, `TOKEN`, `PASSWORD`, `PASSWD`, `AUTH`, `CREDENTIAL`, `BEARER`, `PRIVATE`).
- Core system variables (`PATH`, `SYSTEMROOT`, `TEMP`, `TMP`, etc.) are preserved to maintain standard execution of Python, Git, and system compilers.

### 3. Role-Based Least Privilege Tool Allocation
- Tools are granted strictly according to role need:
  - **Analyst & Reviewer**: No command execution; read/write restricted to documentation.
  - **Tester**: Cannot edit `src/` (preventing weakening production code to force a pass).
  - **Debugger**: Cannot edit `tests/` (preventing weakening assertions to hide bugs).
  - **Developer**: Cannot edit `tests/`.

### 4. Git Checkpoint Snapshot & Rollback
- Each workspace is a local Git repository.
- After every stage transition, a commit checkpoint is recorded (`create_checkpoint`).
- The orchestrator supports `rollback_to_stage(stage)` using `git reset --hard <hash>` and `git clean -fd`, restoring the workspace to the exact state of that stage.

### 5. Honest Acknowledgment of Limits
- **Process Sandboxing**: Commands run under the host user account. Application-level path checking and environment scrubbing prevent accidental traversal and credential leakage, but child processes are not enclosed in a kernel namespace/cgroup sandbox (Docker/Firecracker).
- **Command Blocklists**: The shell blocklist (`rm -rf`, `format`, `shutdown`) is defense-in-depth against accidental model mistakes, not an exploit boundary.
- **Indirect Prompt Injection**: Delimiting file content in prompt context isolates data from instructions, but prompt injection cannot be 100% prevented by prompts alone; structural role tool permissions and human approval gates serve as the real safeguards.

## Consequences
- Clean, zero-dependency sandboxing that runs natively on Windows with Device Guard without needing administrative Docker or WSL2 setup.
- Safe execution where host API keys cannot be exfiltrated by generated code.
- Clear, honest security documentation for reviewers and evaluators.
