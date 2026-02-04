# ABOUTME: HEARTBEAT.md file reader with intelligent empty-file detection
# ABOUTME: Reads heartbeat files and determines if they contain meaningful content

from pathlib import Path


def read_heartbeat_file(path: Path | None = None) -> str | None:
    """
    Read HEARTBEAT.md file and return contents if meaningful.

    Args:
        path: Path to HEARTBEAT.md file. If None, uses HEARTBEAT.md in current directory.

    Returns:
        File contents if it exists and has meaningful content (not just headers/whitespace).
        None if file doesn't exist, is empty, or only contains markdown headers.

    This allows skipping heartbeat runs when there's nothing to check.
    """
    # Use default path if none provided
    if path is None:
        path = Path.cwd() / "HEARTBEAT.md"

    # Return None if file doesn't exist
    if not path.exists():
        return None

    # Read file contents
    content = path.read_text()

    # Check if content is meaningful
    if not _has_meaningful_content(content):
        return None

    return content


def _has_meaningful_content(content: str) -> bool:
    """
    Check if markdown content has meaningful text beyond headers and whitespace.

    Args:
        content: The markdown content to check

    Returns:
        True if content has non-header, non-whitespace text
        False if content is empty, only whitespace, or only markdown headers
    """
    # Split into lines and check each one
    lines = content.split("\n")

    for line in lines:
        stripped = line.strip()

        # Skip empty lines
        if not stripped:
            continue

        # Skip markdown headers (lines starting with #)
        if stripped.startswith("#"):
            continue

        # Found a line with meaningful content
        return True

    # No meaningful content found
    return False
