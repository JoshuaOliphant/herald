# Herald: Telegram Gateway to Claude Code

[![Tests](https://github.com/joshuaoliphant/herald/actions/workflows/test.yml/badge.svg)](https://github.com/joshuaoliphant/herald/actions/workflows/test.yml)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![Python 3.11+](https://img.shields.io/badge/python-3.11+-blue.svg)](https://www.python.org/downloads/)

Herald is a self-hosted Telegram bot that bridges to [Claude Code](https://docs.anthropic.com/en/docs/claude-code) on your machine, giving you mobile access to your **second brain** — a personal knowledge management system stored as markdown files in a git repo.

> **What is a "second brain"?** It's a system for organizing your notes, tasks, projects, and learnings in a structured way (often using the [PARA method](https://fortelabs.com/blog/para/)). Herald lets you query, update, and interact with yours from anywhere via Telegram, powered by Claude Code's ability to read, search, and edit files.

## Architecture

```
Phone (Telegram) → HTTPS Tunnel → Herald (FastAPI) → Claude Code (Agent SDK)
                                       ↓
                                Second Brain (markdown files)
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

```bash
cp .env.example .env
# Edit .env with your bot token and user ID
```

### 4. Install and Run

```bash
cd herald

# Install dependencies
uv sync

# Run Herald
uv run herald
```

### 5. Expose Herald to the Internet

Herald needs a public HTTPS endpoint for Telegram webhooks. Options:

**Tailscale Funnel** (recommended for always-on setups):
```bash
tailscale funnel 8080
# Note your funnel URL (e.g., https://your-mac.ts.net)
```

**ngrok** (quick testing):
```bash
ngrok http 8080
```

**Cloudflare Tunnels** (production):
```bash
cloudflared tunnel --url http://localhost:8080
```

### 6. Register Webhook with Telegram

```bash
curl "https://api.telegram.org/bot<YOUR_TOKEN>/setWebhook?url=https://<YOUR_DOMAIN>/webhook"
```

## Configuration Options

### Core Settings

| Variable | Required | Default | Description |
|----------|----------|---------|-------------|
| `TELEGRAM_BOT_TOKEN` | Yes | - | Bot token from @BotFather |
| `ALLOWED_TELEGRAM_USER_IDS` | Yes | - | Comma-separated user IDs |
| `SECOND_BRAIN_PATH` | No | `~/second-brain` | Path to your knowledge base |
| `MEMORY_PATH` | No | `areas/herald` | Herald memory dir (relative to second brain) |
| `CHAT_HISTORY_PATH_OVERRIDE` | No | - | Custom chat history path (relative to second brain) |
| `CLAUDE_MODEL` | No | SDK default | Override Claude model (e.g., `claude-opus-4-6`) |
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

See `examples/` for sample heartbeat prompt files.

#### How It Works

1. **Periodic execution**: Every `HEARTBEAT_EVERY` interval, Herald runs a Claude Code session with the heartbeat prompt
2. **HEARTBEAT_OK suppression**: If the agent responds with `HEARTBEAT_OK` (nothing to report), the message is suppressed
3. **Alert delivery**: Meaningful findings are forwarded to the target Telegram chat
4. **Active hours**: Checks only run during the configured time window (if set)

## Security

Herald implements several security measures:

1. **User Whitelist**: Only configured Telegram user IDs can interact
2. **Damage Control Hooks**: Extends existing Claude Code guardrails
3. **HTTPS Required**: Telegram webhooks require HTTPS (provided by your tunnel)
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
4. **Claude Execution**: Sends prompt to Claude Code via the Agent SDK
5. **Streaming**: Substantive intermediate text is forwarded to Telegram in real-time
6. **Response Formatting**: Escapes for Telegram MarkdownV2, splits long messages
7. **Chat History**: Persists conversation to markdown files for future reference

## Features

### Chat History Persistence

Herald automatically persists all conversations to markdown files in your second brain:

```
{memory_path}/chat-history/{chat_id}/YYYY-MM-DD.md
```

Each daily file contains timestamped user and assistant messages, making conversations searchable and reviewable.

### Memory Priming

On startup, Herald loads memory files from the herald memory directory with priority-based budget allocation:

- `pending.md` (30% budget) - Actionable items and follow-ups
- `learnings.md` (40% budget) - Service knowledge and patterns
- `observations.md` (30% budget) - User preferences

This gives the agent context about your preferences and pending items without consuming excessive context window.

### Agent Teams (Experimental)

Set `AGENT_TEAMS=true` to enable Claude Code's experimental agent teams feature, allowing Herald to spawn multiple agents for complex tasks.

## Roadmap

- [X] Heartbeat system (proactive check-ins)
- [X] Chat history persistence
- [X] Memory priming from second brain
- [X] Streaming intermediate responses
- [X] Agent teams support
- [ ] Voice message support
- [ ] Image/document handling
- [ ] Telegram approval for dangerous commands
- [ ] Multi-user contexts

## License

MIT - see [LICENSE](LICENSE) for details.
