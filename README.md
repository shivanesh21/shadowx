# ShadowX 🌒

**ShadowX** is a fast, sandboxed, and observable terminal AI coding agent and foundation engine for **ShadowX Factory** — an Agentic Software Factory powered by Google Gemini.

---

## ⚡ What Makes ShadowX Different?

Most terminal AI agents couple LLM generation directly with shell execution and console printing. **ShadowX** decouples execution, tooling, security, and observability into modular layers:

```
┌────────────────────────────────────────────────────────┐
│                   ShadowX ReAct Loop                   │
│         (Spec-Driven, Dual-Track SDK Memory)           │
└──────────────────────────┬─────────────────────────────┘
                           │ Emits Typed Events
                           ▼
┌────────────────────────────────────────────────────────┐
│                   In-Process EventBus                  │
│       (Sync/Async Dispatcher + events.jsonl Log)       │
└────────────┬─────────────────────────────┬─────────────┘
             │                             │
             ▼                             ▼
┌──────────────────────────┐  ┌──────────────────────────┐
│   CLI Event Renderer     │  │  Telemetry & Web UI /    │
│    (Rich Terminal UI)    │  │    SSE Event Streams     │
└──────────────────────────┘  └──────────────────────────┘
```

---

## 🛡️ Key Features & Capabilities

| Capability | Technical Implementation | Benefit |
|---|---|---|
| 🔒 **Workspace Sandbox** | `resolve_workspace_path` with strict confinement | Blocks `../` traversal, drive changes, and symlink escapes |
| 🧹 **Credential Scrubbing** | `scrub_environment` cleans `os.environ` | Strips `GEMINI_API_KEY` and tokens from subprocess execution |
| ✂️ **Surgical Code Editing** | `edit_file` enforces strict 1-occurrence uniqueness | Zero hallucinated multi-edits; returns unified diff on success |
| 🧪 **Structured Test Runner**| `run_tests` parses `pytest` runs | Provides structured pass/fail metrics and test failure traces |
| 👥 **Role-Based Permissions**| `ToolRegistry` with role rules | Least-privilege matrix (`Analyst`, `Architect`, `Dev`, `Tester`, `Debugger`) |
| 📡 **Event-Driven UI** | Typed events (`Event`, `ToolCallEvent`, `FileChanged`) | Terminal UI renders purely from events; decoupled from core logic |
| 📝 **Audit Logging** | In-process `EventBus` auto-streams to `events.jsonl` | Complete audit trail ready for offline replay and web UI |

---

## 🛠️ Tool Registry & Role Permissions

The centralized `ToolRegistry` enforces role-specific capabilities:

- **Analyst & Architect**: Read access and documentation generation (`docs/` only).
- **Developer**: Read, write, edit, search (`glob_files`, `grep_search`), and shell commands (`src/` scoped). Cannot touch tests.
- **Tester**: Derives and writes tests in `tests/`, executes `run_tests`. Cannot edit `src/`.
- **Debugger**: Diagnoses test failures, edits `src/` to fix bugs, executes `run_tests`. Forbidden from modifying `tests/` to prevent weakening assertions.
- **Reviewer**: Read and search only.
- **Documenter**: Read and documentation editing (`README.md`, `docs/`).
- **CLI / Default**: Full access across the workspace root for standalone terminal use.

---

## 🚀 Quickstart

### 1. Installation

```bash
git clone https://github.com/your-username/shadowx.git
cd shadowx
pip install -e .
```

### 2. Configure Environment

Create a `.env` file in the root folder:

```env
GEMINI_API_KEY=your-gemini-api-key-here
MODEL_NAME=gemini-3.5-flash-lite
```

*(If not provided, ShadowX will prompt you interactively on first launch).*

### 3. Run the Agent

**Interactive Mode:**
```bash
python -m shadow.cli
# or on Windows with Device Guard:
.\shadowx.bat
```

**One-Shot Mode:**
```bash
python -m shadow.cli "Create a hello.py that prints Hello World and run it"
```

---

## 🧪 Running Unit Tests

The test suite requires no network or Gemini API keys to run unit tests:

```bash
python -m pytest tests/ -v
```

All 27 tests validate:
- Path traversal & escape prevention
- Environment scrubbing
- `edit_file` uniqueness and unified diff generation
- Shell command timeout and truncation
- Structured test runner
- Tool Registry permissions per role
- EventBus publication and `events.jsonl` persistence
- ReAct loop execution and finish tool contract

---

## 📂 Project Architecture

```
shadowx/
├── backend/            # Dedicated FastAPI backend service
│   ├── main.py         # REST & SSE API endpoints
│   ├── database.py     # SQLite persistence layer
│   ├── run_manager.py  # Background run executor & lifecycle
│   └── sse.py          # Server-Sent Events stream generator
├── frontend/           # Dedicated React + Vite + TypeScript web application
│   ├── src/            # Visual pipeline DAG, Monaco editor, timeline, artifacts
│   ├── package.json    # Frontend dependencies and build scripts
│   └── vite.config.ts  # Configured to build into static/
├── static/             # Bundled SPA assets served by FastAPI
├── api/                # Backward-compatibility shims forwarding to backend/
├── shadow/             # Core agent framework & CLI
│   ├── core/           # ReAct Agent loop, EventBus, events, LLM providers
│   ├── tools/          # Sandboxing, filesystem, shell, testing, registry
│   ├── cli.py          # Rich terminal REPL and one-shot runner
│   └── agent.py        # Single-agent baseline runner
├── pipeline/           # Multi-agent orchestrator & state machine
│   ├── orchestrator.py # State machine, loop guard, stage execution
│   ├── git_checkpoints.py # Workspace git snapshots & stage rollback
│   └── schemas.py      # Pydantic schemas for requirements, design, reviews
├── evals/              # Benchmark evaluation tasks and comparison runner
├── docs/               # System architecture, ADRs, security specifications
└── tests/              # 97 unit, integration, and security tests
```

---

## 📜 License

MIT License.
