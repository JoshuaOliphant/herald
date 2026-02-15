# Herald - Claude Code Instructions

## What This Is

Herald is a Telegram gateway to Claude Code, enabling mobile access to your knowledge base ("second brain") from anywhere.

## Architecture

```
Telegram → HTTPS Tunnel → Herald (FastAPI) → Claude Code (Agent SDK)
                               ↓
                        Second Brain (markdown)
```

## Key Files

- `src/herald/webhook.py` - FastAPI webhook handler, user authorization, typing indicators
- `src/herald/executor.py` - Agent SDK client manager, per-chat conversation continuity
- `src/herald/formatter.py` - Telegram HTML formatting, message splitting
- `src/herald/config.py` - Pydantic settings from environment variables
- `src/herald/chat_history.py` - Conversation persistence to daily markdown files
- `src/herald/main.py` - Entry point, uvicorn server
- `src/herald/heartbeat/` - Proactive check-in subsystem (scheduler, classifier, delivery)

## Development Commands

```bash
uv sync                          # Install dependencies
uv run pytest                    # Run tests (286+)
uv run pytest tests/test_config.py  # Run single test file
uv run ruff check src tests      # Lint
uv run ty check src              # Type check
uv run uvicorn herald.webhook:create_app --factory --reload --port 8080  # Dev server
```

## Code Conventions

- All `.py` files start with two `ABOUTME:` comment lines explaining the file's purpose
- Ruff for linting and formatting (line-length 100, target py311)
- Tests use `asyncio_mode = "auto"` — no need for `@pytest.mark.asyncio` on test classes
- Telegram messages use HTML parse mode (not MarkdownV2)

## Testing Strategy

- Unit tests for config parsing, formatting, executor, heartbeat subsystem
- Integration tests for webhook handler with mocked executor
- Manual testing via Telegram after tunnel setup

## Gotchas

- `executor.py` manages one SDK client per `chat_id` with per-chat locks — concurrent messages to the same chat are serialized
- `MESSAGE_IDLE_TIMEOUT` (1800s) is the hang-detection safety net; `POST_RESULT_IDLE_TIMEOUT` (30s) kicks in after the first ResultMessage
- `MIN_STREAM_LENGTH` (200 chars) filters short status messages from being streamed to Telegram
- Heartbeat responses containing `HEARTBEAT_OK` are suppressed (not forwarded to user)

## Security Notes

- User whitelist is mandatory — empty whitelist rejects all users
- Bot token must never be logged or exposed in responses
- HTTPS required for Telegram webhooks (provided by your tunnel)

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
