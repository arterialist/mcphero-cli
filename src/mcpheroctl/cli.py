"""mcpheroctl – CLI tool for interacting with the MCPHero platform.

Designed for both human operators and AI agent workflows.
Follows the agent-first CLI guidelines: structured JSON output,
meaningful exit codes, noun-verb grammar, and actionable errors.

Exit codes:
    0  success
    1  general failure
    2  usage error (bad arguments)
    3  resource not found
    4  permission denied / not authenticated
    5  conflict (resource already exists)
    6  not implemented
"""

from __future__ import annotations

import typer

from mcpheroctl import __version__
from mcpheroctl.commands.auth import auth_app
from mcpheroctl.commands.server import server_app
from mcpheroctl.commands.wizard import wizard_app

app = typer.Typer(
    name="mcpheroctl",
    help="CLI tool for interacting with the MCPHero platform.",
    no_args_is_help=True,
    rich_markup_mode="rich",
    add_completion=True,
    pretty_exceptions_enable=False,
)

# Register sub-apps (noun-verb pattern)
app.add_typer(auth_app, name="auth")
app.add_typer(server_app, name="server")
app.add_typer(wizard_app, name="wizard")


def version_callback(value: bool) -> None:
    if value:
        typer.echo(f"mcpheroctl {__version__}")
        raise typer.Exit()


@app.callback()
def main(
    _: bool = typer.Option(  # pyright: ignore[reportCallInDefaultInitializer]
        False,
        "--version",
        "-v",
        help="Show version and exit.",
        callback=version_callback,
        is_eager=True,
    ),
) -> None:
    """MCPHero CLI – manage MCP servers and run the creation wizard.

    Authenticate first with `mcpheroctl auth login --token <TOKEN>`, then
    use `mcpheroctl server` and `mcpheroctl wizard` to interact with the
    platform.

    Use --json on any command for structured JSON output (stdout).
    Human-readable messages go to stderr.
    """
