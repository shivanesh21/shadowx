# ShadowX 🌑

**ShadowX** is a fast, polished terminal AI coding agent powered by Google Gemini.  
It reads files, writes code, edits projects, and runs commands — all from your terminal, with a beautiful Rich UI.

---

## Features

| Feature | Detail |
|---|---|
| ⚡ **Fast execution** | Simple greetings in 1 turn, full tasks in 2-3 steps |
| 💬 **Interactive chat** | Persistent conversation across tasks |
| 📂 **History** | Saves & resumes from `shadowx_history.json` |
| 🎨 **Rich UI** | Colored panels, spinners, and markdown rendering |
| 🛡️ **Safety** | Blocks dangerous commands (`rm -rf`, `format`, `shutdown`) |
| 🔧 **Tools** | `read_file`, `write_file`, `edit_file`, `list_files`, `run_command` |

---

## Setup

### 1. Install dependencies

```bash
pip install -e .
```

This registers the `shadowx` command.

### 2. Configure API key

Create a `.env` file in the project folder (or let ShadowX prompt you on first run):

```env
GEMINI_API_KEY=your-api-key-here
MODEL_NAME=gemini-3.5-flash-lite
```

---

## Usage

### Interactive mode (recommended)

```bash
shadowx
```
*(or `.\shadowx.bat` on Windows if Device Guard is active)*

```
You > hi
You > create a hello.py that prints Hello World and run it
You > /help
You > /clear
You > exit
```

### One-shot mode

```bash
shadowx "create a hello.py and run it"
```

### Flags

| Flag | Effect |
|---|---|
| `--yes` / `-y` | Auto-approve all tool confirmations |
| `--fresh` | Ignore saved history; start a fresh conversation |

```bash
shadow --yes "create a full Flask REST API skeleton"
shadow --fresh "start over with a new project"
```

---

## Special commands (interactive mode)

| Command | Effect |
|---|---|
| `/help` | Show all available commands |
| `/clear` | Wipe conversation history |
| `exit` | Quit Shadow |

---

## Project structure

```
shadow/
├── __init__.py    # Package marker + version
├── agent.py       # Agentic loop, Gemini client, history I/O
├── cli.py         # CLI entry-point, interactive loop
└── tools.py       # Tool implementations (read, write, edit, run…)
pyproject.toml     # pip install -e . config
README.md          # This file
```

---

## How it works

1. **You** type a task.
2. **Shadow** writes a short plan.
3. **Gemini** decides which tool to call.
4. **Shadow** executes the tool, shows you the result, and feeds it back.
5. Repeat until the model has no more tool calls → final summary printed.
6. History saved to `shadow_history.json`.

---

## Safety

- `rm -rf`, `format`, `shutdown`, `del /f`, and similar commands are **always blocked**.
- `write_file` and `run_command` ask for `y/n` confirmation (unless `--yes` is set).
- Tool output is truncated at 5 000 characters to protect the context window.
- Max 15 steps per task to prevent runaway loops.

---

## License

MIT
