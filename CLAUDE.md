# Herald - Claude Code Instructions

## What This Is

Herald is a Telegram gateway to Claude Code, enabling mobile access to your knowledge base ("second brain") from anywhere.

## Architecture

```
Telegram → Tailscale Funnel → Herald (FastAPI) → Claude Code → Second Brain
```

## Key Files

- `src/herald/webhook.py` - FastAPI webhook handler, user authorization
- `src/herald/executor.py` - Claude Code CLI wrapper, JSON parsing
- `src/herald/formatter.py` - Telegram message formatting, MarkdownV2 escaping
- `src/herald/config.py` - Settings from environment variables
- `src/herald/main.py` - Entry point, uvicorn server

## Development Commands

```bash
# Install dependencies
uv sync

# Run tests
uv run pytest

# Run with auto-reload
uv run uvicorn herald.webhook:create_app --factory --reload --port 8080

# Lint
uv run ruff check src tests

# Type check
uv run pyright src
```

## Testing Strategy

- Unit tests for config parsing, formatting, executor parsing
- Integration tests for webhook handler with mocked executor
- Manual testing via Telegram after Tailscale Funnel setup

## Security Notes

- User whitelist is mandatory - empty whitelist rejects all users
- Uses `--dangerously-skip-permissions` but relies on damage-control hooks
- Bot token must never be logged or exposed in responses
- Tailscale Funnel provides HTTPS automatically

## Issue Tracking

This project uses **GitHub Issues** for issue tracking.

```bash
gh issue list                    # Find available work
gh issue view <number>           # View issue details
gh issue edit <number> --add-assignee @me  # Claim work
gh issue close <number>          # Complete work
```

## Session Completion

**When ending a work session**, you MUST complete ALL steps below. Work is NOT complete until `git push` succeeds.

1. **File issues for remaining work** - Create issues for anything that needs follow-up
2. **Run quality gates** (if code changed) - Tests, linters, builds
3. **Update issue status** - Close finished work, update in-progress items
4. **Push to remote**: `git pull --rebase && git push`
5. **Verify** - `git status` shows "up to date with origin"
