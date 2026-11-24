"""
git_checkpoints.py — Workspace Git checkpoint helper for ShadowX Factory.

Initializes git within the run workspace and records snapshot commits after
every stage transition so stages can be audited or rolled back.
"""

from __future__ import annotations
import subprocess
import logging
from pathlib import Path

logger = logging.getLogger(__name__)


def init_workspace_git(workspace_dir: Path) -> bool:
    """
    Initialize a local git repository inside the workspace directory if not present.
    Configures a factory committer identity so commits succeed without global git config.
    """
    ws = Path(workspace_dir).resolve()
    ws.mkdir(parents=True, exist_ok=True)
    git_dir = ws / ".git"

    if not git_dir.exists():
        try:
            subprocess.run(
                ["git", "init"],
                cwd=str(ws),
                capture_output=True,
                check=True,
                text=True,
            )
            subprocess.run(
                ["git", "config", "user.name", "ShadowX Factory"],
                cwd=str(ws),
                capture_output=True,
                check=True,
                text=True,
            )
            subprocess.run(
                ["git", "config", "user.email", "factory@shadowx.local"],
                cwd=str(ws),
                capture_output=True,
                check=True,
                text=True,
            )
            return True
        except Exception as e:
            logger.warning(f"Failed to initialize git repository in workspace: {e}")
            return False
    return True


def create_checkpoint(workspace_dir: Path, stage_name: str) -> str:
    """
    Stage all files in the workspace and commit a checkpoint.
    Returns the commit hash or an empty string if git is unavailable.
    """
    ws = Path(workspace_dir).resolve()
    init_workspace_git(ws)

    try:
        subprocess.run(
            ["git", "add", "-A"],
            cwd=str(ws),
            capture_output=True,
            check=True,
            text=True,
        )
        msg = f"checkpoint({stage_name.lower()}): completed {stage_name} stage"
        subprocess.run(
            ["git", "commit", "-m", msg, "--allow-empty"],
            cwd=str(ws),
            capture_output=True,
            check=True,
            text=True,
        )
        res = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=str(ws),
            capture_output=True,
            check=True,
            text=True,
        )
        commit_hash = res.stdout.strip()
        return commit_hash
    except Exception as e:
        logger.warning(f"Git checkpoint failed for stage {stage_name}: {e}")
        return ""
