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

| Variable | Required | Default | Description |
|----------|----------|---------|-------------|
| `TELEGRAM_BOT_TOKEN` | Yes | - | Bot token from @BotFather |
| `ALLOWED_TELEGRAM_USER_IDS` | Yes | - | Comma-separated user IDs |
| `SECOND_BRAIN_PATH` | No | `~/Dropbox/python_workspace/second_brain` | Path to second brain |
| `CLAUDE_CODE_PATH` | No | Auto-detect | Path to Claude CLI |
| `HOST` | No | `0.0.0.0` | Server bind address |
| `PORT` | No | `8080` | Server port |
| `WEBHOOK_PATH` | No | `/webhook` | Telegram webhook path |
| `COMMAND_TIMEOUT` | No | `300` | Max execution time (seconds) |

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

## Roadmap

- [X] Heartbeat system (proactive check-ins)
- [ ] Voice message support
- [ ] Image/document handling
- [ ] Telegram approval for dangerous commands
- [ ] Multi-user contexts
