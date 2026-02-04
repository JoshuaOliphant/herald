# ABOUTME: Unit tests for heartbeat response classifier
# ABOUTME: Tests HEARTBEAT_OK detection and acknowledgment suppression logic


from herald.heartbeat.classifier import HeartbeatResponse, classify_heartbeat_response


class TestHeartbeatResponse:
    """Tests for the HeartbeatResponse dataclass."""

    def test_heartbeat_response_attributes(self):
        """Test that HeartbeatResponse has the expected attributes."""
        response = HeartbeatResponse(
            is_ok=True,
            content="All systems operational",
            should_deliver=False,
        )
        assert response.is_ok is True
        assert response.content == "All systems operational"
        assert response.should_deliver is False


class TestClassifyHeartbeatResponse:
    """Tests for classify_heartbeat_response function."""

    # HEARTBEAT_OK detection tests
    def test_heartbeat_ok_prefix_uppercase(self):
        """Test detection of HEARTBEAT_OK at the start (uppercase)."""
        result = classify_heartbeat_response("HEARTBEAT_OK All systems green")
        assert result.is_ok is True
        assert result.content == "All systems green"

    def test_heartbeat_ok_prefix_lowercase(self):
        """Test detection of heartbeat_ok at the start (lowercase)."""
        result = classify_heartbeat_response("heartbeat_ok Everything running smoothly")
        assert result.is_ok is True
        assert result.content == "Everything running smoothly"

    def test_heartbeat_ok_prefix_mixed_case(self):
        """Test detection of HeArTbEaT_oK at the start (mixed case)."""
        result = classify_heartbeat_response("HeArTbEaT_oK Status nominal")
        assert result.is_ok is True
        assert result.content == "Status nominal"

    def test_heartbeat_ok_suffix_uppercase(self):
        """Test detection of HEARTBEAT_OK at the end (uppercase)."""
        result = classify_heartbeat_response("All good HEARTBEAT_OK")
        assert result.is_ok is True
        assert result.content == "All good"

    def test_heartbeat_ok_suffix_lowercase(self):
        """Test detection of heartbeat_ok at the end (lowercase)."""
        result = classify_heartbeat_response("Everything fine heartbeat_ok")
        assert result.is_ok is True
        assert result.content == "Everything fine"

    def test_heartbeat_ok_both_prefix_and_suffix(self):
        """Test when HEARTBEAT_OK appears at both start and end."""
        result = classify_heartbeat_response("HEARTBEAT_OK Status good HEARTBEAT_OK")
        assert result.is_ok is True
        # Should strip both occurrences
        assert result.content == "Status good"

    def test_heartbeat_ok_with_whitespace(self):
        """Test HEARTBEAT_OK with various whitespace."""
        result = classify_heartbeat_response("  HEARTBEAT_OK  Status update  ")
        assert result.is_ok is True
        assert result.content == "Status update"

    def test_heartbeat_ok_standalone(self):
        """Test standalone HEARTBEAT_OK with no other content."""
        result = classify_heartbeat_response("HEARTBEAT_OK")
        assert result.is_ok is True
        assert result.content == ""

    def test_heartbeat_ok_in_middle_not_detected(self):
        """Test that HEARTBEAT_OK in the middle of text is NOT detected."""
        result = classify_heartbeat_response("The HEARTBEAT_OK signal was received")
        assert result.is_ok is False
        assert result.content == "The HEARTBEAT_OK signal was received"

    def test_non_heartbeat_response(self):
        """Test response without HEARTBEAT_OK marker."""
        result = classify_heartbeat_response("Error: Database connection failed")
        assert result.is_ok is False
        assert result.content == "Error: Database connection failed"

    # should_deliver logic tests
    def test_short_acknowledgment_suppressed_default_threshold(self):
        """Test that short OK responses are suppressed (default 300 chars)."""
        result = classify_heartbeat_response("HEARTBEAT_OK OK")
        assert result.is_ok is True
        assert result.should_deliver is False
        assert len(result.content) <= 300

    def test_long_acknowledgment_delivered_default_threshold(self):
        """Test that long OK responses are delivered (default 300 chars)."""
        long_message = "HEARTBEAT_OK " + "A" * 400
        result = classify_heartbeat_response(long_message)
        assert result.is_ok is True
        assert result.should_deliver is True
        assert len(result.content) > 300

    def test_exact_threshold_is_suppressed(self):
        """Test that content exactly at threshold is suppressed."""
        # Content exactly 300 chars after stripping HEARTBEAT_OK
        exact_content = "A" * 300
        result = classify_heartbeat_response(f"HEARTBEAT_OK {exact_content}")
        assert result.is_ok is True
        assert result.should_deliver is False
        assert len(result.content) == 300

    def test_one_over_threshold_is_delivered(self):
        """Test that content one char over threshold is delivered."""
        # Content exactly 301 chars after stripping HEARTBEAT_OK
        over_content = "A" * 301
        result = classify_heartbeat_response(f"HEARTBEAT_OK {over_content}")
        assert result.is_ok is True
        assert result.should_deliver is True
        assert len(result.content) == 301

    def test_custom_threshold(self):
        """Test custom ack_max_chars threshold."""
        result = classify_heartbeat_response("HEARTBEAT_OK Short", ack_max_chars=10)
        assert result.is_ok is True
        assert result.should_deliver is False  # "Short" is 5 chars, under threshold

        result = classify_heartbeat_response("HEARTBEAT_OK LongerMessage", ack_max_chars=10)
        assert result.is_ok is True
        assert result.should_deliver is True  # "LongerMessage" is 13 chars, over threshold

    def test_non_ok_response_always_delivered(self):
        """Test that non-OK responses are always delivered."""
        result = classify_heartbeat_response("Error message")
        assert result.is_ok is False
        assert result.should_deliver is True

    def test_empty_response_non_ok(self):
        """Test that empty response is treated as non-OK."""
        result = classify_heartbeat_response("")
        assert result.is_ok is False
        assert result.should_deliver is True
        assert result.content == ""

    def test_whitespace_only_response_non_ok(self):
        """Test that whitespace-only response is treated as non-OK."""
        result = classify_heartbeat_response("   ")
        assert result.is_ok is False
        assert result.should_deliver is True
        assert result.content == "   "

    # Edge cases
    def test_multiline_heartbeat_ok(self):
        """Test HEARTBEAT_OK with multiline content."""
        multiline = "HEARTBEAT_OK\nLine 1\nLine 2\nLine 3"
        result = classify_heartbeat_response(multiline)
        assert result.is_ok is True
        assert "Line 1" in result.content
        assert "Line 2" in result.content
        assert "Line 3" in result.content

    def test_heartbeat_ok_with_special_characters(self):
        """Test HEARTBEAT_OK followed by special characters."""
        result = classify_heartbeat_response("HEARTBEAT_OK 🚀 Deployment successful!")
        assert result.is_ok is True
        assert "🚀 Deployment successful!" in result.content
