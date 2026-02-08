# Herald: Telegram Gateway to Claude Code

Herald is a bi-directional Telegram bot that bridges to Claude Code on your Mac, enabling mobile access to your second brain.

## Architecture

```
Phone (Telegram) → Tailscale Funnel → Herald (FastAPI) → Claude Code
                                          ↓
                                   Second Brain + Skills
                                          ↓
                                   macOS (osascript)
```

## Quick Start

### 1. Create a Telegram Bot

1. Message [@BotFather](https://t.me/botfather) on Telegram
2. Send `/newbot` and follow the prompts
3. Save the bot token (looks like `123456789:ABCdefGHIjklMNOpqrsTUVwxyz`)

### 2. Get Your Telegram User ID

1. Message [@userinfobot](https://t.me/userinfobot) on Telegram
2. Note your user ID (a number like `123456789`)

### 3. Configure Herald

Create a `.env` file in the project root:

```bash
# Required: Your Telegram Bot Token (from @BotFather)
TELEGRAM_BOT_TOKEN=your_bot_token_here

# Required: Comma-separated list of allowed Telegram user IDs
ALLOWED_TELEGRAM_USER_IDS=123456789

# Optional: Override paths if needed
# SECOND_BRAIN_PATH=/path/to/your/second_brain
# CLAUDE_CODE_PATH=/path/to/claude
```

### 4. Install and Run

```bash
cd ~/Dropbox/python_workspace/herald

# Install dependencies
uv sync

# Run Herald
uv run herald
```

### 5. Set Up Tailscale Funnel

```bash
# Enable Tailscale Funnel (one-time)
tailscale funnel 8080

# Note your funnel URL (e.g., https://your-mac.ts.net)
```

### 6. Register Webhook with Telegram

```bash
curl "https://api.telegram.org/bot<YOUR_TOKEN>/setWebhook?url=https://<YOUR_MAC>.ts.net/webhook"
```

## Configuration Options

### Core Settings

| Variable | Required | Default | Description |
|----------|----------|---------|-------------|
| `TELEGRAM_BOT_TOKEN` | Yes | - | Bot token from @BotFather |
| `ALLOWED_TELEGRAM_USER_IDS` | Yes | - | Comma-separated user IDs |
| `SECOND_BRAIN_PATH` | No | `~/second-brain` | Path to second brain |
| `CLAUDE_CODE_PATH` | No | Auto-detect | Path to Claude CLI |
| `HOST` | No | `0.0.0.0` | Server bind address |
| `PORT` | No | `8080` | Server port |
| `WEBHOOK_PATH` | No | `/webhook` | Telegram webhook path |
| `COMMAND_TIMEOUT` | No | `300` | Max execution time (seconds) |

### Heartbeat Settings

The heartbeat system sends periodic check-ins through Claude Code, allowing Herald to proactively surface reminders, stale projects, inbox items, and other useful information.

| Variable | Required | Default | Description |
|----------|----------|---------|-------------|
| `HEARTBEAT_ENABLED` | No | `false` | Enable periodic heartbeat checks |
| `HEARTBEAT_EVERY` | No | `30m` | Check interval (e.g., `15m`, `1h`, `2h30m`) |
| `HEARTBEAT_PROMPT` | No | Built-in | Custom prompt for heartbeat checks |
| `HEARTBEAT_PROMPT_FILE` | No | - | Load prompt from file (overrides `HEARTBEAT_PROMPT`) |
| `HEARTBEAT_TARGET` | No | `last` | Where to deliver alerts: `last` (most recent chat), or a chat ID |
| `HEARTBEAT_ACTIVE_HOURS` | No | - | Restrict to time window (e.g., `09:00-22:00`) |
| `HEARTBEAT_ACK_MAX_CHARS` | No | `300` | Suppress "all clear" responses under this length |
| `HEARTBEAT_MODEL` | No | - | Model override (e.g., `sonnet` for cheaper checks) |
| `HEARTBEAT_FILE` | No | - | Path to a `HEARTBEAT.md` file injected into heartbeat context |

#### Example Heartbeat Configuration

```bash
# Enable heartbeat with hourly checks during waking hours
HEARTBEAT_ENABLED=true
HEARTBEAT_EVERY=1h
HEARTBEAT_ACTIVE_HOURS=08:00-22:00
HEARTBEAT_TARGET=last
HEARTBEAT_PROMPT_FILE=/path/to/heartbeat-prompt.md
```

#### How It Works

1. **Periodic execution**: Every `HEARTBEAT_EVERY` interval, Herald runs a Claude Code session with the heartbeat prompt
2. **HEARTBEAT_OK suppression**: If the agent responds with `HEARTBEAT_OK` (nothing to report), the message is suppressed
3. **Alert delivery**: Meaningful findings are forwarded to the target Telegram chat
4. **Active hours**: Checks only run during the configured time window (if set)

## Security

Herald implements several security measures:

1. **User Whitelist**: Only configured Telegram user IDs can interact
2. **Damage Control Hooks**: Extends existing Claude Code guardrails
3. **Tailscale Funnel**: HTTPS by default, no port forwarding needed
4. **No Secret Exposure**: Bot token never logged or transmitted

## Development

```bash
# Install dev dependencies
uv sync --all-extras

# Run tests
uv run pytest

# Run with auto-reload
uv run uvicorn herald.main:app --reload --port 8080

# Lint
uv run ruff check src tests
```

## How It Works

1. **Telegram Update**: User sends message to bot
2. **Webhook Receives**: FastAPI endpoint receives the update
3. **User Validation**: Checks if user ID is in whitelist
4. **Claude Execution**: Runs `claude -p "{message}" --dangerously-skip-permissions`
5. **Output Parsing**: Extracts text from streaming JSON output
6. **Response Formatting**: Escapes for Telegram MarkdownV2, splits if needed
7. **Send Response**: Posts back to Telegram chat

## Features

### Chat History Persistence

Herald automatically persists all conversations to markdown files in your second brain:

```
areas/herald/chat-history/{chat_id}/YYYY-MM-DD.md
```

Each daily file contains timestamped user and assistant messages, making conversations searchable and reviewable.

### Memory Priming

On startup, Herald loads memory files from `areas/herald/` in your second brain with priority-based budget allocation:

- `pending.md` (60% budget) - Pending tasks and follow-ups
- `learnings.md` (40% budget) - Service knowledge and observations

This gives the agent context about your preferences and pending items without consuming excessive context window.

## Roadmap

- [X] Heartbeat system (proactive check-ins)
- [X] Chat history persistence
- [X] Memory priming from second brain
- [ ] Voice message support
- [ ] Image/document handling
- [ ] Telegram approval for dangerous commands
- [ ] Multi-user contexts
