"""
tools.py — Backward-compatibility layer for existing ShadowX imports.

Routes directly to the hardened implementations in shadow/tools/.
"""

from __future__ import annotations
from typing import Any

from shadow.tools.sandbox import resolve_workspace_path, scrub_environment
from shadow.tools.filesystem import (
    read_file as _read_file,
    write_file as _write_file,
    edit_file as _edit_file,
    list_files as _list_files,
    glob_files as _glob_files,
    grep_search as _grep_search,
)
from shadow.tools.shell import run_command as _run_command, BLOCKED_COMMANDS
from shadow.tools.testing import run_tests as _run_tests
from shadow.tools.registry import ALL_TOOL_DECLARATIONS, ToolRegistry

MAX_OUTPUT_LEN = 5000

# Backward compatibility functions
def read_file(path: str, **kwargs: Any) -> str:
    return _read_file(path, **kwargs)

def write_file(path: str, content: str, skip_confirm: bool = False, **kwargs: Any) -> str:
    return _write_file(path, content, **kwargs)

def edit_file(path: str, old_text: str, new_text: str, **kwargs: Any) -> str:
    return _edit_file(path, old_text, new_text, **kwargs)

def list_files(path: str = ".", **kwargs: Any) -> str:
    return _list_files(path, **kwargs)

def glob_files(pattern: str = "*", path: str = ".", **kwargs: Any) -> str:
    return _glob_files(pattern, path, **kwargs)

def grep_search(query: str, path: str = ".", is_regex: bool = False, **kwargs: Any) -> str:
    return _grep_search(query, path, is_regex=is_regex, **kwargs)

def run_command(command: str, skip_confirm: bool = False, timeout: int = 30, **kwargs: Any) -> str:
    return _run_command(command, timeout=timeout, **kwargs)

def run_tests(test_path: str = "tests", **kwargs: Any) -> str:
    return _run_tests(test_path=test_path, **kwargs)

TOOL_DECLARATIONS = ALL_TOOL_DECLARATIONS

TOOL_MAP = {
    "read_file": read_file,
    "write_file": write_file,
    "edit_file": edit_file,
    "list_files": list_files,
    "glob_files": glob_files,
    "grep_search": grep_search,
    "run_command": run_command,
    "run_tests": run_tests,
}
