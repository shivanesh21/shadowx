"""
cli.py — Entry-point for the ShadowX agent.

Provides two modes:
  1. Interactive chat loop:  `shadowx`
  2. One-shot task:          `shadowx "do something"`

Special commands inside the chat loop:
  /help    — show available commands
  /clear   — wipe conversation history
  exit     — quit the loop
"""

import sys
import argparse

from rich.console import Console
from rich.panel import Panel
from rich.rule import Rule

from shadow.agent import run_task, load_history, save_history, clear_history

console = Console()

# ---------------------------------------------------------------------------
# Banner / Help
# ---------------------------------------------------------------------------

BANNER = """
[bold cyan]
  ███████╗██╗  ██╗ █████╗ ██████╗  ██████╗ ██╗    ██╗██╗  ██╗
  ██╔════╝██║  ██║██╔══██╗██╔══██╗██╔═══██╗██║    ██║╚██╗██╔╝
  ███████╗███████║███████║██║  ██║██║   ██║██║ █╗ ██║ ╚███╔╝ 
  ╚════██║██╔══██║██╔══██║██║  ██║██║   ██║██║███╗██║ ██╔██╗ 
  ███████║██║  ██║██║  ██║██████╔╝╚██████╔╝╚███╔███╔╝██╔╝ ██╗
  ╚══════╝╚═╝  ╚═╝╚═╝  ╚═╝╚═════╝  ╚═════╝  ╚══╝╚══╝ ╚═╝  ╚═╝
[/bold cyan]
[dim]  Your AI coding agent in the terminal (ShadowX)[/dim]
"""

HELP_TEXT = """
[bold]Available commands:[/bold]

  [cyan]/help[/cyan]    — Show this help message
  [cyan]/clear[/cyan]   — Clear conversation history (starts fresh)
  [cyan]exit[/cyan]     — Quit ShadowX

[bold]Flags (command-line only):[/bold]

  [cyan]--confirm[/cyan] — Prompt for confirmation before file writes and commands
  [cyan]--fresh[/cyan]   — Ignore saved history and start a new conversation

[bold]Example tasks:[/bold]

  > create a hello.py that prints Hello, World! and run it
  > read main.py and add docstrings to every function
  > list the files here, then create a requirements.txt
"""


def show_banner():
    console.print(BANNER)
    console.print("[dim]Type a task and press Enter.  Type [bold]exit[/bold] to quit, "
                  "[bold]/help[/bold] for commands.[/dim]\n")


def show_help():
    console.print(Panel(HELP_TEXT, title="[bold cyan]ShadowX Help[/bold cyan]",
                        border_style="cyan"))


# ---------------------------------------------------------------------------
# Interactive chat loop
# ---------------------------------------------------------------------------

def interactive_loop(skip_confirm: bool, fresh: bool):
    """Run ShadowX in persistent chat mode."""
    show_banner()

    history = [] if fresh else load_history()

    while True:
        try:
            # Prompt the user
            console.print(Rule(style="dim"))
            task = console.input("[bold green]You >[/bold green] ").strip()
        except (KeyboardInterrupt, EOFError):
            console.print("\n[dim]Bye![/dim]")
            save_history(history)
            break

        if not task:
            continue

        # --- Special commands ---
        if task.lower() == "exit":
            console.print("[dim]Saving history and exiting…[/dim]")
            save_history(history)
            break

        if task.lower() == "/help":
            show_help()
            continue

        if task.lower() == "/clear":
            clear_history()
            history = []
            continue

        # --- Run the task ---
        try:
            history = run_task(task, history, skip_confirm=skip_confirm)
            save_history(history)
        except KeyboardInterrupt:
            console.print("\n[yellow]Task interrupted.[/yellow]")
        except Exception as e:
            console.print(f"[bold red]Error:[/bold red] {e}")


# ---------------------------------------------------------------------------
# One-shot mode
# ---------------------------------------------------------------------------

def one_shot(task: str, skip_confirm: bool, fresh: bool):
    """Run a single task and exit."""
    history = [] if fresh else load_history()
    history = run_task(task, history, skip_confirm=skip_confirm)
    save_history(history)


# ---------------------------------------------------------------------------
# CLI entry-point
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(
        prog="shadowx",
        description="ShadowX — your fast AI coding agent in the terminal.",
    )
    parser.add_argument(
        "task",
        nargs="?",
        default=None,
        help="Task to run (omit for interactive mode).",
    )
    parser.add_argument(
        "--confirm", "-c",
        action="store_true",
        help="Prompt for confirmation before file writes and commands.",
    )
    parser.add_argument(
        "--yes", "-y",
        action="store_true",
        help="Auto-approve all actions (default behavior).",
    )
    parser.add_argument(
        "--fresh",
        action="store_true",
        help="Ignore saved history; start a new conversation.",
    )

    args = parser.parse_args()
    skip_confirm = not args.confirm

    if args.task:
        one_shot(args.task, skip_confirm=skip_confirm, fresh=args.fresh)
    else:
        interactive_loop(skip_confirm=skip_confirm, fresh=args.fresh)


if __name__ == "__main__":
    main()
