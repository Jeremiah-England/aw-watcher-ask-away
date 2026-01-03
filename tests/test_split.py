"""Unit tests for split AFK period functionality."""

from datetime import UTC, datetime, timedelta

import pytest

from aw_watcher_ask_away.split_dialog import (
    ActivityLine,
    SplitActivityData,
    TimeCalculator,
)


class TestActivityLine:
    """Test ActivityLine dataclass."""

    def test_activity_line_creation(self) -> None:
        """Test creating an ActivityLine."""
        start = datetime(2025, 1, 15, 14, 30, 0, tzinfo=UTC)
        activity = ActivityLine(
            description="lunch",
            start_time=start,
            duration_minutes=20,
            duration_seconds=30
        )

        assert activity.description == "lunch"
        assert activity.start_time == start
        assert activity.duration_minutes == 20
        assert activity.duration_seconds == 30

    def test_end_time_calculation(self) -> None:
        """Test end_time property calculates correctly."""
        start = datetime(2025, 1, 15, 14, 30, 0, tzinfo=UTC)
        activity = ActivityLine(
            description="meeting",
            start_time=start,
            duration_minutes=45,
            duration_seconds=15
        )

        expected_end = start + timedelta(minutes=45, seconds=15)
        assert activity.end_time == expected_end

    def test_total_duration_seconds(self) -> None:
        """Test total_duration_seconds property."""
        activity = ActivityLine(
            description="test",
            start_time=datetime(2025, 1, 15, 10, 0, 0, tzinfo=UTC),
            duration_minutes=5,
            duration_seconds=30
        )

        assert activity.total_duration_seconds == 5 * 60 + 30

    def test_negative_duration_minutes_rejected(self) -> None:
        """Test that negative duration_minutes raises ValueError."""
        with pytest.raises(ValueError, match="Duration cannot be negative"):
            ActivityLine(
                description="test",
                start_time=datetime(2025, 1, 15, 10, 0, 0, tzinfo=UTC),
                duration_minutes=-5,
                duration_seconds=0
            )

    def test_invalid_duration_seconds_rejected(self) -> None:
        """Test that invalid duration_seconds raises ValueError."""
        with pytest.raises(ValueError, match="Duration seconds must be in"):
            ActivityLine(
                description="test",
                start_time=datetime(2025, 1, 15, 10, 0, 0, tzinfo=UTC),
                duration_minutes=5,
                duration_seconds=65
            )


class TestSplitActivityData:
    """Test SplitActivityData dataclass and validation."""

    def test_valid_split_data(self) -> None:
        """Test validation passes for valid data."""
        start = datetime(2025, 1, 15, 14, 0, 0, tzinfo=UTC)
        activities = [
            ActivityLine("lunch", start, 20, 0),
            ActivityLine("phone", start + timedelta(minutes=20), 10, 0)
        ]

        data = SplitActivityData(
            original_start=start,
            original_duration_seconds=30 * 60,
            activities=activities
        )

        assert data.is_valid()
        assert len(data.validate()) == 0

    def test_first_activity_wrong_start(self) -> None:
        """Test validation fails if first activity doesn't start at AFK period start."""
        start = datetime(2025, 1, 15, 14, 0, 0, tzinfo=UTC)
        wrong_start = start + timedelta(minutes=5)
        activities = [
            ActivityLine("test", wrong_start, 30, 0)
        ]

        data = SplitActivityData(
            original_start=start,
            original_duration_seconds=30 * 60,
            activities=activities
        )

        assert not data.is_valid()
        errors = data.validate()
        assert any("First activity must start" in e for e in errors)

    def test_gap_detected(self) -> None:
        """Test validation detects gaps between activities."""
        start = datetime(2025, 1, 15, 14, 0, 0, tzinfo=UTC)
        activities = [
            ActivityLine("lunch", start, 20, 0),
            # Gap of 5 minutes
            ActivityLine("phone", start + timedelta(minutes=25), 5, 0)
        ]

        data = SplitActivityData(
            original_start=start,
            original_duration_seconds=30 * 60,
            activities=activities
        )

        assert not data.is_valid()
        errors = data.validate()
        assert any("Gap detected" in e for e in errors)

    def test_overlap_detected(self) -> None:
        """Test validation detects overlaps between activities."""
        start = datetime(2025, 1, 15, 14, 0, 0, tzinfo=UTC)
        activities = [
            ActivityLine("lunch", start, 20, 0),
            # Overlap: starts 5 minutes early
            ActivityLine("phone", start + timedelta(minutes=15), 10, 0)
        ]

        data = SplitActivityData(
            original_start=start,
            original_duration_seconds=30 * 60,
            activities=activities
        )

        assert not data.is_valid()
        errors = data.validate()
        assert any("Overlap detected" in e for e in errors)

    def test_minimum_duration_enforced(self) -> None:
        """Test validation enforces minimum 1 minute duration."""
        start = datetime(2025, 1, 15, 14, 0, 0, tzinfo=UTC)
        activities = [
            ActivityLine("short", start, 0, 30),  # 30 seconds, too short
            ActivityLine("rest", start + timedelta(seconds=30), 29, 30)
        ]

        data = SplitActivityData(
            original_start=start,
            original_duration_seconds=30 * 60,
            activities=activities
        )

        assert not data.is_valid()
        errors = data.validate()
        assert any("duration must be at least 1 minute" in e for e in errors)

    def test_last_activity_wrong_end(self) -> None:
        """Test validation fails if last activity doesn't end at AFK period end."""
        start = datetime(2025, 1, 15, 14, 0, 0, tzinfo=UTC)
        activities = [
            ActivityLine("test", start, 20, 0)  # Ends 10 minutes early
        ]

        data = SplitActivityData(
            original_start=start,
            original_duration_seconds=30 * 60,
            activities=activities
        )

        assert not data.is_valid()
        errors = data.validate()
        assert any("Last activity must end" in e for e in errors)

    def test_total_duration_mismatch(self) -> None:
        """Test validation fails if total duration doesn't match."""
        start = datetime(2025, 1, 15, 14, 0, 0, tzinfo=UTC)
        activities = [
            ActivityLine("test1", start, 10, 0),
            ActivityLine("test2", start + timedelta(minutes=10), 10, 0)
        ]

        data = SplitActivityData(
            original_start=start,
            original_duration_seconds=30 * 60,  # Should be 20 * 60
            activities=activities
        )

        assert not data.is_valid()
        errors = data.validate()
        assert any("Total duration mismatch" in e for e in errors)

    def test_rounding_tolerance(self) -> None:
        """Test validation allows 1 second tolerance for rounding."""
        start = datetime(2025, 1, 15, 14, 0, 0, tzinfo=UTC)
        # Total: 29 minutes 59 seconds (1 second short, should be tolerated)
        activities = [
            ActivityLine("test1", start, 15, 0),
            ActivityLine("test2", start + timedelta(minutes=15), 14, 59)
        ]

        data = SplitActivityData(
            original_start=start,
            original_duration_seconds=30 * 60,
            activities=activities
        )

        assert data.is_valid()


class TestTimeCalculatorSplitEqual:
    """Test TimeCalculator.split_equal() method."""

    def test_split_into_two_equal(self) -> None:
        """Test splitting into 2 equal activities."""
        start = datetime(2025, 1, 15, 14, 0, 0, tzinfo=UTC)
        duration = 30 * 60  # 30 minutes

        activities = TimeCalculator.split_equal(start, duration, 2)

        assert len(activities) == 2
        assert activities[0].start_time == start
        assert activities[0].duration_minutes == 15
        assert activities[1].start_time == start + timedelta(minutes=15)
        assert activities[1].duration_minutes == 15

    def test_split_into_three_equal(self) -> None:
        """Test splitting into 3 equal activities."""
        start = datetime(2025, 1, 15, 14, 0, 0, tzinfo=UTC)
        duration = 30 * 60  # 30 minutes

        activities = TimeCalculator.split_equal(start, duration, 3)

        assert len(activities) == 3
        assert all(a.duration_minutes == 10 for a in activities)

    def test_split_odd_duration(self) -> None:
        """Test splitting odd duration distributes remainder to last activity."""
        start = datetime(2025, 1, 15, 14, 0, 0, tzinfo=UTC)
        duration = 37 * 60 + 35  # 37 minutes 35 seconds

        activities = TimeCalculator.split_equal(start, duration, 2)

        assert len(activities) == 2
        # First: 18 minutes 47 seconds
        assert activities[0].duration_minutes == 18
        assert activities[0].duration_seconds == 47
        # Last gets remainder to exactly match total
        total_seconds = sum(a.total_duration_seconds for a in activities)
        assert total_seconds == duration

    def test_split_with_descriptions(self) -> None:
        """Test splitting with custom descriptions."""
        start = datetime(2025, 1, 15, 14, 0, 0, tzinfo=UTC)
        duration = 30 * 60
        descriptions = ["lunch", "phone call"]

        activities = TimeCalculator.split_equal(start, duration, 2, descriptions)

        assert activities[0].description == "lunch"
        assert activities[1].description == "phone call"

    def test_split_invalid_num_activities(self) -> None:
        """Test split with invalid number of activities raises error."""
        start = datetime(2025, 1, 15, 14, 0, 0, tzinfo=UTC)

        with pytest.raises(ValueError, match="Must create at least 1 activity"):
            TimeCalculator.split_equal(start, 1800, 0)

    def test_split_description_count_mismatch(self) -> None:
        """Test split with wrong number of descriptions raises error."""
        start = datetime(2025, 1, 15, 14, 0, 0, tzinfo=UTC)

        with pytest.raises(ValueError, match="Expected 2 descriptions"):
            TimeCalculator.split_equal(start, 1800, 2, ["only one"])


class TestTimeCalculatorAdjustDuration:
    """Test TimeCalculator.adjust_duration() method."""

    def test_increase_duration(self) -> None:
        """Test increasing an activity's duration."""
        start = datetime(2025, 1, 15, 14, 0, 0, tzinfo=UTC)
        activities = [
            ActivityLine("lunch", start, 15, 0),
            ActivityLine("phone", start + timedelta(minutes=15), 15, 0)
        ]

        # Increase first activity from 15 to 20 minutes
        new_activities = TimeCalculator.adjust_duration(activities, 0, 20)

        assert new_activities[0].duration_minutes == 20
        # Second activity shifts start time
        assert new_activities[1].start_time == start + timedelta(minutes=20)
        assert new_activities[1].duration_minutes == 15

    def test_decrease_duration(self) -> None:
        """Test decreasing an activity's duration."""
        start = datetime(2025, 1, 15, 14, 0, 0, tzinfo=UTC)
        activities = [
            ActivityLine("lunch", start, 20, 0),
            ActivityLine("phone", start + timedelta(minutes=20), 10, 0)
        ]

        # Decrease first activity from 20 to 15 minutes
        new_activities = TimeCalculator.adjust_duration(activities, 0, 15)

        assert new_activities[0].duration_minutes == 15
        # Second activity shifts start time earlier
        assert new_activities[1].start_time == start + timedelta(minutes=15)

    def test_adjust_middle_activity(self) -> None:
        """Test adjusting a middle activity affects all subsequent ones."""
        start = datetime(2025, 1, 15, 14, 0, 0, tzinfo=UTC)
        activities = [
            ActivityLine("a", start, 10, 0),
            ActivityLine("b", start + timedelta(minutes=10), 10, 0),
            ActivityLine("c", start + timedelta(minutes=20), 10, 0)
        ]

        # Increase middle activity from 10 to 15 minutes
        new_activities = TimeCalculator.adjust_duration(activities, 1, 15)

        assert new_activities[0].duration_minutes == 10  # Unchanged
        assert new_activities[1].duration_minutes == 15  # Changed
        # Third activity shifts
        assert new_activities[2].start_time == start + timedelta(minutes=25)

    def test_adjust_minimum_duration(self) -> None:
        """Test cannot set duration below 1 minute."""
        start = datetime(2025, 1, 15, 14, 0, 0, tzinfo=UTC)
        activities = [ActivityLine("test", start, 5, 0)]

        with pytest.raises(ValueError, match="Duration must be at least 1 minute"):
            TimeCalculator.adjust_duration(activities, 0, 0)

    def test_adjust_invalid_index(self) -> None:
        """Test adjusting with invalid index raises error."""
        activities = [ActivityLine("test", datetime(2025, 1, 1, 10, 0, 0, tzinfo=UTC), 10, 0)]

        with pytest.raises(ValueError, match="Invalid index"):
            TimeCalculator.adjust_duration(activities, 5, 10)


class TestTimeCalculatorAdjustStartTime:
    """Test TimeCalculator.adjust_start_time() method."""

    def test_adjust_start_time_second_activity(self) -> None:
        """Test adjusting start time of second activity."""
        start = datetime(2025, 1, 15, 14, 0, 0, tzinfo=UTC)
        activities = [
            ActivityLine("lunch", start, 20, 0),
            ActivityLine("phone", start + timedelta(minutes=20), 10, 0)
        ]

        # Move second activity to start 5 minutes earlier
        new_start = start + timedelta(minutes=15)
        new_activities = TimeCalculator.adjust_start_time(activities, 1, new_start)

        # First activity's duration adjusted to 15 minutes
        assert new_activities[0].duration_minutes == 15
        # Second activity starts at new time
        assert new_activities[1].start_time == new_start

    def test_adjust_middle_activity_start(self) -> None:
        """Test adjusting middle activity affects previous and subsequent activities."""
        start = datetime(2025, 1, 15, 14, 0, 0, tzinfo=UTC)
        activities = [
            ActivityLine("a", start, 10, 0),
            ActivityLine("b", start + timedelta(minutes=10), 10, 0),
            ActivityLine("c", start + timedelta(minutes=20), 10, 0)
        ]

        # Move middle activity to start 5 minutes later
        new_start = start + timedelta(minutes=15)
        new_activities = TimeCalculator.adjust_start_time(activities, 1, new_start)

        # First activity's duration increased to 15 minutes
        assert new_activities[0].duration_minutes == 15
        # Second activity starts at new time
        assert new_activities[1].start_time == new_start
        # Third activity shifts
        assert new_activities[2].start_time == new_start + timedelta(minutes=10)

    def test_cannot_adjust_first_activity(self) -> None:
        """Test cannot adjust start time of first activity."""
        start = datetime(2025, 1, 15, 14, 0, 0, tzinfo=UTC)
        activities = [ActivityLine("test", start, 10, 0)]

        with pytest.raises(ValueError, match="Invalid index.*must be > 0"):
            TimeCalculator.adjust_start_time(activities, 0, start + timedelta(minutes=5))

    def test_adjust_would_make_previous_too_short(self) -> None:
        """Test error if adjustment would make previous activity < 1 minute."""
        start = datetime(2025, 1, 15, 14, 0, 0, tzinfo=UTC)
        activities = [
            ActivityLine("a", start, 5, 0),
            ActivityLine("b", start + timedelta(minutes=5), 5, 0)
        ]

        # Try to move second activity too early
        new_start = start + timedelta(seconds=30)  # Only 30 seconds for first activity

        with pytest.raises(ValueError, match="Adjusted duration would be less than 1 minute"):
            TimeCalculator.adjust_start_time(activities, 1, new_start)


class TestTimeCalculatorAddActivity:
    """Test TimeCalculator.add_activity() method."""

    def test_add_with_equal_distribution(self) -> None:
        """Test adding activity with equal distribution."""
        start = datetime(2025, 1, 15, 14, 0, 0, tzinfo=UTC)
        duration = 30 * 60
        activities = [
            ActivityLine("lunch", start, 30, 0)
        ]

        new_activities = TimeCalculator.add_activity(
            activities,
            start + timedelta(seconds=duration),
            equal_distribution=True,
            original_start=start,
            original_duration_seconds=duration
        )

        # Now 2 activities with 15 minutes each
        assert len(new_activities) == 2
        assert new_activities[0].duration_minutes == 15
        assert new_activities[1].duration_minutes == 15
        assert new_activities[0].description == "lunch"
        assert new_activities[1].description == ""

    def test_add_borrowing_from_last(self) -> None:
        """Test adding activity by borrowing time from last activity."""
        start = datetime(2025, 1, 15, 14, 0, 0, tzinfo=UTC)
        duration = 30 * 60
        activities = [
            ActivityLine("lunch", start, 15, 0),
            ActivityLine("phone", start + timedelta(minutes=15), 15, 0)
        ]

        original_end = start + timedelta(seconds=duration)
        new_activities = TimeCalculator.add_activity(
            activities,
            original_end,
            equal_distribution=False
        )

        # Last activity gets remaining time
        assert len(new_activities) == 3
        # New activity at the end
        assert new_activities[2].description == ""

    def test_cannot_add_if_last_too_short(self) -> None:
        """Test cannot add activity if last one is only 1 minute."""
        start = datetime(2025, 1, 15, 14, 0, 0, tzinfo=UTC)
        activities = [
            ActivityLine("a", start, 29, 0),
            ActivityLine("b", start + timedelta(minutes=29), 1, 0)
        ]

        with pytest.raises(ValueError, match="Last activity must have more than 1 minute"):
            TimeCalculator.add_activity(
                activities,
                start + timedelta(minutes=30),
                equal_distribution=False
            )

    def test_add_requires_params_for_equal_distribution(self) -> None:
        """Test equal distribution requires original_start and original_duration_seconds."""
        activities = [ActivityLine("test", datetime(2025, 1, 1, 10, 0, 0, tzinfo=UTC), 10, 0)]

        with pytest.raises(ValueError, match="required for equal distribution"):
            TimeCalculator.add_activity(
                activities,
                datetime(2025, 1, 1, 10, 10, 0, tzinfo=UTC),
                equal_distribution=True
            )


class TestTimeCalculatorRemoveActivity:
    """Test TimeCalculator.remove_activity() method."""

    def test_remove_first_activity(self) -> None:
        """Test removing first activity adds its duration to next one."""
        start = datetime(2025, 1, 15, 14, 0, 0, tzinfo=UTC)
        activities = [
            ActivityLine("lunch", start, 15, 0),
            ActivityLine("phone", start + timedelta(minutes=15), 15, 0)
        ]

        new_activities = TimeCalculator.remove_activity(activities, 0)

        assert len(new_activities) == 1
        # Remaining activity starts at original start and has combined duration
        assert new_activities[0].start_time == start
        assert new_activities[0].duration_minutes == 30
        assert new_activities[0].description == "phone"

    def test_remove_last_activity(self) -> None:
        """Test removing last activity adds its duration to previous one."""
        start = datetime(2025, 1, 15, 14, 0, 0, tzinfo=UTC)
        activities = [
            ActivityLine("lunch", start, 15, 0),
            ActivityLine("phone", start + timedelta(minutes=15), 15, 0)
        ]

        new_activities = TimeCalculator.remove_activity(activities, 1)

        assert len(new_activities) == 1
        # Remaining activity has combined duration
        assert new_activities[0].duration_minutes == 30
        assert new_activities[0].description == "lunch"

    def test_remove_middle_activity(self) -> None:
        """Test removing middle activity adds duration to previous one."""
        start = datetime(2025, 1, 15, 14, 0, 0, tzinfo=UTC)
        activities = [
            ActivityLine("a", start, 10, 0),
            ActivityLine("b", start + timedelta(minutes=10), 10, 0),
            ActivityLine("c", start + timedelta(minutes=20), 10, 0)
        ]

        new_activities = TimeCalculator.remove_activity(activities, 1)

        assert len(new_activities) == 2
        # First activity gets middle activity's duration
        assert new_activities[0].duration_minutes == 20
        # Last activity shifts start time
        assert new_activities[1].start_time == start + timedelta(minutes=20)

    def test_remove_only_activity(self) -> None:
        """Test removing the only activity returns empty list."""
        activities = [ActivityLine("only", datetime(2025, 1, 1, 10, 0, 0, tzinfo=UTC), 10, 0)]

        new_activities = TimeCalculator.remove_activity(activities, 0)

        assert len(new_activities) == 0

    def test_remove_invalid_index(self) -> None:
        """Test removing with invalid index raises error."""
        activities = [ActivityLine("test", datetime(2025, 1, 1, 10, 0, 0, tzinfo=UTC), 10, 0)]

        with pytest.raises(ValueError, match="Invalid index"):
            TimeCalculator.remove_activity(activities, 5)


class TestTimeCalculatorIntegration:
    """Integration tests for TimeCalculator operations."""

    def test_split_adjust_validate_workflow(self) -> None:
        """Test complete workflow: split, adjust, validate."""
        start = datetime(2025, 1, 15, 14, 0, 0, tzinfo=UTC)
        duration = 37 * 60 + 35  # 37 minutes 35 seconds
        original_end = start + timedelta(seconds=duration)

        # Split into 2 equal activities
        activities = TimeCalculator.split_equal(start, duration, 2)

        # Adjust first activity to 20 minutes (with original_end to adjust last activity)
        activities = TimeCalculator.adjust_duration(activities, 0, 20, original_end)

        # Create SplitActivityData and validate
        data = SplitActivityData(
            original_start=start,
            original_duration_seconds=duration,
            activities=activities
        )

        assert data.is_valid()

    def test_add_remove_maintains_consistency(self) -> None:
        """Test adding then removing maintains consistency."""
        start = datetime(2025, 1, 15, 14, 0, 0, tzinfo=UTC)
        duration = 30 * 60

        # Start with 2 activities
        activities = TimeCalculator.split_equal(start, duration, 2)

        # Add a third
        activities = TimeCalculator.add_activity(
            activities,
            start + timedelta(seconds=duration),
            equal_distribution=True,
            original_start=start,
            original_duration_seconds=duration
        )

        # Verify we have 3
        assert len(activities) == 3

        # Remove the middle one
        activities = TimeCalculator.remove_activity(activities, 1)

        # Verify we're back to 2
        assert len(activities) == 2

        # Validate consistency
        data = SplitActivityData(
            original_start=start,
            original_duration_seconds=duration,
            activities=activities
        )
        assert data.is_valid()
