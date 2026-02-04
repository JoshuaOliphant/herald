# Herald - Claude Code Instructions

## What This Is

Herald is a Telegram gateway to Claude Code, enabling La Boeuf to access his second brain from anywhere via mobile.

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

## Related Resources

- **Skill**: `~/.claude/skills/herald/SKILL.md` - Telegram response behavior
- **Memory**: `second_brain/areas/herald/` - Herald's persistent learnings
- **Second Brain**: `~/Dropbox/python_workspace/second_brain/` - Working directory for Claude Code

@AGENTS.md
