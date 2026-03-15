# mcpheroctl

CLI tool for interacting with the [MCPHero](https://mcphero.app) platform — create, manage, and deploy MCP servers via the wizard pipeline.

Designed for both human use and AI agent workflows, following [agent-first CLI](./agent-first-cli-guide.md) principles:
- Structured JSON output to `stdout`; human-readable messages to `stderr`
- Documented, meaningful exit codes
- `--json` flag on every command for scripting / pipeline integration
- Noun-verb command grammar (`mcpheroctl <noun> <verb>`)

---

## Requirements

- Python ≥ 3.12
- [uv](https://docs.astral.sh/uv/) ≥ 0.5

---

## Installation

### From source (recommended while in development)

```bash
git clone git@github.com:arterialist/mcphero-cli.git
cd mcphero-cli
uv sync
uv run mcpheroctl --help
```

### As a pip package (once published)

```bash
pip install mcpheroctl
# or with uv:
uv tool install mcpheroctl
```

---

## Authentication

mcpheroctl uses an **organization API token** stored at `~/.config/mcpheroctl/config.json`.

```bash
mcpheroctl auth login --token <YOUR_ORG_TOKEN>
```

Obtain your token from the MCPHero dashboard. Most commands also accept an optional `--customer-id` / `CUSTOMER_ID` argument; when using an **org API key**, customer context is inferred automatically — passing a customer ID is only required when working with an admin key across multiple customers.

### Auth commands

| Command | Description |
|---------|-------------|
| `mcpheroctl auth login --token TOKEN` | Save API token (optionally `--base-url URL`) |
| `mcpheroctl auth status` | Show current auth state and token preview |
| `mcpheroctl auth logout` | Remove stored credentials |

---

## Configuration

Config is stored at `~/.config/mcpheroctl/config.json`:

```json
{
  "api_token": "your-token-here",
  "base_url": "https://api.mcphero.app/api"
}
```

Override the API endpoint at login time:

```bash
mcpheroctl auth login --token TOKEN --base-url https://staging.mcphero.app/api
```

---

## Server Commands

Manage deployed MCP servers.

```
mcpheroctl server <command>
```

| Command | Description |
|---------|-------------|
| `list [CUSTOMER_ID]` | List all MCP servers (customer optional with org key) |
| `get SERVER_ID` | Get full server details |
| `update SERVER_ID` | Update server `--name` and/or `--description` |
| `delete SERVER_ID --yes` | Delete a server and all resources |
| `api-key SERVER_ID` | Retrieve the server's API key |

### Examples

```bash
# List servers for your org
mcpheroctl server list

# List for a specific customer (admin key)
mcpheroctl server list 550e8400-e29b-41d4-a716-446655440000

# Get details as JSON (for scripting)
mcpheroctl server get SERVER_ID --json

# Update
mcpheroctl server update SERVER_ID --name "My Weather API" --description "Provides weather data"

# Delete (non-interactive)
mcpheroctl server delete SERVER_ID --yes

# Get API key
mcpheroctl server api-key SERVER_ID --json
```

---

## Wizard Commands

The wizard pipeline guides you through creating a new MCP server end-to-end. Each step corresponds to a backend operation — background steps should be polled with `wizard state`.

```
mcpheroctl wizard <command>
```

### Pipeline Overview

```
  start
    → list-tools / refine-tools (iterate)
    → submit-tools
    → [suggest-env-vars]
    → list-env-vars / refine-env-vars (iterate)
    → submit-env-vars
    → set-auth
    → generate-code / regenerate-tool-code (iterate)
    → deploy
```

Poll `wizard state SERVER_ID` between async steps to check when the server is ready for the next command.

---

### Step 1: Start

```bash
# Basic start (org key infers customer)
mcpheroctl wizard start spec.md

# With explicit customer
mcpheroctl wizard start spec.md --customer-id CUSTOMER_UUID

# With multiple technical detail files
mcpheroctl wizard start spec.md -d openapi.md -d schema.md

# JSON output (returns { "server_id": "..." })
mcpheroctl wizard start spec.md --json
```

`spec.md` — A markdown file describing what the MCP server should do. Technical detail files (`-d`) can contain API schemas, endpoint docs, etc.

---

### Step 2: Tools

```bash
# View generated tool suggestions
mcpheroctl wizard list-tools SERVER_ID

# Refine all tools with feedback
mcpheroctl wizard refine-tools SERVER_ID --feedback "Add a search tool and remove the delete tool"

# Refine specific tools only
mcpheroctl wizard refine-tools SERVER_ID -f "Simplify parameters" --tool-id UUID1 --tool-id UUID2

# Submit selected tools to finalize (moves to env vars step)
mcpheroctl wizard submit-tools SERVER_ID --tool-id UUID1 --tool-id UUID2
```

---

### Step 3: Environment Variables

```bash
# Trigger LLM suggestion of required env vars
mcpheroctl wizard suggest-env-vars SERVER_ID

# View suggestions
mcpheroctl wizard list-env-vars SERVER_ID

# Refine with feedback
mcpheroctl wizard refine-env-vars SERVER_ID --feedback "Combine DB vars into DATABASE_URL"

# Submit values for each variable (UUID=VALUE format)
mcpheroctl wizard submit-env-vars SERVER_ID \
  --var "API_KEY_UUID=sk-abc123" \
  --var "BASE_URL_UUID=https://api.example.com"
```

---

### Step 4: Authentication

```bash
# Generate bearer token for the server
mcpheroctl wizard set-auth SERVER_ID --json
```

---

### Step 5: Code Generation

```bash
# Generate code for all tools (async — poll wizard state)
mcpheroctl wizard generate-code SERVER_ID

# Regenerate a single tool (synchronous — returns immediately)
mcpheroctl wizard regenerate-tool-code SERVER_ID TOOL_ID --json
```

---

### Step 6: Deploy

```bash
mcpheroctl wizard deploy SERVER_ID

# JSON response contains the live server endpoint URL
mcpheroctl wizard deploy SERVER_ID --json
```

---

### State Polling

Poll state to wait for background operations to complete:

```bash
mcpheroctl wizard state SERVER_ID --json
```

Useful states: `pending`, `generating_tools`, `tools_ready`, `generating_code`, `code_ready`, `deploying`, `deployed`, `error`.

---

### Conversation (stub)

```bash
mcpheroctl wizard conversation SERVER_ID
```

> **Not yet implemented.** This feature exists on the frontend but has not been migrated to the backend API. Returns exit code `6` (`not_implemented`).

---

## Scripting & Agent Usage

All commands support `--json` for structured output. Combine with `jq` or any JSON tooling:

```bash
# Get the server ID after starting the wizard
SERVER_ID=$(mcpheroctl wizard start spec.md --json | jq -r '.server_id')

# List tool IDs
TOOL_IDS=$(mcpheroctl wizard list-tools "$SERVER_ID" --json | jq -r '.[].id')

# Submit all suggested tools
mcpheroctl wizard submit-tools "$SERVER_ID" \
  $(echo "$TOOL_IDS" | xargs -I{} echo "--tool-id {}")

# Poll until state is ready
while true; do
  STATE=$(mcpheroctl wizard state "$SERVER_ID" --json | jq -r '.status')
  echo "State: $STATE"
  [ "$STATE" = "tools_ready" ] && break
  sleep 3
done
```

---

## Exit Codes

| Code | Meaning |
|------|---------|
| `0` | Success |
| `1` | General failure |
| `2` | Usage error (bad arguments) |
| `3` | Resource not found |
| `4` | Permission denied / not authenticated |
| `5` | Conflict (resource already exists) |
| `6` | Not implemented |

---

## Error Output

When `--json` is passed, errors are emitted as structured JSON to `stdout`:

```json
{
  "error": "not_found",
  "message": "Server not found",
  "status_code": 404
}
```

Without `--json`, errors are printed to `stderr` with a `✖` prefix.

---

## Project Structure

```
src/mcpheroctl/
├── cli.py               # Main entrypoint — registers auth/server/wizard
├── commands/
│   ├── auth.py          # login, status, logout
│   ├── server.py        # list, get, update, delete, api-key
│   └── wizard.py        # Full wizard pipeline + conversation stub
└── core/
    ├── config.py        # Config storage (~/.config/mcpheroctl/config.json)
    ├── output.py        # JSON/stderr output helpers, exit codes
    └── client.py        # httpx HTTP client with tenacity retries
```

---

## Development

```bash
# Install in editable mode
uv sync

# Run CLI directly
uv run mcpheroctl --help

# Format / lint
uv run ruff format .
uv run ruff check .

# Type check
uv run basedpyright
```

---

## Dependencies

| Package | Purpose |
|---------|---------|
| [`typer`](https://typer.tiangolo.com) | CLI framework |
| [`httpx`](https://www.python-httpx.org) | Async-capable HTTP client |
| [`pydantic`](https://docs.pydantic.dev) | Config validation |
| [`tenacity`](https://tenacity.readthedocs.io) | Retry logic on transient/5xx errors |
| [`rich`](https://rich.readthedocs.io) | Colored stderr output |

---

## License

Apache 2.0 — see [LICENSE](./LICENSE).
