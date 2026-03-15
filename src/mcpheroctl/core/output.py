"""Structured output helpers for agent-first CLI design.

Rules:
- JSON to stdout, everything else to stderr.
- Meaningful exit codes (not just 0/1).
- Actionable error messages with error codes.
"""

from __future__ import annotations

import json
import sys
from typing import Any, NoReturn

from rich.console import Console

# Rich console for human-readable stderr messages
err_console = Console(stderr=True)

# ---------------------------------------------------------------------------
# Exit codes (documented in --help)
# ---------------------------------------------------------------------------
EXIT_SUCCESS = 0
EXIT_GENERAL_FAILURE = 1
EXIT_USAGE_ERROR = 2
EXIT_NOT_FOUND = 3
EXIT_PERMISSION_DENIED = 4
EXIT_CONFLICT = 5
EXIT_NOT_IMPLEMENTED = 6


# ---------------------------------------------------------------------------
# Output helpers
# ---------------------------------------------------------------------------


def print_json(data: Any) -> None:
    """Print structured JSON to stdout."""
    if hasattr(data, "model_dump"):
        data = data.model_dump(mode="json")
    json.dump(data, sys.stdout, indent=2, default=str)
    _ = sys.stdout.write("\n")  # noqa: F821


def print_result(data: Any, *, use_json: bool) -> None:
    """Print *data* as JSON (stdout) or as a human table (stderr).

    When *use_json* is False we still pretty-print via Rich to stderr so that
    stdout stays clean for piping.
    """
    if use_json:
        print_json(data)
    else:
        if hasattr(data, "model_dump"):
            data = data.model_dump(mode="json")
        err_console.print_json(data=data)


def info(message: str) -> None:
    """Print an informational message to stderr."""
    err_console.print(f"[bold blue]ℹ[/] {message}")


def success(message: str) -> None:
    """Print a success message to stderr."""
    err_console.print(f"[bold green]✔[/] {message}")


def warn(message: str) -> None:
    """Print a warning message to stderr."""
    err_console.print(f"[bold yellow]⚠[/] {message}")


def error_msg(message: str) -> None:
    """Print an error message to stderr (does not exit)."""
    err_console.print(f"[bold red]✖[/] {message}")


def die(
    message: str,
    *,
    code: int = EXIT_GENERAL_FAILURE,
    error_type: str | None = None,
    details: dict[str, Any] | None = None,
    use_json: bool = False,
) -> NoReturn:
    """Print an error and exit with the given code.

    When *use_json* is True, a structured error object is emitted to stdout
    (matching agent-first guidelines rule 7).
    """
    if use_json:
        payload: dict[str, Any] = {
            "error": error_type or "error",
            "message": message,
        }
        if details:
            payload.update(details)
        print_json(payload)
    else:
        error_msg(message)

    raise SystemExit(code)
