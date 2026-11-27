"""
test_tools.py — Unit tests for hardened tools, sandboxing, and role permissions.
"""

import os
import json
from pathlib import Path
import pytest

from shadow.tools.sandbox import resolve_workspace_path, scrub_environment
from shadow.tools.filesystem import (
    read_file,
    write_file,
    edit_file,
    list_files,
    glob_files,
    grep_search,
)
from shadow.tools.shell import run_command, BLOCKED_COMMANDS
from shadow.tools.testing import run_tests
from shadow.tools.registry import ToolRegistry, ROLE_RULES
from shadow.core.event_bus import EventBus
from shadow.core.events import FileChanged, TestResultEvent


# ---------------------------------------------------------------------------
# 1. Workspace Sandboxing & Path Traversal
# ---------------------------------------------------------------------------

def test_resolve_workspace_path_valid(tmp_path: Path):
    ws = tmp_path / "workspace"
    ws.mkdir()
    target = ws / "sub" / "file.txt"

    resolved = resolve_workspace_path("sub/file.txt", ws)
    assert resolved == target.resolve()


def test_resolve_workspace_path_traversal_rejected(tmp_path: Path):
    ws = tmp_path / "workspace"
    ws.mkdir()

    with pytest.raises(PermissionError, match="Path traversal detected"):
        resolve_workspace_path("../outside.txt", ws)

    with pytest.raises(PermissionError, match="Path traversal detected"):
        resolve_workspace_path("foo/../../escape.txt", ws)


def test_resolve_workspace_path_absolute_escape_rejected(tmp_path: Path):
    ws = tmp_path / "workspace"
    ws.mkdir()
    outside = tmp_path / "outside_dir" / "secret.txt"

    with pytest.raises(PermissionError, match="Path traversal detected"):
        resolve_workspace_path(outside, ws)


# ---------------------------------------------------------------------------
# 2. Environment Scrubbing
# ---------------------------------------------------------------------------

def test_scrub_environment():
    os.environ["GEMINI_API_KEY"] = "secret-gemini-key"
    os.environ["MY_SUPER_SECRET_TOKEN"] = "hidden-token"
    os.environ["SAFE_SYSTEM_VAR"] = "visible_value"

    try:
        clean = scrub_environment()
        assert "GEMINI_API_KEY" not in clean
        assert "MY_SUPER_SECRET_TOKEN" not in clean
        assert clean.get("SAFE_SYSTEM_VAR") == "visible_value"
    finally:
        os.environ.pop("MY_SUPER_SECRET_TOKEN", None)
        os.environ.pop("SAFE_SYSTEM_VAR", None)


# ---------------------------------------------------------------------------
# 3. Filesystem Tools & edit_file Uniqueness
# ---------------------------------------------------------------------------

def test_write_and_read_file(tmp_path: Path):
    ws = tmp_path / "workspace"
    ws.mkdir()

    # Write
    res_w = write_file("docs/readme.txt", "Hello World\nLine 2", workspace_root=ws)
    assert "OK — created docs/readme.txt" in res_w
    assert (ws / "docs" / "readme.txt").exists()

    # Read
    res_r = read_file("docs/readme.txt", workspace_root=ws)
    assert res_r == "Hello World\nLine 2"

    # Read non-existent
    res_missing = read_file("docs/none.txt", workspace_root=ws)
    assert "ERROR: File not found" in res_missing


def test_write_file_emits_file_changed(tmp_path: Path):
    ws = tmp_path / "workspace"
    ws.mkdir()
    bus = EventBus()
    received = []
    bus.subscribe(lambda e: received.append(e), "file_changed")

    write_file("main.py", "print('hello')", workspace_root=ws, event_bus=bus, agent_name="Developer")
    assert len(received) == 1
    assert received[0].path == "main.py"
    assert received[0].agent_name == "Developer"


def test_edit_file_success_with_diff(tmp_path: Path):
    ws = tmp_path / "workspace"
    ws.mkdir()
    f = ws / "app.py"
    f.write_text("def hello():\n    return 'old'\n", encoding="utf-8")

    bus = EventBus()
    received = []
    bus.subscribe(lambda e: received.append(e), "file_changed")

    res = edit_file("app.py", "return 'old'", "return 'new'", workspace_root=ws, event_bus=bus)
    assert "OK — edited app.py" in res
    assert "Diff:" in res
    assert "-    return 'old'" in res
    assert "+    return 'new'" in res
    assert (ws / "app.py").read_text() == "def hello():\n    return 'new'\n"
    assert len(received) == 1


def test_edit_file_not_found(tmp_path: Path):
    ws = tmp_path / "workspace"
    ws.mkdir()
    f = ws / "app.py"
    f.write_text("value = 10\n", encoding="utf-8")

    res = edit_file("app.py", "value = 99", "value = 100", workspace_root=ws)
    assert "ERROR: old_text not found in app.py" in res


def test_edit_file_not_unique_error(tmp_path: Path):
    ws = tmp_path / "workspace"
    ws.mkdir()
    f = ws / "app.py"
    f.write_text("item = 'val'\nitem = 'val'\n", encoding="utf-8")

    res = edit_file("app.py", "item = 'val'", "item = 'new_val'", workspace_root=ws)
    assert "ERROR: old_text is not unique in app.py" in res
    assert "found 2 occurrences" in res


def test_glob_files(tmp_path: Path):
    ws = tmp_path / "workspace"
    ws.mkdir()
    (ws / "src").mkdir()
    (ws / "src" / "a.py").write_text("x = 1")
    (ws / "src" / "b.ts").write_text("let x = 1;")
    (ws / "root.py").write_text("y = 2")

    res = glob_files("*.py", path="src", workspace_root=ws)
    assert "src/a.py" in res
    assert "src/b.ts" not in res


def test_grep_search(tmp_path: Path):
    ws = tmp_path / "workspace"
    ws.mkdir()
    (ws / "calc.py").write_text("def calculate_sum(a, b):\n    return a + b\n")

    res = grep_search("calculate_sum", workspace_root=ws)
    assert "calc.py:1: def calculate_sum" in res

    res_missing = grep_search("non_existent_symbol", workspace_root=ws)
    assert "no matches found" in res_missing


# ---------------------------------------------------------------------------
# 4. Shell Sandboxing
# ---------------------------------------------------------------------------

def test_run_command_blocklist():
    res = run_command("rm -rf /")
    assert "BLOCKED: Command contains dangerous token 'rm -rf'" in res


def test_run_command_executes_in_workspace(tmp_path: Path):
    ws = tmp_path / "workspace"
    ws.mkdir()
    res = run_command("python -c \"import os; print(os.getcwd())\"", workspace_root=ws)
    assert str(ws).lower() in res.lower()


def test_run_command_timeout(tmp_path: Path):
    ws = tmp_path / "workspace"
    ws.mkdir()
    # Execute python sleep with 1 second timeout
    res = run_command("python -c \"import time; time.sleep(3)\"", timeout=1, workspace_root=ws)
    assert "timed out after 1 seconds" in res


# ---------------------------------------------------------------------------
# 5. Testing Tool & Structured Results
# ---------------------------------------------------------------------------

def test_run_tests_structured_success(tmp_path: Path):
    ws = tmp_path / "workspace"
    ws.mkdir()
    tests_dir = ws / "tests"
    tests_dir.mkdir()
    (tests_dir / "test_ok.py").write_text("def test_pass(): assert 1 + 1 == 2\n")

    bus = EventBus()
    received = []
    bus.subscribe(lambda e: received.append(e), "test_result")

    res = run_tests("tests", workspace_root=ws, event_bus=bus)
    assert "TEST RUN RESULT: PASSED" in res
    assert "Passed: 1" in res
    assert len(received) == 1
    assert received[0].passed == 1
    assert received[0].failed == 0


def test_run_tests_structured_failure(tmp_path: Path):
    ws = tmp_path / "workspace"
    ws.mkdir()
    tests_dir = ws / "tests"
    tests_dir.mkdir()
    (tests_dir / "test_fail.py").write_text("def test_bad(): assert 1 == 2\n")

    bus = EventBus()
    received = []
    bus.subscribe(lambda e: received.append(e), "test_result")

    res = run_tests("tests", workspace_root=ws, event_bus=bus)
    assert "TEST RUN RESULT: FAILED" in res
    assert "Failed: 1" in res
    assert len(received) == 1
    assert received[0].failed == 1


# ---------------------------------------------------------------------------
# 6. Tool Registry & Per-Role Permissions
# ---------------------------------------------------------------------------

def test_tool_registry_analyst_permissions(tmp_path: Path):
    ws = tmp_path / "workspace"
    ws.mkdir()
    registry = ToolRegistry(workspace_root=ws)

    analyst_tools = registry.get_tools_for_role("Analyst")
    assert "read_file" in analyst_tools
    assert "write_file" in analyst_tools
    assert "run_command" not in analyst_tools  # Analyst cannot run commands

    # Analyst can write to docs/
    ok_res = analyst_tools["write_file"]("docs/requirements.md", "# Requirements")
    assert "OK — created" in ok_res

    # Analyst cannot write to src/
    denied_res = analyst_tools["write_file"]("src/main.py", "x = 1")
    assert "ERROR: Role 'Analyst' is not allowed to modify 'src/main.py'" in denied_res


def test_tool_registry_tester_permissions(tmp_path: Path):
    ws = tmp_path / "workspace"
    ws.mkdir()
    registry = ToolRegistry(workspace_root=ws)

    tester_tools = registry.get_tools_for_role("Tester")
    assert "run_tests" in tester_tools
    assert "write_file" in tester_tools
    assert "edit_file" not in tester_tools  # Tester cannot edit existing source files

    # Tester can write to tests/
    res_ok = tester_tools["write_file"]("tests/test_foo.py", "def test_foo(): pass")
    assert "OK — created" in res_ok

    # Tester cannot write to src/
    res_blocked = tester_tools["write_file"]("src/app.py", "x = 1")
    assert "ERROR: Role 'Tester' is forbidden from modifying 'src/app.py'" in res_blocked


def test_tool_registry_debugger_permissions(tmp_path: Path):
    ws = tmp_path / "workspace"
    ws.mkdir()
    registry = ToolRegistry(workspace_root=ws)

    debugger_tools = registry.get_tools_for_role("Debugger")
    assert "edit_file" in debugger_tools
    assert "write_file" in debugger_tools

    # Debugger can write debug_log.md
    res_log = debugger_tools["write_file"]("debug_log.md", "# Debug Log\nFixed bug.")
    assert "OK" in res_log

    # Setup file in src/ and tests/
    (ws / "src").mkdir()
    (ws / "src" / "app.py").write_text("val = 1\n")
    (ws / "tests").mkdir()
    (ws / "tests" / "test_app.py").write_text("def test(): pass\n")

    # Debugger can edit src/
    res_ok = debugger_tools["edit_file"]("src/app.py", "val = 1", "val = 2")
    assert "OK — edited src/app.py" in res_ok

    # Debugger cannot edit tests/
    res_blocked = debugger_tools["edit_file"]("tests/test_app.py", "pass", "assert True")
    assert "ERROR: Role 'Debugger' is forbidden from modifying 'tests/test_app.py'" in res_blocked
