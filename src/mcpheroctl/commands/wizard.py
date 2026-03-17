"""Wizard commands for mcpheroctl.

Covers the full MCP server creation wizard pipeline:
  0a. create-session  – create a session and get server_id
  0b. conversation    – chat with AI to gather requirements
  1. start            – transition to tool suggestion (requires readiness)
  2. list-tools       – view suggested/current tools
  3. refine-tools     – refine tools via LLM with feedback
  4. submit-tools     – select tools to keep
  5. suggest-env-vars – trigger env var suggestion
  6. list-env-vars    – view suggested env vars
  7. refine-env-vars  – refine env vars via LLM
  8. submit-env-vars  – provide env var values
  9. set-auth         – generate bearer token
 10. generate-code    – generate tool implementation code
 11. regenerate-tool-code – regenerate code for a single tool
 12. deploy           – deploy to shared runtime
 13. state            – poll current wizard state
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Annotated

import typer

from mcpheroctl.core.client import APIError, MCPHeroClient
from mcpheroctl.core.output import (
    EXIT_GENERAL_FAILURE,
    EXIT_NOT_FOUND,
    die,
    info,
    print_result,
    success,
)

_MARKER_PATTERN = re.compile(
    r"---TECHNICAL_DETAILS---.*?---END_TECHNICAL_DETAILS---|"
    r"---READY_TO_START---.*?---END_READY---",
    re.DOTALL,
)

wizard_app = typer.Typer(
    name="wizard",
    help="MCP server creation wizard pipeline.",
    no_args_is_help=True,
    rich_markup_mode=None,
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


# ---------------------------------------------------------------------------
# Step 0a: Create session
# ---------------------------------------------------------------------------


@wizard_app.command("create-session")
def create_session(
    customer_id: Annotated[
        str | None,
        typer.Option(
            "--customer-id",
            "-c",
            help="Customer UUID (optional when using org API key).",
        ),
    ] = None,
    output_json: Annotated[
        bool, typer.Option("--json", help="Output result as JSON.")
    ] = False,
) -> None:
    """Create a new wizard session and return a server_id.

    This is Step 0a of the wizard. After creating a session, use
    `wizard conversation` to chat with the AI and gather requirements,
    then `wizard start` once the AI indicates readiness.

    Examples:
        mcpheroctl wizard create-session
        mcpheroctl wizard create-session --customer-id 550e8400-e29b-41d4-a716-446655440000
        mcpheroctl wizard create-session --json
    """
    try:
        result = _client().wizard_create_session(customer_id)
        if output_json:
            print_result(result, use_json=True)
        else:
            server_id = result.get("server_id", "unknown")
            success(f"Session created. Server ID: {server_id}")
            info(
                "Use `wizard conversation SERVER_ID -m 'your message'` to start chatting."
            )
    except APIError as exc:
        _handle_api_error(exc, use_json=output_json)


# ---------------------------------------------------------------------------
# Step 0b: Conversation
# ---------------------------------------------------------------------------


@wizard_app.command("conversation")
def conversation(
    server_id: Annotated[str, typer.Argument(help="Server UUID.")],
    message: Annotated[
        str,
        typer.Option("--message", "-m", help="Message to send to the AI."),
    ],
    output_json: Annotated[
        bool, typer.Option("--json", help="Output result as JSON.")
    ] = False,
) -> None:
    """Send a message in the wizard requirements-gathering chat.

    Iterate on server requirements with the AI until it indicates readiness,
    then run `wizard start SERVER_ID` to kick off tool suggestion.

    Marker blocks (TECHNICAL_DETAILS, READY_TO_START) are stripped from the
    displayed content – they are persisted in the database automatically.

    Examples:
        mcpheroctl wizard conversation SERVER_ID -m "I want a GitHub integration tool"
        mcpheroctl wizard conversation SERVER_ID --message "Add webhook support" --json
    """
    try:
        result = _client().wizard_chat(server_id, message)
        raw_content: str = result.get("content", "")
        is_ready: bool = result.get("is_ready", False)
        cleaned = _MARKER_PATTERN.sub("", raw_content).strip()

        if output_json:
            print_result(
                {"server_id": server_id, "content": cleaned, "is_ready": is_ready},
                use_json=True,
            )
        else:
            info(cleaned)
            if is_ready:
                success(
                    "The AI has gathered enough information. Run `wizard start SERVER_ID` to proceed."
                )
    except APIError as exc:
        _handle_api_error(exc, use_json=output_json)


# ---------------------------------------------------------------------------
# Step 1: Start wizard (transition to tool suggestion)
# ---------------------------------------------------------------------------


@wizard_app.command("start")
def start(
    server_id: Annotated[
        str, typer.Argument(help="Server UUID (from create-session).")
    ],
    spec: Annotated[
        Path | None,
        typer.Option(
            "--spec",
            "-f",
            help="Optional markdown file to override the description from chat.",
            exists=True,
            readable=True,
        ),
    ] = None,
    technical_details: Annotated[
        list[Path] | None,
        typer.Option(
            "--technical-details",
            "-d",
            help="Path(s) to markdown files with technical details (API specs, schemas, etc.). Can be repeated.",
            exists=True,
            readable=True,
        ),
    ] = None,
    output_json: Annotated[
        bool, typer.Option("--json", help="Output result as JSON.")
    ] = False,
) -> None:
    """Transition from requirements gathering to tool suggestion.

    The server must be in gathering_requirements state and the AI must have
    indicated readiness (conversation returned is_ready=True). Optionally
    override the description with --spec or add technical details with -d.

    Examples:
        mcpheroctl wizard start SERVER_ID
        mcpheroctl wizard start SERVER_ID --spec override.md
        mcpheroctl wizard start SERVER_ID -d api_schema.md -d endpoints.md
    """
    description: str | None = spec.read_text() if spec else None
    tech_details: list[str] | None = None
    if technical_details:
        tech_details = [p.read_text() for p in technical_details]

    try:
        result = _client().wizard_start(server_id, description, tech_details)
        if output_json:
            print_result(result, use_json=True)
        else:
            success(f"Wizard started. Server ID: {server_id}")
            info(
                "Tool suggestion is running in the background. Poll with `wizard state`."
            )
    except APIError as exc:
        _handle_api_error(exc, use_json=output_json)


# ---------------------------------------------------------------------------
# Step 1 tools management
# ---------------------------------------------------------------------------


@wizard_app.command("list-tools")
def list_tools(
    server_id: Annotated[str, typer.Argument(help="Server UUID.")],
    output_json: Annotated[
        bool, typer.Option("--json", help="Output result as JSON.")
    ] = False,
) -> None:
    """List current tools for a server in the wizard.

    Examples:
        mcpheroctl wizard list-tools SERVER_ID
        mcpheroctl wizard list-tools SERVER_ID --json
    """
    try:
        result = _client().wizard_get_tools(server_id)
        print_result(result, use_json=output_json)
    except APIError as exc:
        _handle_api_error(exc, use_json=output_json)


@wizard_app.command("refine-tools")
def refine_tools(
    server_id: Annotated[str, typer.Argument(help="Server UUID.")],
    feedback: Annotated[
        str, typer.Option("--feedback", "-f", help="Feedback text for LLM refinement.")
    ],
    tool_id: Annotated[
        list[str] | None,
        typer.Option(
            "--tool-id",
            help="Tool UUID(s) to refine. Can be repeated. Omit to refine all.",
        ),
    ] = None,
    output_json: Annotated[
        bool, typer.Option("--json", help="Output result as JSON.")
    ] = False,
) -> None:
    """Refine suggested tools based on feedback.

    Triggers an LLM refinement in the background. Pass --tool-id multiple
    times to target specific tools, or omit to refine all.

    Examples:
        mcpheroctl wizard refine-tools SERVER_ID --feedback "Add a search tool"
        mcpheroctl wizard refine-tools SERVER_ID -f "Split into two" --tool-id UUID1 --tool-id UUID2
        mcpheroctl wizard refine-tools SERVER_ID -f "Simplify parameters" --json
    """
    try:
        result = _client().wizard_refine_tools(server_id, feedback, tool_id)
        if output_json:
            print_result(result, use_json=True)
        else:
            success("Tool refinement started. Poll with `wizard state`.")
    except APIError as exc:
        _handle_api_error(exc, use_json=output_json)


@wizard_app.command("submit-tools")
def submit_tools(
    server_id: Annotated[str, typer.Argument(help="Server UUID.")],
    tool_id: Annotated[
        list[str],
        typer.Option("--tool-id", help="Tool UUID(s) to keep. Can be repeated."),
    ],
    output_json: Annotated[
        bool, typer.Option("--json", help="Output result as JSON.")
    ] = False,
) -> None:
    """Submit selected tools to proceed to env vars step.

    Pass --tool-id for each tool to keep. Unselected tools are deleted.

    Examples:
        mcpheroctl wizard submit-tools SERVER_ID --tool-id UUID1 --tool-id UUID2
        mcpheroctl wizard submit-tools SERVER_ID --tool-id UUID1 --json
    """
    try:
        result = _client().wizard_submit_tools(server_id, tool_id)
        if output_json:
            print_result(result, use_json=True)
        else:
            success(f"Submitted {len(tool_id)} tool(s). Env var suggestion started.")
    except APIError as exc:
        _handle_api_error(exc, use_json=output_json)


# ---------------------------------------------------------------------------
# Step 2: Environment variables
# ---------------------------------------------------------------------------


@wizard_app.command("suggest-env-vars")
def suggest_env_vars(
    server_id: Annotated[str, typer.Argument(help="Server UUID.")],
    output_json: Annotated[
        bool, typer.Option("--json", help="Output result as JSON.")
    ] = False,
) -> None:
    """Trigger environment variable suggestion via LLM.

    Examples:
        mcpheroctl wizard suggest-env-vars SERVER_ID
        mcpheroctl wizard suggest-env-vars SERVER_ID --json
    """
    try:
        result = _client().wizard_suggest_env_vars(server_id)
        if output_json:
            print_result(result, use_json=True)
        else:
            success("Env var suggestion started. Poll with `wizard state`.")
    except APIError as exc:
        _handle_api_error(exc, use_json=output_json)


@wizard_app.command("list-env-vars")
def list_env_vars(
    server_id: Annotated[str, typer.Argument(help="Server UUID.")],
    output_json: Annotated[
        bool, typer.Option("--json", help="Output result as JSON.")
    ] = False,
) -> None:
    """List current environment variables for a server.

    Examples:
        mcpheroctl wizard list-env-vars SERVER_ID
        mcpheroctl wizard list-env-vars SERVER_ID --json
    """
    try:
        result = _client().wizard_get_env_vars(server_id)
        print_result(result, use_json=output_json)
    except APIError as exc:
        _handle_api_error(exc, use_json=output_json)


@wizard_app.command("refine-env-vars")
def refine_env_vars(
    server_id: Annotated[str, typer.Argument(help="Server UUID.")],
    feedback: Annotated[
        str, typer.Option("--feedback", "-f", help="Feedback text for LLM refinement.")
    ],
    output_json: Annotated[
        bool, typer.Option("--json", help="Output result as JSON.")
    ] = False,
) -> None:
    """Refine suggested environment variables based on feedback.

    Triggers an LLM refinement in the background.

    Examples:
        mcpheroctl wizard refine-env-vars SERVER_ID -f "Combine DB vars into DATABASE_URL"
        mcpheroctl wizard refine-env-vars SERVER_ID --feedback "Add API key var" --json
    """
    try:
        result = _client().wizard_refine_env_vars(server_id, feedback)
        if output_json:
            print_result(result, use_json=True)
        else:
            success("Env var refinement started. Poll with `wizard state`.")
    except APIError as exc:
        _handle_api_error(exc, use_json=output_json)


@wizard_app.command("submit-env-vars")
def submit_env_vars(
    server_id: Annotated[str, typer.Argument(help="Server UUID.")],
    var: Annotated[
        list[str],
        typer.Option("--var", help="Env var value as VAR_UUID=VALUE. Can be repeated."),
    ],
    output_json: Annotated[
        bool, typer.Option("--json", help="Output result as JSON.")
    ] = False,
) -> None:
    """Submit environment variable values.

    Pass --var for each variable in the format UUID=VALUE.

    Examples:
        mcpheroctl wizard submit-env-vars SERVER_ID --var "UUID1=sk-abc123" --var "UUID2=https://api.example.com"
        mcpheroctl wizard submit-env-vars SERVER_ID --var "UUID1=value1" --json
    """
    values: dict[str, str] = {}
    for v in var:
        if "=" not in v:
            die(
                f"Invalid --var format: '{v}'. Expected VAR_UUID=VALUE.",
                code=2,
                use_json=output_json,
            )
        key, val = v.split("=", 1)
        values[key.strip()] = val.strip()

    try:
        result = _client().wizard_submit_env_vars(server_id, values)
        if output_json:
            print_result(result, use_json=True)
        else:
            success(f"Submitted {len(values)} env var value(s).")
    except APIError as exc:
        _handle_api_error(exc, use_json=output_json)


# ---------------------------------------------------------------------------
# Step 3: Auth
# ---------------------------------------------------------------------------


@wizard_app.command("set-auth")
def set_auth(
    server_id: Annotated[str, typer.Argument(help="Server UUID.")],
    output_json: Annotated[
        bool, typer.Option("--json", help="Output result as JSON.")
    ] = False,
) -> None:
    """Set up bearer token authentication for the server.

    Generates and returns a Bearer token.

    Examples:
        mcpheroctl wizard set-auth SERVER_ID
        mcpheroctl wizard set-auth SERVER_ID --json
    """
    try:
        result = _client().wizard_set_auth(server_id)
        if output_json:
            print_result(result, use_json=True)
        else:
            token = result.get("bearer_token", "")
            success(f"Auth set. Bearer token: {token}")
    except APIError as exc:
        _handle_api_error(exc, use_json=output_json)


# ---------------------------------------------------------------------------
# Step 4: Code generation
# ---------------------------------------------------------------------------


@wizard_app.command("generate-code")
def generate_code(
    server_id: Annotated[str, typer.Argument(help="Server UUID.")],
    output_json: Annotated[
        bool, typer.Option("--json", help="Output result as JSON.")
    ] = False,
) -> None:
    """Trigger code generation for all tools.

    Runs in the background. Poll with `wizard state` to check progress.

    Examples:
        mcpheroctl wizard generate-code SERVER_ID
        mcpheroctl wizard generate-code SERVER_ID --json
    """
    try:
        result = _client().wizard_generate_code(server_id)
        if output_json:
            print_result(result, use_json=True)
        else:
            success("Code generation started. Poll with `wizard state`.")
    except APIError as exc:
        _handle_api_error(exc, use_json=output_json)


@wizard_app.command("regenerate-tool-code")
def regenerate_tool_code(
    server_id: Annotated[str, typer.Argument(help="Server UUID.")],
    tool_id: Annotated[str, typer.Argument(help="Tool UUID to regenerate code for.")],
    output_json: Annotated[
        bool, typer.Option("--json", help="Output result as JSON.")
    ] = False,
) -> None:
    """Regenerate code for a single tool (synchronous).

    Waits for LLM to produce new code and returns it.

    Examples:
        mcpheroctl wizard regenerate-tool-code SERVER_ID TOOL_ID
        mcpheroctl wizard regenerate-tool-code SERVER_ID TOOL_ID --json
    """
    try:
        result = _client().wizard_regenerate_tool_code(server_id, tool_id)
        if output_json:
            print_result(result, use_json=True)
        else:
            success(f"Code regenerated for tool {tool_id}.")
            code = result.get("code", "")
            if code:
                info(f"Generated code:\n{code}")
    except APIError as exc:
        _handle_api_error(exc, use_json=output_json)


# ---------------------------------------------------------------------------
# Step 5: Deploy
# ---------------------------------------------------------------------------


@wizard_app.command("deploy")
def deploy(
    server_id: Annotated[str, typer.Argument(help="Server UUID.")],
    output_json: Annotated[
        bool, typer.Option("--json", help="Output result as JSON.")
    ] = False,
) -> None:
    """Deploy the MCP server to the shared runtime.

    Examples:
        mcpheroctl wizard deploy SERVER_ID
        mcpheroctl wizard deploy SERVER_ID --json
    """
    try:
        result = _client().wizard_deploy(server_id)
        if output_json:
            print_result(result, use_json=True)
        else:
            url = result.get("server_url", "")
            success(f"Deployed! Endpoint: {url}")
    except APIError as exc:
        _handle_api_error(exc, use_json=output_json)


# ---------------------------------------------------------------------------
# State polling
# ---------------------------------------------------------------------------


@wizard_app.command("state")
def state(
    server_id: Annotated[str, typer.Argument(help="Server UUID.")],
    output_json: Annotated[
        bool, typer.Option("--json", help="Output result as JSON.")
    ] = False,
) -> None:
    """Get the current wizard state for a server.

    Useful for polling during background operations (tool suggestion,
    code generation, etc.).

    Examples:
        mcpheroctl wizard state SERVER_ID
        mcpheroctl wizard state SERVER_ID --json
    """
    try:
        result = _client().wizard_get_state(server_id)
        print_result(result, use_json=output_json)
    except APIError as exc:
        _handle_api_error(exc, use_json=output_json)
