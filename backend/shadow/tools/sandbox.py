"""
sandbox.py — Path sandboxing and environment scrubbing for ShadowX tools.

Enforces workspace-root confinement:
- Rejects path traversal escapes (e.g. `../`, `..\\`).
- Rejects absolute paths outside the workspace root.
- Rejects symlink escapes.
- Scrubs sensitive environment variables (API keys, secrets) for subprocess execution.
"""

from __future__ import annotations
import os
from pathlib import Path
from typing import Union

# Sensitive environment variable patterns to strip before subprocess execution
SENSITIVE_ENV_PATTERNS = [
    "KEY",
    "SECRET",
    "TOKEN",
    "PASSWORD",
    "PASSWD",
    "AUTH",
    "CREDENTIAL",
    "BEARER",
    "PRIVATE",
]

# Explicit keys to never leak
EXPLICIT_BLOCKED_ENV = {
    "GEMINI_API_KEY",
    "GOOGLE_API_KEY",
    "OPENAI_API_KEY",
    "ANTHROPIC_API_KEY",
    "ANTHROPIC_AUTH_TOKEN",
    "AWS_SECRET_ACCESS_KEY",
    "AWS_ACCESS_KEY_ID",
    "AWS_SESSION_TOKEN",
    "GITHUB_TOKEN",
    "GH_TOKEN",
    "SLACK_BOT_TOKEN",
    "DATABASE_URL",
}


def resolve_workspace_path(path: Union[str, Path], workspace_root: Union[str, Path]) -> Path:
    """
    Safely resolve a path relative to the workspace root.

    Raises PermissionError if the target resolves outside the workspace, contains
    null bytes, or attempts symlink/junction escape.
    """
    path_str = str(path)
    if "\0" in path_str:
        raise PermissionError("Null byte injection detected in path")

    root = Path(workspace_root).resolve()
    raw_path = Path(path)

    if raw_path.is_absolute():
        resolved = raw_path.resolve()
    else:
        resolved = (root / raw_path).resolve()

    # Enforce confinement inside workspace_root
    try:
        resolved.relative_to(root)
    except ValueError:
        raise PermissionError(
            f"Path traversal detected: '{path}' resolves to '{resolved}' which is outside workspace '{root}'"
        )

    return resolved


def scrub_environment(extra_env: dict[str, str] | None = None) -> dict[str, str]:
    """
    Produce a sanitized copy of os.environ with secrets removed.

    Retains standard execution variables needed by Python, git, and shell.
    """
    clean_env: dict[str, str] = {}

    for k, v in os.environ.items():
        k_upper = k.upper()

        if k in EXPLICIT_BLOCKED_ENV:
            continue

        if any(pat in k_upper for pat in SENSITIVE_ENV_PATTERNS):
            continue

        clean_env[k] = v

    if extra_env:
        clean_env.update(extra_env)

    return clean_env
