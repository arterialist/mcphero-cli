# Writing CLI Tools That AI Agents Actually Want to Use

A practical guide to building CLI tools designed for AI agent workflows.

---

## Why CLI Design Matters for Agents

AI coding agents like Claude Code, Codex, and Cursor have shell access and can run any CLI tool. But most CLI tools are subtly hostile to AI agents — they assume human users who can interpret ambiguous output, handle interactive prompts, and guess at command semantics.

This guide provides eight rules for building CLI tools that agents can use effectively.

---

## The Eight Rules

### 1. Structured Output Is Not Optional

The single most important thing: support `--json` or `--output json`.

```bash
# Bad: agent has to parse this
$ myctl list pods
NAME          STATUS    AGE
web-1         Running   3d
worker-2      Failed    1h

# Good: agent gets clean data
$ myctl list pods --json
[
  {"name": "web-1", "status": "Running", "age_seconds": 259200},
  {"name": "worker-2", "status": "Failed", "age_seconds": 3600}
]
```

Agents are good at parsing text, but "good" isn't "reliable." Wrapping tables, inconsistent casing, and ambiguous formats cause silent failures.

**Rules for structured output:**

- **JSON to stdout, everything else to stderr.** Progress messages, warnings, spinners — all stderr. Stdout is your API contract.
- **Flat over nested.** `{"pod_name": "web-1", "pod_status": "Running"}` is easier than `{"pod": {"metadata": {"name": "web-1"}, "status": {"phase": "Running"}}}`.
- **Consistent types.** If `age` is a number in one command, don't make it a string like `"3 days"` in another. Use seconds or ISO 8601 timestamps.
- **JSON Lines for streaming.** If the command produces incremental output, emit one JSON object per line.

---

### 2. Exit Codes Are the Agent's Control Flow

Agents check `$?` to decide what to do next. A tool that returns 0 on failure breaks every agent workflow.

```bash
# This is a contract:
0   = success
1   = general failure  
2   = usage error (bad arguments)
3   = resource not found
4   = permission denied
5   = conflict (resource already exists)
```

Document your exit codes. An agent that gets exit code 5 can skip creation and move to the next step. An agent that gets exit code 1 for everything has to parse stderr — and it will sometimes get it wrong.

**Combine exit codes with structured error output:**

```bash
$ myctl create thing --name duplicate-name
# stderr: Error: resource "duplicate-name" already exists
# stdout (with --json): {"error": "conflict", "message": "resource 'duplicate-name' already exists", "existing_id": "abc123"}
# exit code: 5
```

---

### 3. Make Commands Idempotent

Agents retry. Networks fail. Commands get interrupted. If your `create` command fails on the second run because the resource already exists, the agent has to write special-case retry logic.

```bash
# Fragile: fails on retry
$ myctl create namespace prod
Error: namespace "prod" already exists

# Robust: idempotent
$ myctl ensure namespace prod
namespace "prod" already exists (no changes)

# Or use a flag
$ myctl create namespace prod --if-not-exists
```

The kubectl model is a good reference: `kubectl apply` is idempotent by design. Declarative commands (`ensure`, `apply`, `sync`) are inherently safer for agents than imperative ones (`create`, `delete`).

If you can't make a command idempotent, make the conflict detectable with a distinct exit code.

---

### 4. Self-Documenting Beats External Docs

When an agent encounters an unfamiliar CLI, the first thing it does is run `--help`. That help text is your tool description, parameter spec, and usage guide all in one.

```bash
# Bad: minimal help
$ myctl deploy --help
Usage: myctl deploy [flags]

# Good: the agent can learn from this
$ myctl deploy --help
Deploy a service to the target environment.

Usage:
  myctl deploy <service-name> --env <environment> [flags]

Arguments:
  service-name    Name of the service to deploy (required)

Flags:
  --env string       Target environment: dev, staging, prod (required)
  --image string     Container image override (default: from config)
  --dry-run          Preview changes without applying
  --wait             Wait for deployment to complete (default: true)
  --timeout duration Maximum wait time (default: 5m)
  --json             Output result as JSON

Examples:
  myctl deploy web-api --env staging
  myctl deploy web-api --env prod --image myregistry/web:v2.1.0 --json
  myctl deploy web-api --env dev --dry-run
```

**Key points:**

- **Show required vs optional clearly.** Agents will not guess which flags are required.
- **Include realistic examples.** Agents learn patterns from examples faster than from flag descriptions.
- **Document the `--json` flag.** If the agent doesn't know it exists, it won't use it.
- **Use subcommand discovery.** `myctl --help` should list all subcommands. `myctl deploy --help` should give full detail.

---

### 5. Design for Composability

Unix philosophy applies doubly for agents. Agents already think in pipelines — they chain commands naturally.

```bash
# An agent will naturally compose these:
myctl list pods --json | jq '.[] | select(.status == "Failed") | .name'

# Better: build filtering in
myctl list pods --status failed --json --field name

# Best: support both approaches
myctl list pods --status failed --json        # filtered JSON
myctl list pods --status failed --quiet       # just names, one per line
```

**Design your CLI so that:**

- **`--quiet` or `-q` outputs bare values.** One value per line, no headers, no decoration. Agents use this for piping into `xargs` or `while read`.
- **Stdin acceptance is explicit.** If a command can read from stdin, document it: `myctl apply -f -` reads from stdin. Don't make the agent guess.
- **Batch operations exist.** If an agent needs to delete 50 resources, `myctl delete --selector app=old` is one call instead of 50.

---

### 6. Provide Dry-Run and Confirmation Bypass

Agents need two things that conflict with interactive CLI design: they need to preview destructive actions, and they need to execute without human confirmation prompts.

```bash
# Preview what would happen
$ myctl deploy web-api --env prod --dry-run --json
{
  "action": "deploy",
  "changes": [
    {"type": "update", "resource": "deployment/web-api", "diff": "image: v2.0 → v2.1"}
  ],
  "warnings": ["This will restart 3 running pods"]
}

# Execute without interactive prompt
$ myctl deploy web-api --env prod --yes
# or
$ myctl deploy web-api --env prod --force
```

**Rules:**

- **`--dry-run` should produce structured output.** Not "would deploy web-api to prod" but a JSON diff of what changes.
- **`--yes` / `--no-confirm` / `--force` bypasses all prompts.** An agent cannot type "y" at a confirmation prompt. If your CLI hangs waiting for input, the agent's workflow is dead.
- **Detect non-interactive terminals.** If stdin is not a TTY, either skip prompts automatically or fail with a clear error telling the user to pass `--yes`.

---

### 7. Errors Should Be Actionable

When a command fails, the agent needs to decide: retry, try something else, or give up. The error message determines which.

```bash
# Bad: the agent has no idea what to do
$ myctl deploy web-api --env prod
Error: deployment failed

# Good: the agent can reason about this
$ myctl deploy web-api --env prod --json
# exit code: 1
# stderr: Error: image "myregistry/web:v2.1.0" not found in registry
# stdout: {"error": "image_not_found", "image": "myregistry/web:v2.1.0", 
#          "registry": "myregistry", "suggestion": "check image tag exists"}
```

**Error design for agents:**

- **Error codes/types in structured output.** A string like `"image_not_found"` is parseable. `"Error occurred"` is not.
- **Include the failing input.** If the image name is wrong, echo it back. The agent needs this to construct a fix.
- **Suggest next steps when possible.** `"suggestion": "run myctl images list to see available tags"` gives the agent a concrete recovery path.
- **Separate transient from permanent errors.** A timeout is worth retrying. A permission denied is not.

---

### 8. Use Consistent Noun-Verb Grammar

When designing a CLI with many subcommands, order matters. Human users might memorize random command names, but agents rely on predictable patterns to discover what a tool can do.

```bash
# Bad: Mixed grammar is hard to guess
$ myctl create-user
$ myctl delete_user
$ myctl user-group add

# Good: Noun -> Verb hierarchy
$ myctl user create
$ myctl user delete
$ myctl user group add
```

The `noun verb` pattern (e.g., `docker container ls`, `gh pr create`) is exceptionally agent-friendly because it naturally groups related actions in the `--help` output.

When an agent runs `myctl --help`, it sees a list of resources (nouns). When it runs `myctl user --help`, it sees all possible actions (verbs) for that resource. This hierarchical structure turns exploration into a deterministic tree search.

---

## Quick Reference Checklist

When building a CLI tool that agents will use:

```
[ ] --json flag for structured output
[ ] JSON to stdout, messages to stderr
[ ] Meaningful exit codes (not just 0/1)
[ ] Idempotent operations (or clear conflict handling)
[ ] Comprehensive --help with examples
[ ] --dry-run for destructive commands
[ ] --yes/--force to bypass prompts
[ ] --quiet for pipe-friendly bare output
[ ] Consistent field names and types across commands
[ ] Consistent noun-verb hierarchy (e.g., `noun verb`)
[ ] Actionable error messages with error codes
[ ] Batch operations for bulk work
[ ] Non-interactive TTY detection
```
