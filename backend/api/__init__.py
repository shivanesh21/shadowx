"""api — Backward-compatibility facade forwarding to backend."""
import sys
import backend
import backend.database
import backend.run_manager
import backend.sse
import backend.main

sys.modules["api.database"] = backend.database
sys.modules["api.run_manager"] = backend.run_manager
sys.modules["api.sse"] = backend.sse
sys.modules["api.main"] = backend.main
