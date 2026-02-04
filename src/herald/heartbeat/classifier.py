# ABOUTME: Classifier for heartbeat responses to detect HEARTBEAT_OK acknowledgments
# ABOUTME: Determines whether responses should be delivered based on content length

import re
from dataclasses import dataclass


@dataclass
class HeartbeatResponse:
    """
    Classification result for a heartbeat response.

    Attributes:
        is_ok: True if response contains HEARTBEAT_OK marker
        content: Response content with HEARTBEAT_OK marker stripped
        should_deliver: True if response should be delivered to user
    """

    is_ok: bool
    content: str
    should_deliver: bool


def classify_heartbeat_response(response: str, ack_max_chars: int = 300) -> HeartbeatResponse:
    """
    Classify a heartbeat response and determine if it should be delivered.

    Detection rules:
    1. Response starting or ending with "HEARTBEAT_OK" (case-insensitive) is an acknowledgment
    2. Strip "HEARTBEAT_OK" from the response for delivery
    3. Acknowledgments <= ack_max_chars are suppressed (should_deliver=False)
    4. Non-OK responses always have should_deliver=True

    Args:
        response: The response text to classify
        ack_max_chars: Maximum character count for suppressing acknowledgments (default: 300)

    Returns:
        HeartbeatResponse with classification results
    """
    # Pattern to match HEARTBEAT_OK at start or end (case-insensitive)
    # Use word boundaries to ensure it's not in the middle of text
    pattern = r"^\s*heartbeat_ok\s*|\s*heartbeat_ok\s*$"

    # Check if HEARTBEAT_OK is present
    is_ok = bool(re.search(pattern, response, re.IGNORECASE))

    if is_ok:
        # Strip HEARTBEAT_OK from the response
        content = re.sub(pattern, "", response, flags=re.IGNORECASE).strip()

        # Determine if should deliver based on content length
        should_deliver = len(content) > ack_max_chars
    else:
        # Non-OK responses are always delivered unchanged
        content = response
        should_deliver = True

    return HeartbeatResponse(is_ok=is_ok, content=content, should_deliver=should_deliver)
