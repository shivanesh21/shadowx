"""
filesystem.py — Hardened filesystem tools for ShadowX Factory.

All operations are confined within the workspace root.
Provides:
- read_file
- write_file (creates dirs, emits FileChanged)
- edit_file (enforces uniqueness, returns unified diff, emits FileChanged)
- list_files
- glob_files
- grep_search
"""

from __future__ import annotations
import difflib
import re
from pathlib import Path
from typing import Optional, Union, Any

from shadow.tools.sandbox import resolve_workspace_path
from shadow.core.events import FileChanged
from shadow.core.event_bus import EventBus

MAX_OUTPUT_LEN = 5000


def _truncate_head_tail(text: str, max_len: int = MAX_OUTPUT_LEN) -> str:
    """Preserve both the beginning and the end of long text outputs."""
    if len(text) <= max_len:
        return text
    half = max_len // 2
    return text[:half] + f"\n\n... [output truncated ({len(text)} chars total)] ...\n\n" + text[-half:]


def read_file(path: str, workspace_root: Union[str, Path] = ".", **kwargs: Any) -> str:
    """Return the contents of a file inside the workspace."""
    try:
        target = resolve_workspace_path(path, workspace_root)
        if not target.exists():
            return f"ERROR: File not found: {path}"
        if not target.is_file():
            return f"ERROR: Path is not a file: {path}"
        content = target.read_text(encoding="utf-8", errors="replace")
        return _truncate_head_tail(content)
    except PermissionError as pe:
        return f"ERROR: {pe}"
    except Exception as e:
        return f"ERROR reading {path}: {e}"


def write_file(
    path: str,
    content: str,
    workspace_root: Union[str, Path] = ".",
    event_bus: Optional[EventBus] = None,
    run_id: str = "default",
    agent_name: str = "",
    **kwargs: Any,
) -> str:
    """Write content to a file inside the workspace and emit FileChanged event."""
    try:
        target = resolve_workspace_path(path, workspace_root)
        target.parent.mkdir(parents=True, exist_ok=True)

        old_content = ""
        is_new = not target.exists()
        if not is_new:
            try:
                old_content = target.read_text(encoding="utf-8", errors="replace")
            except Exception:
                old_content = ""

        target.write_text(content, encoding="utf-8")

        diff = "".join(
            difflib.unified_diff(
                old_content.splitlines(keepends=True),
                content.splitlines(keepends=True),
                fromfile=f"a/{path}",
                tofile=f"b/{path}",
                n=3,
            )
        )

        if event_bus:
            event_bus.emit(
                FileChanged(
                    run_id=run_id,
                    path=str(path),
                    diff=diff or f"(created {path} with {len(content)} chars)",
                    agent_name=agent_name,
                )
            )

        status = "created" if is_new else "overwrote"
        return f"OK — {status} {path} ({len(content)} chars)"
    except PermissionError as pe:
        return f"ERROR: {pe}"
    except Exception as e:
        return f"ERROR writing {path}: {e}"


def edit_file(
    path: str,
    old_text: str,
    new_text: str,
    workspace_root: Union[str, Path] = ".",
    event_bus: Optional[EventBus] = None,
    run_id: str = "default",
    agent_name: str = "",
    **kwargs: Any,
) -> str:
    """
    Replace exactly one occurrence of old_text with new_text.

    Returns an error if old_text is missing or not unique in the file.
    Returns a unified diff on success.
    """
    try:
        target = resolve_workspace_path(path, workspace_root)
        if not target.exists():
            return f"ERROR: File not found: {path}"

        original = target.read_text(encoding="utf-8", errors="replace")
        count = original.count(old_text)

        if count == 0:
            return f"ERROR: old_text not found in {path}"
        if count > 1:
            return (
                f"ERROR: old_text is not unique in {path} (found {count} occurrences). "
                f"Include more surrounding context lines so the target snippet matches exactly once."
            )

        updated = original.replace(old_text, new_text, 1)
        target.write_text(updated, encoding="utf-8")

        diff = "".join(
            difflib.unified_diff(
                original.splitlines(keepends=True),
                updated.splitlines(keepends=True),
                fromfile=f"a/{path}",
                tofile=f"b/{path}",
                n=3,
            )
        )

        if event_bus:
            event_bus.emit(
                FileChanged(
                    run_id=run_id,
                    path=str(path),
                    diff=diff,
                    agent_name=agent_name,
                )
            )

        return f"OK — edited {path}\n\nDiff:\n{diff}"
    except PermissionError as pe:
        return f"ERROR: {pe}"
    except Exception as e:
        return f"ERROR editing {path}: {e}"


def list_files(path: str = ".", workspace_root: Union[str, Path] = ".", **kwargs: Any) -> str:
    """Return a directory listing of the given path within the workspace."""
    try:
        target = resolve_workspace_path(path, workspace_root)
        if not target.exists():
            return f"ERROR: Directory not found: {path}"
        if not target.is_dir():
            return f"ERROR: Path is not a directory: {path}"

        entries = sorted(target.iterdir(), key=lambda p: (p.is_file(), p.name.lower()))
        lines = []
        for entry in entries:
            # Skip noise directories
            if entry.name in {".git", "__pycache__", ".pytest_cache"}:
                continue
            prefix = "📄 " if entry.is_file() else "📁 "
            lines.append(f"{prefix}{entry.name}")

        return "\n".join(lines) if lines else "(empty directory)"
    except PermissionError as pe:
        return f"ERROR: {pe}"
    except Exception as e:
        return f"ERROR listing {path}: {e}"


def glob_files(
    pattern: str = "*",
    path: str = ".",
    workspace_root: Union[str, Path] = ".",
    **kwargs: Any,
) -> str:
    """Find files matching a glob pattern relative to a base directory in the workspace."""
    try:
        raw_pat = pattern.replace("\\", "/")
        if ".." in [p for p in raw_pat.split("/") if p]:
            return f"ERROR: Path traversal detected in glob pattern '{pattern}'"

        root = Path(workspace_root).resolve()
        target = resolve_workspace_path(path, workspace_root)
        if not target.exists() or not target.is_dir():
            return f"ERROR: Invalid base directory: {path}"

        matches = []
        for p in target.glob(pattern):
            if any(part in {".git", "__pycache__", ".pytest_cache"} for part in p.parts):
                continue
            if p.is_file():
                try:
                    rel = p.relative_to(root)
                    matches.append(str(rel).replace("\\", "/"))
                except ValueError:
                    continue

        matches.sort()
        if not matches:
            return f"(no files matched pattern '{pattern}')"

        output = "\n".join(matches)
        return _truncate_head_tail(output)
    except PermissionError as pe:
        return f"ERROR: {pe}"
    except Exception as e:
        return f"ERROR in glob_files: {e}"


def grep_search(
    query: str,
    path: str = ".",
    is_regex: bool = False,
    workspace_root: Union[str, Path] = ".",
    **kwargs: Any,
) -> str:
    """Search for query string or regex pattern in text files within the workspace."""
    try:
        root = Path(workspace_root).resolve()
        target = resolve_workspace_path(path, workspace_root)
        if not target.exists():
            return f"ERROR: Path not found: {path}"

        compiled_re = re.compile(query) if is_regex else None
        results: list[str] = []

        files_to_search = [target] if target.is_file() else target.rglob("*")

        for f in files_to_search:
            if not f.is_file():
                continue
            if any(part in {".git", "__pycache__", ".pytest_cache", "runs"} for part in f.parts):
                continue

            try:
                rel_path = str(f.relative_to(root)).replace("\\", "/")
                lines = f.read_text(encoding="utf-8", errors="ignore").splitlines()
                for line_num, line in enumerate(lines, start=1):
                    match = bool(compiled_re.search(line)) if compiled_re else (query in line)
                    if match:
                        results.append(f"{rel_path}:{line_num}: {line.strip()[:200]}")
                        if len(results) >= 200:
                            results.append("... [further matches truncated at 200 items] ...")
                            break
            except Exception:
                continue

            if len(results) >= 201:
                break

        if not results:
            return f"(no matches found for '{query}')"

        return _truncate_head_tail("\n".join(results))
    except PermissionError as pe:
        return f"ERROR: {pe}"
    except Exception as e:
        return f"ERROR in grep_search: {e}"
