# Contributing to Herald

Thanks for your interest in contributing to Herald!

## Prerequisites

- Python 3.11+
- [uv](https://docs.astral.sh/uv/) (Python package manager)
- A Telegram bot token (for integration testing)

## Development Setup

```bash
# Clone the repo
git clone https://github.com/joshuaoliphant/herald.git
cd herald

# Install all dependencies (including dev)
uv sync

# Run tests
uv run pytest

# Run linter
uv run ruff check src tests
```

## Code Style

- **Formatter/Linter**: [Ruff](https://docs.astral.sh/ruff/)
- **Line length**: 100 characters
- **Target**: Python 3.11+
- All files should start with a two-line `ABOUTME:` comment explaining what the file does

Run linting before submitting:

```bash
uv run ruff check src tests
```

## Testing

Herald follows **Test-Driven Development (TDD)**:

1. Write a failing test first
2. Write minimal code to make it pass
3. Refactor while keeping tests green

```bash
# Run full test suite
uv run pytest

# Run specific test file
uv run pytest tests/test_config.py

# Run with verbose output
uv run pytest -v
```

The test suite currently has 286+ tests covering:
- Configuration parsing and validation
- Executor (Claude Agent SDK) interaction
- Webhook handler (message routing, authorization, streaming)
- Heartbeat system (scheduling, delivery, prompt processing)
- Chat history persistence
- Message formatting (Telegram MarkdownV2)

## Pull Request Process

1. Fork the repository
2. Create a feature branch (`git checkout -b feature/my-feature`)
3. Write tests for your changes
4. Ensure all tests pass (`uv run pytest`)
5. Ensure linting passes (`uv run ruff check src tests`)
6. Commit with descriptive messages
7. Push to your fork and open a PR

## Architecture Overview

```
src/herald/
├── main.py          # Entry point, uvicorn server
├── config.py        # Pydantic settings from environment
├── webhook.py       # FastAPI webhook handler, Telegram integration
├── executor.py      # Claude Agent SDK client management
├── formatter.py     # Telegram MarkdownV2 formatting
├── chat_history.py  # Conversation persistence to markdown
└── heartbeat/       # Proactive check-in system
    ├── config.py    # Heartbeat-specific settings
    ├── scheduler.py # Periodic execution scheduler
    ├── delivery.py  # Alert delivery to Telegram
    └── processor.py # Heartbeat prompt processing
```

## Questions?

Open an issue on GitHub if you have questions or need help getting started.
