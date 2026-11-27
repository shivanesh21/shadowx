"""run_manager.py — Compatibility shim forwarding to backend.run_manager."""
from backend.run_manager import *
from backend.run_manager import _lock, _active_run_id, _approval_events, _cancel_flags, RUNS_DIR
