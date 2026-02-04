# ABOUTME: Heartbeat module for Herald - manages active hours and heartbeat configuration.
# ABOUTME: Provides utilities for time window validation and heartbeat settings.

from herald.heartbeat.active_hours import is_within_active_hours

__all__ = ["is_within_active_hours"]
