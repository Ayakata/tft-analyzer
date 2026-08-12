def elapsed_seconds(frame_timestamp_s: float, session_start_s: float) -> float:
    """Return a non-negative elapsed time from two monotonic timestamps."""
    return max(0.0, float(frame_timestamp_s) - float(session_start_s))
