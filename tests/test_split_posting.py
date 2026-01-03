"""Integration tests for posting split events to ActivityWatch."""

from datetime import UTC, datetime, timedelta
from unittest.mock import Mock

import aw_core

from aw_watcher_ask_away.core import AWAskAwayClient
from aw_watcher_ask_away.split_dialog import ActivityLine


def test_post_split_events_creates_multiple_events() -> None:
    """Test that post_split_events creates multiple events with split metadata."""
    # Create mock client
    mock_client = Mock()
    mock_client.client_hostname = "test_host"
    mock_client.get_buckets.return_value = {
        "aw-watcher-afk_test_host": {"type": "afkstatus"},
        "aw-watcher-ask-away_test_host": {"type": "afktask"},
    }
    mock_client.get_events.return_value = []
    mock_client.insert_event = Mock()

    # Create client wrapper
    client = AWAskAwayClient(mock_client, enable_lid_events=False)

    # Create test AFK event
    original_start = datetime(2025, 1, 15, 14, 0, 0, tzinfo=UTC)
    original_event = aw_core.Event(
        timestamp=original_start,
        duration=timedelta(minutes=30),
        data={"status": "afk"},
    )

    # Create split activities
    activities = [
        ActivityLine("lunch", original_start, 15, 0),
        ActivityLine("phone", original_start + timedelta(minutes=15), 15, 0),
    ]

    # Post split events
    client.post_split_events(original_event, activities)

    # Verify insert_event was called twice
    assert mock_client.insert_event.call_count == 2

    # Verify first call has correct metadata
    first_call = mock_client.insert_event.call_args_list[0]
    first_event = first_call[0][1]  # Second argument to insert_event
    assert first_event.data["message"] == "lunch"
    assert first_event.data["split"] is True
    assert first_event.data["split_count"] == 2
    assert first_event.data["split_index"] == 0
    assert "split_id" in first_event.data

    # Verify second call has correct metadata
    second_call = mock_client.insert_event.call_args_list[1]
    second_event = second_call[0][1]
    assert second_event.data["message"] == "phone"
    assert second_event.data["split"] is True
    assert second_event.data["split_count"] == 2
    assert second_event.data["split_index"] == 1
    assert "split_id" in second_event.data

    # Verify same split_id for both
    assert first_event.data["split_id"] == second_event.data["split_id"]


def test_post_split_events_preserves_timestamps() -> None:
    """Test that split events preserve the correct timestamps and durations."""
    mock_client = Mock()
    mock_client.client_hostname = "test_host"
    mock_client.get_buckets.return_value = {
        "aw-watcher-afk_test_host": {"type": "afkstatus"},
        "aw-watcher-ask-away_test_host": {"type": "afktask"},
    }
    mock_client.get_events.return_value = []
    mock_client.insert_event = Mock()

    client = AWAskAwayClient(mock_client, enable_lid_events=False)

    original_start = datetime(2025, 1, 15, 14, 0, 0, tzinfo=UTC)
    original_event = aw_core.Event(
        timestamp=original_start,
        duration=timedelta(minutes=45, seconds=30),
        data={"status": "afk"},
    )

    activities = [
        ActivityLine("first", original_start, 10, 15),
        ActivityLine("second", original_start + timedelta(minutes=10, seconds=15), 20, 30),
        ActivityLine("third", original_start + timedelta(minutes=30, seconds=45), 14, 45),
    ]

    client.post_split_events(original_event, activities)

    # Verify correct number of calls
    assert mock_client.insert_event.call_count == 3

    # Check timestamps and durations
    calls = mock_client.insert_event.call_args_list

    # First activity: starts at original_start, duration 10m 15s
    first_event = calls[0][0][1]
    assert first_event.timestamp == original_start
    assert first_event.duration == timedelta(minutes=10, seconds=15)

    # Second activity: starts 10m 15s later, duration 20m 30s
    second_event = calls[1][0][1]
    assert second_event.timestamp == original_start + timedelta(minutes=10, seconds=15)
    assert second_event.duration == timedelta(minutes=20, seconds=30)

    # Third activity: starts 30m 45s later, duration 14m 45s
    third_event = calls[2][0][1]
    assert third_event.timestamp == original_start + timedelta(minutes=30, seconds=45)
    assert third_event.duration == timedelta(minutes=14, seconds=45)


def test_post_split_events_marks_original_as_seen_on_success() -> None:
    """Test that original event is marked as seen only after all splits post successfully."""
    mock_client = Mock()
    mock_client.client_hostname = "test_host"
    mock_client.get_buckets.return_value = {
        "aw-watcher-afk_test_host": {"type": "afkstatus"},
        "aw-watcher-ask-away_test_host": {"type": "afktask"},
    }
    mock_client.get_events.return_value = []
    mock_client.insert_event = Mock()  # All succeed

    client = AWAskAwayClient(mock_client, enable_lid_events=False)

    original_start = datetime(2025, 1, 15, 14, 0, 0, tzinfo=UTC)
    original_event = aw_core.Event(
        timestamp=original_start,
        duration=timedelta(minutes=20),
        data={"status": "afk"},
    )

    activities = [
        ActivityLine("first", original_start, 10, 0),
        ActivityLine("second", original_start + timedelta(minutes=10), 10, 0),
    ]

    # State should not have the event initially
    assert not client.state.has_event(original_event)

    # Post split events
    client.post_split_events(original_event, activities)

    # State should now have the event marked as seen
    assert client.state.has_event(original_event)


def test_post_split_events_does_not_mark_seen_on_partial_failure() -> None:
    """Test that original event is NOT marked as seen if any split event fails to post."""
    mock_client = Mock()
    mock_client.client_hostname = "test_host"
    mock_client.get_buckets.return_value = {
        "aw-watcher-afk_test_host": {"type": "afkstatus"},
        "aw-watcher-ask-away_test_host": {"type": "afktask"},
    }
    mock_client.get_events.return_value = []

    # Make the second insert fail
    def insert_side_effect(bucket_id, event):
        if mock_client.insert_event.call_count == 2:
            raise Exception("Network error")

    mock_client.insert_event = Mock(side_effect=insert_side_effect)

    client = AWAskAwayClient(mock_client, enable_lid_events=False)

    original_start = datetime(2025, 1, 15, 14, 0, 0, tzinfo=UTC)
    original_event = aw_core.Event(
        timestamp=original_start,
        duration=timedelta(minutes=20),
        data={"status": "afk"},
    )

    activities = [
        ActivityLine("first", original_start, 10, 0),
        ActivityLine("second", original_start + timedelta(minutes=10), 10, 0),
    ]

    # State should not have the event initially
    assert not client.state.has_event(original_event)

    # Post split events (second one will fail)
    client.post_split_events(original_event, activities)

    # State should still NOT have the event marked as seen
    assert not client.state.has_event(original_event)


def test_post_split_events_split_id_based_on_timestamp() -> None:
    """Test that split_id is consistently generated from the original event timestamp."""
    mock_client = Mock()
    mock_client.client_hostname = "test_host"
    mock_client.get_buckets.return_value = {
        "aw-watcher-afk_test_host": {"type": "afkstatus"},
        "aw-watcher-ask-away_test_host": {"type": "afktask"},
    }
    mock_client.get_events.return_value = []
    mock_client.insert_event = Mock()

    client = AWAskAwayClient(mock_client, enable_lid_events=False)

    # Use a specific timestamp
    original_start = datetime(2025, 1, 15, 14, 30, 45, tzinfo=UTC)
    original_event = aw_core.Event(
        timestamp=original_start,
        duration=timedelta(minutes=20),
        data={"status": "afk"},
    )

    activities = [
        ActivityLine("first", original_start, 10, 0),
        ActivityLine("second", original_start + timedelta(minutes=10), 10, 0),
    ]

    client.post_split_events(original_event, activities)

    # Get the split_id from the first posted event
    first_call = mock_client.insert_event.call_args_list[0]
    first_event = first_call[0][1]
    split_id = first_event.data["split_id"]

    # Verify split_id is the timestamp as a string
    expected_split_id = str(original_start.timestamp())
    assert split_id == expected_split_id


def test_post_split_events_with_seconds() -> None:
    """Test that split events correctly handle durations with seconds."""
    mock_client = Mock()
    mock_client.client_hostname = "test_host"
    mock_client.get_buckets.return_value = {
        "aw-watcher-afk_test_host": {"type": "afkstatus"},
        "aw-watcher-ask-away_test_host": {"type": "afktask"},
    }
    mock_client.get_events.return_value = []
    mock_client.insert_event = Mock()

    client = AWAskAwayClient(mock_client, enable_lid_events=False)

    original_start = datetime(2025, 1, 15, 14, 0, 0, tzinfo=UTC)
    original_event = aw_core.Event(
        timestamp=original_start,
        duration=timedelta(minutes=5, seconds=37),
        data={"status": "afk"},
    )

    activities = [
        ActivityLine("first", original_start, 2, 45),
        ActivityLine("second", original_start + timedelta(minutes=2, seconds=45), 2, 52),
    ]

    client.post_split_events(original_event, activities)

    # Verify durations include seconds
    first_event = mock_client.insert_event.call_args_list[0][0][1]
    assert first_event.duration == timedelta(minutes=2, seconds=45)

    second_event = mock_client.insert_event.call_args_list[1][0][1]
    assert second_event.duration == timedelta(minutes=2, seconds=52)
