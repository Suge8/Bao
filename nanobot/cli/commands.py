"""CLI commands for nanobot."""

import asyncio
import atexit
import os
import signal
import sys
from pathlib import Path
import select

import typer
from rich.console import Console
from rich.markdown import Markdown
from rich.panel import Panel
from rich.table import Table
from rich.text import Text

from nanobot import __version__, __logo__

app = typer.Typer(
    name="nanobot",
    help=f"{__logo__} nanobot - Personal AI Assistant",
    no_args_is_help=True,
)

console = Console()
EXIT_COMMANDS = {"exit", "quit", "/exit", "/quit", ":q"}

# ---------------------------------------------------------------------------
# Lightweight CLI input: readline for arrow keys / history, termios for flush
# ---------------------------------------------------------------------------

_READLINE = None
_HISTORY_FILE: Path | None = None
_HISTORY_HOOK_REGISTERED = False
_USING_LIBEDIT = False
_SAVED_TERM_ATTRS = None  # original termios settings, restored on exit


def _flush_pending_tty_input() -> None:
    """Drop unread keypresses typed while the model was generating output."""
    try:
        fd = sys.stdin.fileno()
        if not os.isatty(fd):
            return
    except Exception:
        return

    try:
        import termios
        termios.tcflush(fd, termios.TCIFLUSH)
        return
    except Exception:
        pass

    try:
        while True:
            ready, _, _ = select.select([fd], [], [], 0)
            if not ready:
                break
            if not os.read(fd, 4096):
                break
    except Exception:
        return


def _save_history() -> None:
    if _READLINE is None or _HISTORY_FILE is None:
        return
    try:
        _READLINE.write_history_file(str(_HISTORY_FILE))
    except Exception:
        return


def _restore_terminal() -> None:
    """Restore terminal to its original state (echo, line buffering, etc.)."""
    if _SAVED_TERM_ATTRS is None:
        return
    try:
        import termios
        termios.tcsetattr(sys.stdin.fileno(), termios.TCSADRAIN, _SAVED_TERM_ATTRS)
    except Exception:
        pass


def _enable_line_editing() -> None:
    """Enable readline for arrow keys, line editing, and persistent history."""
    global _READLINE, _HISTORY_FILE, _HISTORY_HOOK_REGISTERED, _USING_LIBEDIT, _SAVED_TERM_ATTRS

    # Save terminal state before readline touches it
    try:
        import termios
        _SAVED_TERM_ATTRS = termios.tcgetattr(sys.stdin.fileno())
    except Exception:
        pass

    try:
        import readline as _READLINE
        import atexit

        # Detect libedit (macOS) vs GNU readline (Linux)
        if hasattr(_READLINE, "__doc__") and _READLINE.__doc__ and "libedit" in _READLINE.__doc__:
            _USING_LIBEDIT = True

        hist_file = Path.home() / ".nanobot_history"
        _HISTORY_FILE = hist_file
        try:
            _READLINE.read_history_file(str(hist_file))
        except FileNotFoundError:
            pass

        # Enable common readline settings
        _READLINE.parse_and_bind("bind -v" if _USING_LIBEDIT else "set editing-mode vi")
        _READLINE.parse_and_bind("set show-all-if-ambiguous on")
        _READLINE.parse_and_bind("set colored-completion-prefix on")

        if not _HISTORY_HOOK_REGISTERED:
            atexit.register(_save_history)
            _HISTORY_HOOK_REGISTERED = True
    except Exception:
        return


async def _read_interactive_input_async() -> str:
    """Async wrapper around synchronous input() (runs in thread pool)."""
    loop = asyncio.get_running_loop()
    return await loop.run_in_executor(None, lambda: input(f"{__logo__} "))


def _is_exit_command(text: str) -> bool:
    return text.strip().lower() in EXIT_COMMANDS


# ---------------------------------------------------------------------------
# OAuth and Authentication helpers
# ---------------------------------------------------------------------------

def _handle_oauth_login(provider: str) -> None:
    """Handle OAuth login flow for supported providers."""
    from nanobot.providers.registry import get_oauth_handler
    
    oauth_handler = get_oauth_handler(provider)
    if oauth_handler is None:
        console.print(f"[red]OAuth is not supported for provider: {provider}[/red]")
        console.print("[yellow]Supported OAuth providers: github-copilot[/yellow]")
        raise typer.Exit(1)
    
    try:
        result = oauth_handler.authenticate()
        if result.success:
            console.print(f"[green]✓ {result.message}[/green]")
            if result.token_path:
                console.print(f"[dim]Token saved to: {result.token_path}[/dim]")
        else:
            console.print(f"[red]✗ {result.message}[/red]")
            raise typer.Exit(1)
    except Exception as e:
        console.print(f"[red]OAuth authentication failed: {e}[/red]")
        raise typer.Exit(1)


# ---------------------------------------------------------------------------
# @agent decorator and public API helpers
# ---------------------------------------------------------------------------

_agent_registry: dict[str, callable] = {}


def _get_agent(name: str | None = None) -> callable | None:
    """Retrieve a registered agent function by name."""
    if name is None:
        # Return the first registered agent if no name specified
        return next(iter(_agent_registry.values())) if _agent_registry else None
    return _agent_registry.get(name)


def agent(name: str | None = None, model: str | None = None, prompt: str | None = None):
    """Decorator to register an agent function.
    
    Args:
        name: Optional name for the agent (defaults to function name)
        model: Optional model override (e.g., "gpt-4o", "claude-3-opus")
        prompt: Optional system prompt for the agent
    """
    def decorator(func):
        agent_name = name or func.__name__
        _agent_registry[agent_name] = func
        func._agent_config = {"model": model, "prompt": prompt}
        return func
    return decorator


# ---------------------------------------------------------------------------
# Built-in CLI commands
# ---------------------------------------------------------------------------

@app.command()
def login(
    provider: str = typer.Argument(..., help="Provider to authenticate with (e.g., 'github-copilot')"),
):
    """Authenticate with an OAuth provider."""
    _handle_oauth_login(provider)


@app.command()
def version():
    """Show version information."""
    console.print(f"{__logo__} nanobot {__version__}")


@app.command(name="agent")
def run_agent(
    name: str | None = typer.Argument(None, help="Name of the agent to run"),
    message: str = typer.Option(None, "--message", "-m", help="Single message to send to the agent"),
    model: str = typer.Option(None, "--model", help="Override the model for this run"),
    markdown: bool = typer.Option(True, "--markdown/--no-markdown", help="Render response as markdown"),
    session_id: str = typer.Option("cli", "--session", "-s", help="Session ID for this conversation"),
):
    """Run an interactive AI agent session."""
    import asyncio
    from nanobot.agent.loop import AgentLoop
    
    # Get the agent function
    agent_func = _get_agent(name)
    if agent_func is None:
        if name:
            console.print(f"[red]Agent '{name}' not found[/red]")
        else:
            console.print("[yellow]No agents registered. Use @agent decorator to register agents.[/yellow]")
        raise typer.Exit(1)
    
    # Initialize agent loop
    agent_config = getattr(agent_func, '_agent_config', {})
    agent_model = model or agent_config.get('model')
    agent_prompt = agent_config.get('prompt')
    
    agent_loop = AgentLoop(model=agent_model, system_prompt=agent_prompt)
    
    if message:
        # Single message mode
        async def run_once():
            with _thinking_ctx():
                response = await agent_loop.process_direct(message, session_id)
            _print_agent_response(response, render_markdown=markdown)
        
        asyncio.run(run_once())
    else:
        # Interactive mode
        _enable_line_editing()
        console.print(f"{__logo__} Interactive mode (type [bold]exit[/bold] or [bold]Ctrl+C[/bold] to quit)\n")

        # input() runs in a worker thread that can't be cancelled.
        # Without this handler, asyncio.run() would hang waiting for it.
        def _exit_on_sigint(signum, frame):
            _save_history()
            _restore_terminal()
            console.print("\nGoodbye!")
            os._exit(0)

        signal.signal(signal.SIGINT, _exit_on_sigint)
        
        async def run_interactive():
            while True:
                try:
                    _flush_pending_tty_input()
                    user_input = await _read_interactive_input_async()
                    command = user_input.strip()
                    if not command:
                        continue

                    if _is_exit_command(command):
                        _save_history()
                        _restore_terminal()
                        console.print("\nGoodbye!")
                        break
                    
                    with _thinking_ctx():
                        response = await agent_loop.process_direct(user_input, session_id)
                    _print_agent_response(response, render_markdown=markdown)
                except KeyboardInterrupt:
                    _save_history()
                    _restore_terminal()
                    console.print("\nGoodbye!")
                    break
        
        asyncio.run(run_interactive())


def _thinking_ctx():
    """Context manager for showing thinking indicator."""
    from rich.live import Live
    from rich.spinner import Spinner
    
    class ThinkingSpinner:
        def __enter__(self):
            self.live = Live(Spinner("dots", text="Thinking..."), console=console, refresh_per_second=10)
            self.live.start()
            return self
        
        def __exit__(self, exc_type, exc_val, exc_tb):
            self.live.stop()
            return False
    
    return ThinkingSpinner()


def _print_agent_response(response: str, render_markdown: bool = True):
    """Print agent response with optional markdown rendering."""
    if render_markdown:
        console.print(Markdown(response))
    else:
        console.print(response)
    console.print()


@app.command()
def setup():
    """Interactive setup wizard for nanobot."""
    console.print(Panel.fit(
        f"{__logo__} Welcome to nanobot setup!\n\n"
        "This wizard will help you configure nanobot.",
        title="Setup",
        border_style="green"
    ))
    
    # TODO: Implement setup wizard
    console.print("[yellow]Setup wizard coming soon![/yellow]")


def main():
    """Main entry point for the CLI."""
    app()


if __name__ == "__main__":
    main()
