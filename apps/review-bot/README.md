# review-bot

A long-running FastAPI service that automatically reviews GitHub pull requests using a configurable large language model (LLM). The service runs in a Kubernetes pod and uses outbound polling — no inbound webhook endpoint or public internet exposure is required.

## How It Works

On startup the service launches a background polling loop that queries the GitHub API every `REVIEW_BOT_POLL_INTERVAL_SECONDS` (default 60 seconds) for open PRs in all registered repositories. When a new or updated PR is detected, the bot fetches the diff and any `AGENTS.md` files from the target repository, assembles a layered LLM prompt, calls the configured model, and posts a GitHub Review with inline line-level comments and a top-level summary. A SQLite state store persists the last-seen head SHA per PR so that unchanged commits are never re-reviewed.

An optional `POST /v1/review` endpoint is also available for on-demand reviews from skills, MCP tools, or CLI clients.

## Secrets Setup

All secrets are stored as Kubernetes secrets and surfaced to the service as environment variables. Create a `review-bot-secrets` secret in the `review-bot` namespace:

```yaml
# Required
GITHUB_TOKEN: <GitHub personal access token with read:repo and write:pull-requests scopes>
REVIEW_BOT_PSK: <pre-shared key for POST /v1/review bearer token auth>

# One or both API keys are required depending on the model(s) configured
GEMINI_API_KEY: <Google Gemini API key (shared across all repos)>
ANTHROPIC_API_KEY: <Anthropic API key (shared across all repos)>
```

### Per-Repository Secret Overrides

To use different credentials for a specific repository, add per-repo environment variables to the secret. The `<SAFE_NAME>` is derived from `owner/repo` by uppercasing and replacing `/` and `-` with `_`.

Example for `anchavesb/my-app` → `ANCHAVESB_MY_APP`:

```
REPO_ANCHAVESB_MY_APP_GITHUB_TOKEN=<token>
REPO_ANCHAVESB_MY_APP_GEMINI_API_KEY=<key>
REPO_ANCHAVESB_MY_APP_ANTHROPIC_API_KEY=<key>
```

Per-repo keys take precedence over the shared keys.

## Configuration

### Environment Variables

| Variable | Purpose | Default |
|----------|---------|---------|
| `REVIEW_BOT_POLL_INTERVAL_SECONDS` | Seconds between poll cycles | `60` |
| `REVIEW_BOT_STATE_DB_PATH` | Path to SQLite state file | `data/state.db` |
| `REVIEW_BOT_REGISTRY_PATH` | Path to `repos.yml` | `config/repos.yml` |
| `REVIEW_BOT_PROMPTS_DIR` | Path to `prompts/` directory | `prompts` |
| `REVIEW_BOT_MAX_CONCURRENT` | Max simultaneous LLM review calls | `3` |
| `REVIEW_BOT_LOG_LEVEL` | Log level | `INFO` |
| `REVIEW_BOT_LOG_FORMAT` | `json` or `text` | `json` |

In Kubernetes the `REVIEW_BOT_STATE_DB_PATH` is typically set to `/data/state.db` via a ConfigMap, where `/data` is the PVC mount path.

### Poll Interval

Set `REVIEW_BOT_POLL_INTERVAL_SECONDS` in the service ConfigMap to control how frequently the service checks for new PRs. Lower values reduce review latency at the cost of more GitHub API calls.

### Concurrency

`REVIEW_BOT_MAX_CONCURRENT` limits simultaneous LLM calls regardless of trigger source (poller or manual trigger). Increase this value if you have many repositories and want faster throughput. Note that each concurrent review counts against your LLM provider's rate limits.

## Adding a Repository

1. Add an entry to `apps/review-bot/config/repos.yml`:

   ```yaml
   repositories:
     - repo: "owner/repo-name"
       model: "anthropic/claude-sonnet-4-20250514"  # optional; overrides defaults.model
   ```

2. Provision a GitHub token with `repo:read` and `pull_requests:write` permissions for the target repository. Add it to the `review-bot-secrets` Kubernetes secret:
   - Use the shared `GITHUB_TOKEN` if the same token works for all repositories.
   - Use `REPO_<SAFE_NAME>_GITHUB_TOKEN` if the repository requires a separate token.

3. Provision the appropriate LLM API key (`GEMINI_API_KEY` or `ANTHROPIC_API_KEY`) if not already set.

4. Apply the updated ConfigMap or secret and restart the pod. No code changes or redeployment of the service image is required.

## Per-Repository Config (`review-bot.yml`)

A repository can customize its review behavior by placing a `review-bot.yml` file at its root. The file is fetched by the bot at review time via the GitHub API.

```yaml
# review-bot.yml (in the target repository root)
model: "gemini/gemini-1.5-pro"   # optional model override

prompt:
  mode: "extend"                  # "extend" | "replace"
  extension: |
    Focus especially on type safety and test coverage for new public APIs.
```

Configuration precedence (highest to lowest):

1. Per-repo `review-bot.yml` in the target repository
2. Per-repo entry in `config/repos.yml`
3. Global `defaults` in `config/repos.yml`

## `POST /v1/review` Endpoint

The manual trigger endpoint allows external callers (skills, MCP tools, CLI clients) to request an on-demand review for a specific PR without waiting for the next poll cycle.

**Request**:

```http
POST /v1/review
Authorization: Bearer <REVIEW_BOT_PSK>
Content-Type: application/json

{
  "repo": "owner/repo-name",
  "pr_number": 42,
  "force": false
}
```

**Fields**:

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `repo` | string | yes | Repository in `owner/repo` format |
| `pr_number` | int | yes | Pull request number |
| `force` | bool | no | Bypass deduplication and re-review even if SHA is unchanged (default `false`) |

**Response Codes**:

| Code | Body | Meaning |
|------|------|---------|
| `202 Accepted` | `{"status": "accepted", "repo": "...", "pr_number": N}` | Review queued as a background task |
| `200 OK` | `{"status": "already_reviewed", "sha": "..."}` | PR already reviewed at this SHA; `force=false` |
| `401 Unauthorized` | — | Missing or invalid PSK bearer token |
| `503 Service Unavailable` | — | Semaphore exhausted; retry after 30 seconds |

The review runs asynchronously. The `202` response means the review has been queued, not that it has completed.

## Review Prompt

The base review prompt is defined in `apps/review-bot/prompts/base_review.md`. Editing this file changes the review instructions for all repositories that have not configured a `replace`-mode prompt. Changes take effect on the next pod restart.

## `AGENTS.md` Integration

Before submitting a diff to the LLM, the bot discovers and reads `AGENTS.md` files from the target repository:

- `AGENTS.md` at the repository root
- `<subdir>/AGENTS.md` for each top-level subdirectory touched by the diff

The content of all discovered files is included in the LLM prompt as explicit review guidelines. Repositories can steer the automated review simply by editing their own `AGENTS.md` files — no changes to the bot are required.

## Health Endpoint

`GET /health` returns a `200 OK` with service status. This endpoint is used by Kubernetes liveness and readiness probes.
