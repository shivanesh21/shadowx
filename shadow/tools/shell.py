"""
shell.py — Sandboxed command execution for ShadowX Factory.

Features:
- Configurable timeout (1s to 120s, default 30s).
- Working directory bound strictly to workspace root.
- Environment scrubbing (API keys, secrets stripped).
- Output truncation preserving both head and tail.
- Command blocklist retained as defense in depth.
"""

from __future__ import annotations
import subprocess
from pathlib import Path
from typing import Union, Any

from shadow.tools.sandbox import scrub_environment

# Safety blocklist: commands rejected regardless of prompt
BLOCKED_COMMANDS = [
    "rm -rf",
    "rmdir /s",
    "format",
    "shutdown",
    "del /f",
    "rd /s",
    "mkfs",
    ":(){:|:&};:",   # fork bomb
]

MAX_SHELL_OUTPUT_LEN = 6000


def _truncate_head_tail(text: str, max_len: int = MAX_SHELL_OUTPUT_LEN) -> str:
    """Preserve beginning and end of stdout/stderr."""
    if len(text) <= max_len:
        return text
    half = max_len // 2
    return (
        text[:half]
        + f"\n\n... [output truncated ({len(text)} chars total, showing head & tail)] ...\n\n"
        + text[-half:]
    )


def run_command(
    command: str,
    timeout: int = 30,
    workspace_root: Union[str, Path] = ".",
    **kwargs: Any,
) -> str:
    """
    Execute a shell command inside the workspace directory with scrubbed environment.
    """
    # 1. Blocklist check
    lower = command.lower()
    for bad in BLOCKED_COMMANDS:
        if bad in lower:
            return f"BLOCKED: Command contains dangerous token '{bad}'."

    # 2. Timeout clamping (1s - 120s)
    timeout_clamped = max(1, min(int(timeout or 30), 120))

    # 3. Workspace root
    root = Path(workspace_root).resolve()
    if not root.exists():
        root.mkdir(parents=True, exist_ok=True)

    # 4. Environment
    clean_env = scrub_environment()

    try:
        result = subprocess.run(
            command,
            shell=True,
            capture_output=True,
            text=True,
            cwd=str(root),
            env=clean_env,
            timeout=timeout_clamped,
        )
        combined = (result.stdout or "") + (result.stderr or "")
        output = combined.strip() or "(no output)"
        if result.returncode != 0:
            return f"EXIT CODE: {result.returncode}\n\n{_truncate_head_tail(output)}"
        return _truncate_head_tail(output)
    except subprocess.TimeoutExpired:
        return f"ERROR: Command timed out after {timeout_clamped} seconds."
    except Exception as e:
        return f"ERROR running command: {e}"
