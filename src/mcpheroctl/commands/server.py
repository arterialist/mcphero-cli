"""Server management commands for mcpheroctl."""

from __future__ import annotations

from typing import Annotated

import typer

from mcpheroctl.core.client import APIError, MCPHeroClient
from mcpheroctl.core.output import (
    EXIT_GENERAL_FAILURE,
    EXIT_NOT_FOUND,
    die,
    print_result,
    success,
)

server_app = typer.Typer(
    name="server",
    help="Manage MCP servers.",
    no_args_is_help=True,
)


def _client() -> MCPHeroClient:
    return MCPHeroClient()


def _handle_api_error(exc: APIError, *, use_json: bool) -> None:
    """Translate APIError into a structured exit."""
    code = EXIT_GENERAL_FAILURE
    error_type = "api_error"
    if exc.status_code == 404:
        code = EXIT_NOT_FOUND
        error_type = "not_found"
    elif exc.status_code in (401, 403):
        code = 4
        error_type = "permission_denied"
    elif exc.status_code == 409:
        code = 5
        error_type = "conflict"
    die(
        exc.detail,
        code=code,
        error_type=error_type,
        details={"status_code": exc.status_code},
        use_json=use_json,
    )


@server_app.command("list")
def list_servers(
    customer_id: Annotated[
        str, typer.Argument(help="Customer UUID to list servers for.")
    ],
    output_json: Annotated[
        bool, typer.Option("--json", help="Output result as JSON.")
    ] = False,
) -> None:
    """List all MCP servers for a customer.

    Examples:
        mcpheroctl server list 550e8400-e29b-41d4-a716-446655440000
        mcpheroctl server list 550e8400-e29b-41d4-a716-446655440000 --json
    """
    try:
        result = _client().list_servers(customer_id)
        print_result(result, use_json=output_json)
    except APIError as exc:
        _handle_api_error(exc, use_json=output_json)


@server_app.command("get")
def get_server(
    server_id: Annotated[str, typer.Argument(help="Server UUID.")],
    output_json: Annotated[
        bool, typer.Option("--json", help="Output result as JSON.")
    ] = False,
) -> None:
    """Get full details of an MCP server.

    Examples:
        mcpheroctl server get 550e8400-e29b-41d4-a716-446655440000
        mcpheroctl server get 550e8400-e29b-41d4-a716-446655440000 --json
    """
    try:
        result = _client().get_server(server_id)
        print_result(result, use_json=output_json)
    except APIError as exc:
        _handle_api_error(exc, use_json=output_json)


@server_app.command("delete")
def delete_server(
    server_id: Annotated[str, typer.Argument(help="Server UUID to delete.")],
    yes: Annotated[
        bool, typer.Option("--yes", "-y", help="Skip confirmation prompt.")
    ] = False,
    output_json: Annotated[
        bool, typer.Option("--json", help="Output result as JSON.")
    ] = False,
) -> None:
    """Delete an MCP server and all its resources.

    This is a destructive operation. Use --yes to skip the confirmation prompt
    (required for non-interactive / agent usage).

    Examples:
        mcpheroctl server delete 550e8400-e29b-41d4-a716-446655440000 --yes
        mcpheroctl server delete 550e8400-e29b-41d4-a716-446655440000 --yes --json
    """
    if not yes:
        confirm = typer.confirm(f"Delete server {server_id}? This cannot be undone")
        if not confirm:
            raise typer.Abort()
    try:
        result = _client().delete_server(server_id)
        if output_json:
            print_result(result, use_json=True)
        else:
            success(f"Server {server_id} deleted.")
    except APIError as exc:
        _handle_api_error(exc, use_json=output_json)


@server_app.command("update")
def update_server(
    server_id: Annotated[str, typer.Argument(help="Server UUID to update.")],
    name: Annotated[str | None, typer.Option("--name", help="New server name.")] = None,
    description: Annotated[
        str | None, typer.Option("--description", help="New server description.")
    ] = None,
    output_json: Annotated[
        bool, typer.Option("--json", help="Output result as JSON.")
    ] = False,
) -> None:
    """Update an MCP server's name or description.

    Examples:
        mcpheroctl server update 550e8400-... --name "My Server"
        mcpheroctl server update 550e8400-... --description "Does X, Y, Z" --json
    """
    if name is None and description is None:
        die(
            "At least one of --name or --description is required.",
            code=2,
            use_json=output_json,
        )
    try:
        result = _client().update_server(server_id, name=name, description=description)
        if output_json:
            print_result(result, use_json=True)
        else:
            success(f"Server {server_id} updated.")
    except APIError as exc:
        _handle_api_error(exc, use_json=output_json)


@server_app.command("api-key")
def get_api_key(
    server_id: Annotated[str, typer.Argument(help="Server UUID.")],
    output_json: Annotated[
        bool, typer.Option("--json", help="Output result as JSON.")
    ] = False,
) -> None:
    """Get the API key for a server.

    Examples:
        mcpheroctl server api-key 550e8400-e29b-41d4-a716-446655440000
        mcpheroctl server api-key 550e8400-e29b-41d4-a716-446655440000 --json
    """
    try:
        result = _client().get_server_api_key(server_id)
        print_result(result, use_json=output_json)
    except APIError as exc:
        _handle_api_error(exc, use_json=output_json)
