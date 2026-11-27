"""
testing.py — Structured test runner for ShadowX Factory.

Executes pytest within the workspace and extracts:
- Total passed, failed, errors
- Failure diagnostics per test
- Emits TestResultEvent to EventBus
"""

from __future__ import annotations
import re
import subprocess
import sys
from pathlib import Path
from typing import Optional, Union, Any

from shadow.tools.sandbox import resolve_workspace_path, scrub_environment
from shadow.core.events import TestResultEvent
from shadow.core.event_bus import EventBus


def run_tests(
    test_path: str = "tests",
    workspace_root: Union[str, Path] = ".",
    event_bus: Optional[EventBus] = None,
    run_id: str = "default",
    timeout: int = 60,
    **kwargs: Any,
) -> str:
    """
    Run pytest inside the workspace root and return structured results.
    """
    root = Path(workspace_root).resolve()
    target_path = resolve_workspace_path(test_path, root)

    cmd = [sys.executable, "-m", "pytest", str(target_path), "-v", "--tb=short"]
    clean_env = scrub_environment()

    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            cwd=str(root),
            env=clean_env,
            timeout=timeout,
        )
        output = (result.stdout or "") + (result.stderr or "")

        # Parse test metrics from pytest output
        passed = 0
        failed = 0
        errors = 0

        # Regex matches e.g. "2 passed, 1 failed, 1 error in 0.45s"
        summary_match = re.search(r"=+\s*(.*?)\s*in\s+[\d\.]+s\s*=+", output)
        summary_line = summary_match.group(1) if summary_match else ""

        p_match = re.search(r"(\d+)\s+passed", summary_line)
        if p_match:
            passed = int(p_match.group(1))

        f_match = re.search(r"(\d+)\s+failed", summary_line)
        if f_match:
            failed = int(f_match.group(1))

        e_match = re.search(r"(\d+)\s+error", summary_line)
        if e_match:
            errors = int(e_match.group(1))

        # Extract failed test names
        failures: dict[str, str] = {}
        failure_blocks = re.findall(r"_{3,}\s*(.*?)\s*_{3,}(.*?)(?=\n_{3,}|\n={3,}|\Z)", output, re.DOTALL)
        for name, trace in failure_blocks:
            failures[name.strip()] = trace.strip()[:500]

        details = {
            "summary": summary_line or "Test execution complete",
            "failures": failures,
            "exit_code": result.returncode,
        }

        if event_bus:
            event_bus.emit(
                TestResultEvent(
                    run_id=run_id,
                    passed=passed,
                    failed=failed,
                    errors=errors,
                    details=details,
                )
            )

        status_msg = (
            f"TEST RUN RESULT: {'PASSED' if result.returncode == 0 else 'FAILED'}\n"
            f"Passed: {passed} | Failed: {failed} | Errors: {errors}\n\n"
        )

        if failures:
            status_msg += "FAILURES:\n"
            for test_name, reason in failures.items():
                status_msg += f"- {test_name}:\n{reason}\n\n"

        return status_msg + f"Full Output:\n{output[:3000]}"
    except subprocess.TimeoutExpired:
        return f"ERROR: Test runner timed out after {timeout} seconds."
    except Exception as e:
        return f"ERROR running tests: {e}"
