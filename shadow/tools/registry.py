"""
registry.py — Role-based Tool Registry for ShadowX Factory.

Defines:
- Granular permissions per role (Analyst, Architect, Developer, Tester, Debugger, Reviewer, Documenter)
- Tool parameter schemas for LLM function calling
- Binding of workspace sandbox and EventBus logging
"""

from __future__ import annotations
from pathlib import Path
from typing import Callable, Optional, Union, Any

from shadow.core.event_bus import EventBus
from shadow.tools.filesystem import (
    read_file,
    write_file,
    edit_file,
    list_files,
    glob_files,
    grep_search,
)
from shadow.tools.shell import run_command
from shadow.tools.testing import run_tests

# ---------------------------------------------------------------------------
# Declarations for Gemini Function Calling
# ---------------------------------------------------------------------------

ALL_TOOL_DECLARATIONS = [
    {
        "name": "read_file",
        "description": "Read the full text content of a file within the workspace.",
        "parameters": {
            "type": "object",
            "properties": {
                "path": {"type": "string", "description": "Relative path to the file inside workspace."},
            },
            "required": ["path"],
        },
    },
    {
        "name": "write_file",
        "description": "Create or overwrite a file with given content inside the workspace.",
        "parameters": {
            "type": "object",
            "properties": {
                "path": {"type": "string", "description": "Destination file path relative to workspace."},
                "content": {"type": "string", "description": "Full file content to write."},
            },
            "required": ["path", "content"],
        },
    },
    {
        "name": "edit_file",
        "description": "Replace exactly one unique occurrence of old_text with new_text inside a file.",
        "parameters": {
            "type": "object",
            "properties": {
                "path": {"type": "string", "description": "File path relative to workspace."},
                "old_text": {"type": "string", "description": "Exact text to replace (must appear exactly once)."},
                "new_text": {"type": "string", "description": "Replacement text."},
            },
            "required": ["path", "old_text", "new_text"],
        },
    },
    {
        "name": "list_files",
        "description": "List files and directories in a workspace directory.",
        "parameters": {
            "type": "object",
            "properties": {
                "path": {"type": "string", "description": "Directory relative to workspace. Defaults to '.'"},
            },
            "required": [],
        },
    },
    {
        "name": "glob_files",
        "description": "Find files matching a glob pattern (e.g. '**/*.py') within the workspace.",
        "parameters": {
            "type": "object",
            "properties": {
                "pattern": {"type": "string", "description": "Glob pattern (e.g. '*.py' or 'src/**/*.ts')."},
                "path": {"type": "string", "description": "Base directory to search from. Defaults to '.'"},
            },
            "required": ["pattern"],
        },
    },
    {
        "name": "grep_search",
        "description": "Search for a query string or regex pattern across workspace text files.",
        "parameters": {
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": "Text substring or regex pattern to match."},
                "path": {"type": "string", "description": "Directory to search. Defaults to '.'"},
                "is_regex": {"type": "boolean", "description": "True if query is a regular expression."},
            },
            "required": ["query"],
        },
    },
    {
        "name": "run_command",
        "description": "Execute a shell command inside the workspace directory.",
        "parameters": {
            "type": "object",
            "properties": {
                "command": {"type": "string", "description": "The shell command to execute."},
                "timeout": {"type": "integer", "description": "Timeout in seconds (1 to 120, default 30)."},
            },
            "required": ["command"],
        },
    },
    {
        "name": "run_tests",
        "description": "Execute pytest in the workspace and return structured pass/fail results.",
        "parameters": {
            "type": "object",
            "properties": {
                "test_path": {"type": "string", "description": "Path to test directory or file. Defaults to 'tests'."},
            },
            "required": [],
        },
    },
]

TOOL_DECLARATION_MAP = {d["name"]: d for d in ALL_TOOL_DECLARATIONS}

# ---------------------------------------------------------------------------
# Role Specifications and Constraints
# ---------------------------------------------------------------------------

ROLE_RULES: dict[str, dict[str, Any]] = {
    "Analyst": {
        "allowed_tools": ["read_file", "write_file", "list_files", "glob_files", "grep_search"],
        "write_paths": ["docs/"],
    },
    "Architect": {
        "allowed_tools": ["read_file", "write_file", "list_files", "glob_files", "grep_search"],
        "write_paths": ["docs/"],
    },
    "Developer": {
        "allowed_tools": [
            "read_file",
            "write_file",
            "edit_file",
            "list_files",
            "glob_files",
            "grep_search",
            "run_command",
        ],
        "write_paths": ["src/", ""],  # Can implement in src/ and root config
        "forbidden_write_paths": ["tests/"],  # Developer does not write tests
    },
    "Tester": {
        "allowed_tools": [
            "read_file",
            "write_file",
            "list_files",
            "glob_files",
            "grep_search",
            "run_tests",
        ],
        "write_paths": ["tests/", "test_report.json"],
        "forbidden_write_paths": ["src/"],  # Tester cannot modify src/
    },
    "Debugger": {
        "allowed_tools": [
            "read_file",
            "write_file",
            "edit_file",
            "list_files",
            "glob_files",
            "grep_search",
            "run_command",
            "run_tests",
        ],
        "write_paths": ["src/", "debug_log.md"],
        "forbidden_write_paths": ["tests/"],  # Cannot edit tests to force a pass
    },
    "Reviewer": {
        "allowed_tools": ["read_file", "write_file", "list_files", "glob_files", "grep_search"],
        "write_paths": ["docs/review.md", "review.md"],
    },
    "Documenter": {
        "allowed_tools": [
            "read_file",
            "write_file",
            "edit_file",
            "list_files",
            "glob_files",
            "grep_search",
            "run_command",
        ],
        "write_paths": ["README.md", "docs/"],
    },
    "CLI": {
        "allowed_tools": [
            "read_file",
            "write_file",
            "edit_file",
            "list_files",
            "glob_files",
            "grep_search",
            "run_command",
            "run_tests",
        ],
        "write_paths": None,  # Unrestricted in workspace
    },
}


class ToolRegistry:
    """
    Registry managing tool functions, role permission enforcement, and sandbox binding.
    """

    def __init__(
        self,
        workspace_root: Union[str, Path] = ".",
        event_bus: Optional[EventBus] = None,
        run_id: str = "default",
    ) -> None:
        self.workspace_root = Path(workspace_root).resolve()
        self.event_bus = event_bus
        self.run_id = run_id

        # Base tool map
        self._raw_tools: dict[str, Callable[..., Any]] = {
            "read_file": read_file,
            "write_file": write_file,
            "edit_file": edit_file,
            "list_files": list_files,
            "glob_files": glob_files,
            "grep_search": grep_search,
            "run_command": run_command,
            "run_tests": run_tests,
        }

    def _check_path_permission(self, role: str, tool_name: str, path: str) -> Optional[str]:
        """Validate if a role is permitted to write/edit a given path."""
        rules = ROLE_RULES.get(role)
        if not rules:
            return None  # Unspecified role or CLI has full access

        norm_path = str(path).replace("\\", "/").lstrip("/")

        # Check explicit forbidden paths
        forbidden = rules.get("forbidden_write_paths") or []
        for f in forbidden:
            f_norm = f.rstrip("/")
            if norm_path == f_norm or norm_path.startswith(f"{f_norm}/"):
                return f"ERROR: Role '{role}' is forbidden from modifying '{path}' (blocked prefix: '{f}')"

        # Check allowed write paths if restricted
        allowed = rules.get("write_paths")
        if allowed is not None:
            matches_allowed = False
            for a in allowed:
                a_norm = a.rstrip("/")
                if not a_norm:
                    # Root level file
                    if "/" not in norm_path:
                        matches_allowed = True
                        break
                elif norm_path == a_norm or norm_path.startswith(f"{a_norm}/"):
                    matches_allowed = True
                    break

            if not matches_allowed:
                return (
                    f"ERROR: Role '{role}' is not allowed to modify '{path}'. "
                    f"Permitted write locations: {allowed}"
                )

        return None

    def get_tools_for_role(
        self,
        role: str,
        agent_name: Optional[str] = None,
    ) -> dict[str, Callable[..., Any]]:
        """
        Return the bound dictionary of allowed tools for a given role.
        Enforces both tool selection and filesystem scope constraints.
        """
        effective_agent_name = agent_name or role
        rules = ROLE_RULES.get(role, ROLE_RULES["CLI"])
        allowed_tool_names = set(rules.get("allowed_tools", list(self._raw_tools.keys())))

        bound_tools: dict[str, Callable[..., Any]] = {}

        for name in allowed_tool_names:
            if name not in self._raw_tools:
                continue

            raw_fn = self._raw_tools[name]

            def make_wrapper(fn_name: str, target_fn: Callable[..., Any]) -> Callable[..., Any]:
                def wrapper(*args: Any, **kwargs: Any) -> Any:
                    # Inject workspace_root, event_bus, run_id, agent_name
                    kwargs.setdefault("workspace_root", self.workspace_root)
                    kwargs.setdefault("event_bus", self.event_bus)
                    kwargs.setdefault("run_id", self.run_id)
                    kwargs.setdefault("agent_name", effective_agent_name)

                    # Path permission check on write / edit
                    if fn_name in ("write_file", "edit_file"):
                        path_arg = kwargs.get("path") or (args[0] if args else None)
                        if path_arg:
                            perm_err = self._check_path_permission(role, fn_name, str(path_arg))
                            if perm_err:
                                return perm_err

                    return target_fn(*args, **kwargs)

                return wrapper

            bound_tools[name] = make_wrapper(name, raw_fn)

        return bound_tools

    def get_declarations_for_role(self, role: str) -> list[dict[str, Any]]:
        """Return schema declarations corresponding to the role's allowed tools."""
        rules = ROLE_RULES.get(role, ROLE_RULES["CLI"])
        allowed_tool_names = set(rules.get("allowed_tools", list(self._raw_tools.keys())))
        return [d for d in ALL_TOOL_DECLARATIONS if d["name"] in allowed_tool_names]

    def get_all_tools(self, agent_name: str = "ShadowX") -> dict[str, Callable[..., Any]]:
        """Return all tools configured for interactive/CLI usage."""
        return self.get_tools_for_role("CLI", agent_name=agent_name)

    def get_all_declarations(self) -> list[dict[str, Any]]:
        """Return all tool declarations."""
        return list(ALL_TOOL_DECLARATIONS)
