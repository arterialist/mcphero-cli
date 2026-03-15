"""Auth commands for mcpheroctl."""

from __future__ import annotations

from typing import Annotated

import typer

from mcpheroctl.core.config import Config, load_config, save_config
from mcpheroctl.core.output import die, info, print_result, success

auth_app = typer.Typer(
    name="auth",
    help="Manage API authentication.",
    no_args_is_help=True,
)


@auth_app.command("login")
def login(
    token: Annotated[
        str, typer.Option("--token", "-t", help="Organization API token.", prompt=False)
    ],
    base_url: Annotated[
        str | None, typer.Option("--base-url", help="Override the API base URL.")
    ] = None,
    output_json: Annotated[
        bool, typer.Option("--json", help="Output result as JSON.")
    ] = False,
) -> None:
    """Authenticate with the MCPHero API using an organization API token.

    Saves the token to ~/.config/mcpheroctl/config.json for future use.

    Examples:
        mcpheroctl auth login --token myorg_sk_abc123
        mcpheroctl auth login --token myorg_sk_abc123 --base-url https://custom.api.com/api
    """
    config: Config = load_config()
    config.api_token = token
    if base_url is not None:
        config.base_url = base_url
    save_config(config)
    if output_json:
        print_result(
            {"status": "authenticated", "base_url": config.base_url}, use_json=True
        )
        return

    success(f"Token saved. API: {config.base_url}")


@auth_app.command("status")
def status(
    output_json: Annotated[
        bool, typer.Option("--json", help="Output result as JSON.")
    ] = False,
) -> None:
    """Check current authentication status.

    Examples:
        mcpheroctl auth status
        mcpheroctl auth status --json
    """
    config: Config = load_config()
    is_authenticated: bool = config.api_token is not None
    if output_json:
        print_result(
            {
                "authenticated": is_authenticated,
                "base_url": config.base_url,
                "token_preview": f"...{config.api_token[-8:]}"
                if config.api_token
                else None,
            },
            use_json=True,
        )
        return

    if is_authenticated:
        success(f"Authenticated (token: ...{config.api_token[-8:]})")  # pyright: ignore[reportOptionalSubscript]
        info(f"API: {config.base_url}")
        return

    die("Not authenticated. Run `mcpheroctl auth login --token <TOKEN>`.", code=4)


@auth_app.command("logout")
def logout(
    output_json: Annotated[
        bool, typer.Option("--json", help="Output result as JSON.")
    ] = False,
) -> None:
    """Remove stored credentials.

    Examples:
        mcpheroctl auth logout
        mcpheroctl auth logout --json
    """
    config: Config = load_config()
    config.api_token = None
    save_config(config)
    if output_json:
        print_result({"status": "logged_out"}, use_json=True)
        return

    success("Credentials removed.")
