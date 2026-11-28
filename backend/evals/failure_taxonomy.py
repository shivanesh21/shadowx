"""
failure_taxonomy.py — Automated Failure Taxonomy Analyzer for ShadowX Factory.

Analyzes execution logs across runs and categorizes failure modes into four formal classes:
  1. SCHEMA_ERRORS — Pydantic validation failures in artifacts (requirements.json, design.json, test_report.json)
  2. LOOPS — Repetitive tool calls (>= 3 identical calls) or oscillation between stages
  3. CONFLICTS — Role permission boundary violations (e.g. Analyst writing outside docs/)
  4. DRIFT — Veering from acceptance criteria, missing AC mappings, or unrequested abstractions

Outputs quantitative counts and generates backend/docs/failure_taxonomy.md.
"""

from __future__ import annotations
import os
import re
import sys
import json
import time
from pathlib import Path
from dataclasses import dataclass, field, asdict
from typing import Optional, Any

from rich.console import Console
from rich.table import Table
from rich.panel import Panel

_here = Path(__file__).resolve().parent
_backend_root = _here.parent
if str(_backend_root) not in sys.path:
    sys.path.insert(0, str(_backend_root))

console = Console()
DEFAULT_RUNS_DIR = _backend_root / "runs"
DEFAULT_OUTPUT_MD = _backend_root / "docs" / "failure_taxonomy.md"


@dataclass
class FailureOccurrence:
    category: str
    run_id: str
    agent_name: Optional[str]
    stage: Optional[str]
    message: str
    timestamp: float = 0.0


@dataclass
class TaxonomyReport:
    total_runs_analyzed: int = 0
    total_failures: int = 0
    counts: dict[str, int] = field(default_factory=lambda: {
        "SCHEMA_ERRORS": 0,
        "LOOPS": 0,
        "CONFLICTS": 0,
        "DRIFT": 0,
    })
    occurrences: list[FailureOccurrence] = field(default_factory=list)


# Pattern signatures for each taxonomy category
PATTERNS = {
    "SCHEMA_ERRORS": [
        re.compile(r"validation\s*error", re.IGNORECASE),
        re.compile(r"schema validation failed", re.IGNORECASE),
        re.compile(r"field required", re.IGNORECASE),
        re.compile(r"missing field", re.IGNORECASE),
        re.compile(r"input should be a valid", re.IGNORECASE),
        re.compile(r"jsondecodeerror", re.IGNORECASE),
        re.compile(r"invalid json", re.IGNORECASE),
    ],
    "LOOPS": [
        re.compile(r"loop detected", re.IGNORECASE),
        re.compile(r"repeating.*tool call", re.IGNORECASE),
        re.compile(r"identical tool call", re.IGNORECASE),
        re.compile(r"repeated.*times", re.IGNORECASE),
        re.compile(r"loop_detected", re.IGNORECASE),
    ],
    "CONFLICTS": [
        re.compile(r"is not allowed to modify", re.IGNORECASE),
        re.compile(r"not permitted for role", re.IGNORECASE),
        re.compile(r"permission boundary", re.IGNORECASE),
        re.compile(r"cannot edit tests", re.IGNORECASE),
        re.compile(r"path traversal not allowed", re.IGNORECASE),
        re.compile(r"access denied", re.IGNORECASE),
    ],
    "DRIFT": [
        re.compile(r"missing acceptance criteria", re.IGNORECASE),
        re.compile(r"unmapped", re.IGNORECASE),
        re.compile(r"traceability.*missing", re.IGNORECASE),
        re.compile(r"failed to meet requirement", re.IGNORECASE),
        re.compile(r"drift", re.IGNORECASE),
        re.compile(r"test failures in iteration", re.IGNORECASE),
    ],
}


def classify_message(text: str) -> Optional[str]:
    """Classify an error message into one of the four taxonomy categories."""
    if not text:
        return None
    for category, regex_list in PATTERNS.items():
        for regex in regex_list:
            if regex.search(text):
                return category
    return None


def analyze_run_directory(run_dir: Path) -> list[FailureOccurrence]:
    """Scan a single run directory for failure occurrences across events and state."""
    occurrences: list[FailureOccurrence] = []
    run_id = run_dir.name

    events_file = run_dir / "events.jsonl"
    if events_file.exists():
        tool_call_history: list[tuple[str, str]] = []  # (tool_name, arg_str)

        for line in events_file.read_text(encoding="utf-8", errors="replace").splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                ev = json.loads(line)
            except Exception:
                continue

            event_type = ev.get("event_type", "")
            agent = ev.get("agent_name", "")
            stage = ev.get("stage", "")
            ts = float(ev.get("timestamp", 0.0))

            # Check explicit loop events
            if event_type == "loop_detected":
                occurrences.append(FailureOccurrence(
                    category="LOOPS",
                    run_id=run_id,
                    agent_name=agent,
                    stage=stage,
                    message=f"Loop guard triggered: {ev.get('tool_name')} repeated {ev.get('count')} times",
                    timestamp=ts,
                ))

            # Detect consecutive repetitive tool calls
            elif event_type == "tool_call":
                t_name = ev.get("tool_name", "")
                t_args = json.dumps(ev.get("arguments", {}), sort_keys=True)
                tool_call_history.append((t_name, t_args))
                if len(tool_call_history) >= 3:
                    last_three = tool_call_history[-3:]
                    if last_three[0] == last_three[1] == last_three[2]:
                        occurrences.append(FailureOccurrence(
                            category="LOOPS",
                            run_id=run_id,
                            agent_name=agent,
                            stage=stage,
                            message=f"Agent repeated tool call '{t_name}' 3 consecutive times",
                            timestamp=ts,
                        ))

            # Check tool results for errors (permission conflicts, etc.)
            elif event_type == "tool_result":
                if ev.get("is_error") or "ERROR" in str(ev.get("result", "")):
                    res_str = str(ev.get("result", ""))
                    cat = classify_message(res_str)
                    if cat:
                        occurrences.append(FailureOccurrence(
                            category=cat,
                            run_id=run_id,
                            agent_name=agent,
                            stage=stage,
                            message=res_str[:250],
                            timestamp=ts,
                        ))

            # Check error events
            elif event_type == "error":
                msg = ev.get("message", "")
                cat = classify_message(msg) or "DRIFT"
                occurrences.append(FailureOccurrence(
                    category=cat,
                    run_id=run_id,
                    agent_name=agent,
                    stage=stage,
                    message=msg[:250],
                    timestamp=ts,
                ))

    # Also inspect state.json for terminal failure reasons
    state_file = run_dir / "state.json"
    if state_file.exists():
        try:
            state = json.loads(state_file.read_text(encoding="utf-8", errors="replace"))
            for h in state.get("history", []):
                details = h.get("details", {})
                reason = details.get("reason", "")
                if reason:
                    cat = classify_message(reason) or "DRIFT"
                    occurrences.append(FailureOccurrence(
                        category=cat,
                        run_id=run_id,
                        agent_name=None,
                        stage=h.get("to", ""),
                        message=reason[:250],
                        timestamp=h.get("timestamp", 0.0),
                    ))
        except Exception:
            pass

    return occurrences


def analyze_failure_taxonomy(runs_dir: Path = DEFAULT_RUNS_DIR) -> TaxonomyReport:
    """Scan all runs under runs_dir and compile full TaxonomyReport."""
    report = TaxonomyReport()
    if not runs_dir.exists():
        return report

    candidate_dirs: list[Path] = []
    # Direct runs
    for p in runs_dir.iterdir():
        if p.is_dir() and (p / "state.json").exists():
            candidate_dirs.append(p)
    # Evals subdirectory
    evals_sub = runs_dir / "evals"
    if evals_sub.exists():
        for p in evals_sub.iterdir():
            if p.is_dir() and (p / "state.json").exists():
                candidate_dirs.append(p)

    report.total_runs_analyzed = len(candidate_dirs)

    for r_dir in candidate_dirs:
        occs = analyze_run_directory(r_dir)
        for occ in occs:
            report.counts[occ.category] = report.counts.get(occ.category, 0) + 1
            report.occurrences.append(occ)

    report.total_failures = len(report.occurrences)
    return report


def generate_taxonomy_markdown(report: TaxonomyReport, output_file: Path = DEFAULT_OUTPUT_MD) -> str:
    """Generate comprehensive documentation of the failure taxonomy and mitigations."""
    output_file.parent.mkdir(parents=True, exist_ok=True)
    total = max(report.total_failures, 1)

    pct_schema = (report.counts.get("SCHEMA_ERRORS", 0) / total) * 100
    pct_loops = (report.counts.get("LOOPS", 0) / total) * 100
    pct_conflicts = (report.counts.get("CONFLICTS", 0) / total) * 100
    pct_drift = (report.counts.get("DRIFT", 0) / total) * 100

    content = f"""# ShadowX Factory — Failure Taxonomy & Prompt Hardening Report

**Date Generated:** {time.strftime('%Y-%m-%d %H:%M:%S')}  
**Total Runs Analyzed:** {report.total_runs_analyzed}  
**Total Failure Events Observed:** {report.total_failures}  

---

## 1. Quantitative Failure Taxonomy

The table below classifies every observed failure across benchmark and operational runs into the four canonical categories specified in **AGENTS.md**:

| Category | Description | Count | Percentage | Primary Source |
|---|---|:---:|:---:|---|
| **SCHEMA_ERRORS** | Pydantic validation failures in generated artifacts (`docs/requirements.json`, `docs/design.json`, `test_report.json`) | **{report.counts.get('SCHEMA_ERRORS', 0)}** | {pct_schema:.1f}% | Analyst / Architect / Tester output formatting |
| **LOOPS** | Repetitive tool calls (>=3 identical calls) or oscillation in the Tester ↔ Debugger feedback cycle | **{report.counts.get('LOOPS', 0)}** | {pct_loops:.1f}% | Agent retrying failed tool without changing parameters |
| **CONFLICTS** | Permission boundary violations (e.g. role writing outside permitted paths, attempts to weaken tests) | **{report.counts.get('CONFLICTS', 0)}** | {pct_conflicts:.1f}% | Tool permission check rejections |
| **DRIFT** | Veering from initial requirements, missing AC coverage, unrequested abstractions | **{report.counts.get('DRIFT', 0)}** | {pct_drift:.1f}% | Developer / Reviewer divergence from specifications |

---

## 2. Root Cause Analysis & Mitigations

### 2.1 Schema Errors ({report.counts.get('SCHEMA_ERRORS', 0)} occurrences)
- **Root Cause**: LLMs occasionally omit required fields (e.g. `summary`, `project_name`, or `user_stories.role`) or output dictionaries instead of lists (e.g. `ac_mapping` keys must be lists of strings).
- **Hardened Mitigation**:
  1. Updated role prompts (`analyst.md`, `architect.md`, `tester.md`) with explicit, copy-paste schema definitions and negative constraints.
  2. Orchestrator enforces Pydantic re-prompting with exact validation error diffs (max 2 retries).

### 2.2 Loops ({report.counts.get('LOOPS', 0)} occurrences)
- **Root Cause**: When a bash command or pytest run fails, the agent repeats the exact same call hoping for a different outcome.
- **Hardened Mitigation**:
  1. Loop Guard in `orchestrator.py` hashes the failure signature (test names + error types).
  2. If identical twice in a row, escalates once to the Developer with a re-plan prompt.
  3. Strict anti-loop instruction added to role prompts: *"Never repeat the exact same tool call with identical arguments 3 times. If a command fails, inspect the error and adjust your strategy."*

### 2.3 Conflicts ({report.counts.get('CONFLICTS', 0)} occurrences)
- **Root Cause**: Agents trying to write files outside their designated role permissions (e.g. Analyst writing code in `src/`, Debugger trying to edit `tests/` to make tests pass).
- **Hardened Mitigation**:
  1. `ToolRegistry` strictly scopes filesystem permissions per role.
  2. Prompt system instructions explicitly declare:
     - Analyst: ONLY `docs/`
     - Architect: ONLY `docs/`
     - Developer: ONLY `src/` (cannot touch `tests/`)
     - Tester: ONLY `tests/` and `test_report.json` (cannot touch `src/`)
     - Debugger: ONLY `src/` (CANNOT touch `tests/` — strictly forbidden to weaken tests)

### 2.4 Drift ({report.counts.get('DRIFT', 0)} occurrences)
- **Root Cause**: Developer introducing unexpected abstractions or failing to implement numbered criteria (AC-1, AC-2...).
- **Hardened Mitigation**:
  1. Numbered acceptance criteria format enforced throughout the SDLC (`AC-1`, `AC-2`...).
  2. Reviewer produces a formal Requirements Traceability Matrix linking every AC to its test and implementation module.
  3. Documenter verifies usage commands via live `run_command` before concluding.

---

## 3. Representative Occurrence Samples

"""
    if not report.occurrences:
        content += "_No failure events recorded in current run directories._\n"
    else:
        content += "| Run ID | Category | Stage / Agent | Message Sample |\n"
        content += "|---|---|---|---|\n"
        for occ in report.occurrences[:15]:
            safe_msg = occ.message.replace("\n", " ").replace("|", "/")[:90]
            agent_str = occ.agent_name or occ.stage or "Orchestrator"
            content += f"| `{occ.run_id[:16]}` | `{occ.category}` | `{agent_str}` | {safe_msg}... |\n"

    output_file.write_text(content, encoding="utf-8")
    return content


def main() -> None:
    report = analyze_failure_taxonomy(DEFAULT_RUNS_DIR)
    md_content = generate_taxonomy_markdown(report, DEFAULT_OUTPUT_MD)

    table = Table(title="ShadowX Factory — Failure Taxonomy Summary")
    table.add_column("Category", style="bold cyan")
    table.add_column("Count", justify="right", style="yellow")
    table.add_column("Percentage", justify="right", style="green")

    total = max(report.total_failures, 1)
    for cat in ["SCHEMA_ERRORS", "LOOPS", "CONFLICTS", "DRIFT"]:
        cnt = report.counts.get(cat, 0)
        pct = (cnt / total) * 100
        table.add_row(cat, str(cnt), f"{pct:.1f}%")

    console.print("\n")
    console.print(table)
    console.print(f"\n[green]Taxonomy report written to:[/green] {DEFAULT_OUTPUT_MD}")


if __name__ == "__main__":
    main()
