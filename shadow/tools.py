"""
tools.py — All tool implementations for the Shadow agent.

Each function here maps 1-to-1 with a Gemini function-calling declaration.
They do the real work: reading files, writing files, running commands, etc.
"""

import os
import subprocess
import shutil
from pathlib import Path
from rich.console import Console
from rich.panel import Panel
from rich.prompt import Confirm

console = Console()

# ---------------------------------------------------------------------------
# Safety: commands that are never allowed, no matter what the model says
# ---------------------------------------------------------------------------
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

# Max characters we return to the model for a single tool result
MAX_OUTPUT_LEN = 5000


def _truncate(text: str) -> str:
    """Cut long output so we don't blow up the context window."""
    if len(text) > MAX_OUTPUT_LEN:
        half = MAX_OUTPUT_LEN // 2
        return text[:half] + "\n\n... [output truncated] ...\n\n" + text[-half:]
    return text


# ---------------------------------------------------------------------------
# Individual tool functions
# ---------------------------------------------------------------------------

def read_file(path: str, **kwargs) -> str:
    """Return the contents of a file, or an error string."""
    try:
        return _truncate(Path(path).read_text(encoding="utf-8"))
    except Exception as e:
        return f"ERROR reading {path}: {e}"


def write_file(path: str, content: str, skip_confirm: bool = False, **kwargs) -> str:
    """
    Write content to a file.
    Asks the user for confirmation unless skip_confirm is True.
    """
    if not skip_confirm:
        console.print(f"\n[bold yellow]⚠  Agent wants to write to:[/bold yellow] {path}")
        console.print(Panel(content[:500] + ("..." if len(content) > 500 else ""),
                            title="Preview", border_style="yellow"))
        ok = Confirm.ask("[yellow]Allow?[/yellow]")
        if not ok:
            return "User declined write_file."

    try:
        p = Path(path)
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(content, encoding="utf-8")
        return f"OK — wrote {len(content)} chars to {path}"
    except Exception as e:
        return f"ERROR writing {path}: {e}"


def edit_file(path: str, old_text: str, new_text: str, **kwargs) -> str:
    """Replace the first occurrence of old_text with new_text inside a file."""
    try:
        original = Path(path).read_text(encoding="utf-8")
        if old_text not in original:
            return f"ERROR: old_text not found in {path}"
        updated = original.replace(old_text, new_text, 1)
        Path(path).write_text(updated, encoding="utf-8")
        return f"OK — edited {path}"
    except Exception as e:
        return f"ERROR editing {path}: {e}"


def list_files(path: str = ".", **kwargs) -> str:
    """Return a directory listing of the given path."""
    try:
        entries = sorted(Path(path).iterdir(), key=lambda p: (p.is_file(), p.name))
        lines = []
        for entry in entries:
            prefix = "📄 " if entry.is_file() else "📁 "
            lines.append(prefix + entry.name)
        return "\n".join(lines) if lines else "(empty directory)"
    except Exception as e:
        return f"ERROR listing {path}: {e}"


def run_command(command: str, skip_confirm: bool = False, **kwargs) -> str:
    """
    Execute a shell command and return its combined stdout + stderr.
    Blocked commands are rejected.  Timeout is 30 seconds.
    """
    # Safety check
    lower = command.lower()
    for bad in BLOCKED_COMMANDS:
        if bad in lower:
            return f"BLOCKED: '{bad}' is not allowed for safety reasons."

    if not skip_confirm:
        console.print(f"\n[bold red]⚡ Agent wants to run:[/bold red] [cyan]{command}[/cyan]")
        ok = Confirm.ask("[red]Allow?[/red]")
        if not ok:
            return "User declined run_command."

    try:
        result = subprocess.run(
            command,
            shell=True,
            capture_output=True,
            text=True,
            timeout=30,
        )
        output = result.stdout + result.stderr
        return _truncate(output) if output else "(no output)"
    except subprocess.TimeoutExpired:
        return "ERROR: command timed out after 30 seconds."
    except Exception as e:
        return f"ERROR running command: {e}"


# ---------------------------------------------------------------------------
# Gemini function-call schema declarations
# (passed to the model so it knows what tools exist and how to call them)
# ---------------------------------------------------------------------------

TOOL_DECLARATIONS = [
    {
        "name": "read_file",
        "description": "Read the full text content of a file on disk.",
        "parameters": {
            "type": "object",
            "properties": {
                "path": {"type": "string", "description": "Path to the file."},
            },
            "required": ["path"],
        },
    },
    {
        "name": "write_file",
        "description": "Create or overwrite a file with the given content.",
        "parameters": {
            "type": "object",
            "properties": {
                "path":    {"type": "string", "description": "Destination file path."},
                "content": {"type": "string", "description": "Full file content to write."},
            },
            "required": ["path", "content"],
        },
    },
    {
        "name": "edit_file",
        "description": "Replace the first occurrence of old_text with new_text in a file.",
        "parameters": {
            "type": "object",
            "properties": {
                "path":     {"type": "string"},
                "old_text": {"type": "string", "description": "Exact text to find."},
                "new_text": {"type": "string", "description": "Replacement text."},
            },
            "required": ["path", "old_text", "new_text"],
        },
    },
    {
        "name": "list_files",
        "description": "List files and folders in a directory.",
        "parameters": {
            "type": "object",
            "properties": {
                "path": {"type": "string", "description": "Directory to list. Defaults to '.'"},
            },
            "required": [],
        },
    },
    {
        "name": "run_command",
        "description": "Run a shell command and return stdout + stderr.",
        "parameters": {
            "type": "object",
            "properties": {
                "command": {"type": "string", "description": "The shell command to execute."},
            },
            "required": ["command"],
        },
    },
]


# Map name → function so agent.py can dispatch by name
TOOL_MAP = {
    "read_file":   read_file,
    "write_file":  write_file,
    "edit_file":   edit_file,
    "list_files":  list_files,
    "run_command": run_command,
}
