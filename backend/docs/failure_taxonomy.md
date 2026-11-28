# ShadowX Factory — Failure Taxonomy & Prompt Hardening Report

**Date Generated:** 2026-11-28 20:17:20  
**Total Runs Analyzed:** 11  
**Total Failure Events Observed:** 12  

---

## 1. Quantitative Failure Taxonomy

The table below classifies every observed failure across benchmark and operational runs into the four canonical categories specified in **AGENTS.md**:

| Category | Description | Count | Percentage | Primary Source |
|---|---|:---:|:---:|---|
| **SCHEMA_ERRORS** | Pydantic validation failures in generated artifacts (`docs/requirements.json`, `docs/design.json`, `test_report.json`) | **0** | 0.0% | Analyst / Architect / Tester output formatting |
| **LOOPS** | Repetitive tool calls (>=3 identical calls) or oscillation in the Tester ↔ Debugger feedback cycle | **0** | 0.0% | Agent retrying failed tool without changing parameters |
| **CONFLICTS** | Permission boundary violations (e.g. role writing outside permitted paths, attempts to weaken tests) | **0** | 0.0% | Tool permission check rejections |
| **DRIFT** | Veering from initial requirements, missing AC coverage, unrequested abstractions | **12** | 100.0% | Developer / Reviewer divergence from specifications |

---

## 2. Root Cause Analysis & Mitigations

### 2.1 Schema Errors (0 occurrences)
- **Root Cause**: LLMs occasionally omit required fields (e.g. `summary`, `project_name`, or `user_stories.role`) or output dictionaries instead of lists (e.g. `ac_mapping` keys must be lists of strings).
- **Hardened Mitigation**:
  1. Updated role prompts (`analyst.md`, `architect.md`, `tester.md`) with explicit, copy-paste schema definitions and negative constraints.
  2. Orchestrator enforces Pydantic re-prompting with exact validation error diffs (max 2 retries).

### 2.2 Loops (0 occurrences)
- **Root Cause**: When a bash command or pytest run fails, the agent repeats the exact same call hoping for a different outcome.
- **Hardened Mitigation**:
  1. Loop Guard in `orchestrator.py` hashes the failure signature (test names + error types).
  2. If identical twice in a row, escalates once to the Developer with a re-plan prompt.
  3. Strict anti-loop instruction added to role prompts: *"Never repeat the exact same tool call with identical arguments 3 times. If a command fails, inspect the error and adjust your strategy."*

### 2.3 Conflicts (0 occurrences)
- **Root Cause**: Agents trying to write files outside their designated role permissions (e.g. Analyst writing code in `src/`, Debugger trying to edit `tests/` to make tests pass).
- **Hardened Mitigation**:
  1. `ToolRegistry` strictly scopes filesystem permissions per role.
  2. Prompt system instructions explicitly declare:
     - Analyst: ONLY `docs/`
     - Architect: ONLY `docs/`
     - Developer: ONLY `src/` (cannot touch `tests/`)
     - Tester: ONLY `tests/` and `test_report.json` (cannot touch `src/`)
     - Debugger: ONLY `src/` (CANNOT touch `tests/` — strictly forbidden to weaken tests)

### 2.4 Drift (12 occurrences)
- **Root Cause**: Developer introducing unexpected abstractions or failing to implement numbered criteria (AC-1, AC-2...).
- **Hardened Mitigation**:
  1. Numbered acceptance criteria format enforced throughout the SDLC (`AC-1`, `AC-2`...).
  2. Reviewer produces a formal Requirements Traceability Matrix linking every AC to its test and implementation module.
  3. Documenter verifies usage commands via live `run_command` before concluding.

---

## 3. Representative Occurrence Samples

| Run ID | Category | Stage / Agent | Message Sample |
|---|---|---|---|
| `run_0aad8bc0` | `DRIFT` | `Orchestrator` | Analyst artifact validation attempt 1 failed: docs/requirements.md was not created or is e... |
| `run_0aad8bc0` | `DRIFT` | `Orchestrator` | Analyst artifact validation attempt 2 failed: docs/requirements.md was not created or is e... |
| `run_0aad8bc0` | `DRIFT` | `Orchestrator` | Analyst stage failed after 3 attempts: docs/requirements.md was not created or is empty. d... |
| `run_0aad8bc0` | `DRIFT` | `FAILED` | docs/requirements.md was not created or is empty. docs/requirements.json was not created.... |
| `run_87c2182c` | `DRIFT` | `Orchestrator` | Analyst artifact validation attempt 1 failed: docs/requirements.md was not created or is e... |
| `run_87c2182c` | `DRIFT` | `Orchestrator` | Analyst artifact validation attempt 2 failed: docs/requirements.md was not created or is e... |
| `run_87c2182c` | `DRIFT` | `Orchestrator` | Analyst stage failed after 3 attempts: docs/requirements.md was not created or is empty. d... |
| `run_87c2182c` | `DRIFT` | `FAILED` | docs/requirements.md was not created or is empty. docs/requirements.json was not created.... |
| `run_9b54e159` | `DRIFT` | `Orchestrator` | Analyst artifact validation attempt 1 failed: docs/requirements.md was not created or is e... |
| `run_9b54e159` | `DRIFT` | `Orchestrator` | Analyst artifact validation attempt 2 failed: docs/requirements.md was not created or is e... |
| `run_9b54e159` | `DRIFT` | `Orchestrator` | Analyst stage failed after 3 attempts: docs/requirements.md was not created or is empty. d... |
| `run_9b54e159` | `DRIFT` | `FAILED` | docs/requirements.md was not created or is empty. docs/requirements.json was not created.... |
