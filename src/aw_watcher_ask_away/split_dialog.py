"""Split AFK period dialog - allows dividing a single AFK period into multiple activities.

This module provides data structures and logic for splitting an AFK period into
multiple sequential activities with different descriptions and time allocations.
"""

import logging
import tkinter as tk
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from tkinter import simpledialog, ttk
from typing import Optional

from aw_watcher_ask_away.utils import format_time_local

logger = logging.getLogger(__name__)


@dataclass
class ActivityLine:
    """Represents a single activity in a split AFK period.

    Each activity has a description, start time, and duration. Activities are
    sequential (no gaps or overlaps) within the parent AFK period.

    Attributes:
        description: User-provided description of the activity
        start_time: When the activity started (datetime with timezone)
        duration_minutes: How long the activity lasted (in minutes, integer)
        duration_seconds: Additional seconds beyond duration_minutes (for internal precision)
    """

    description: str
    start_time: datetime
    duration_minutes: int
    duration_seconds: int = 0  # Internal precision for sub-minute accuracy

    @property
    def end_time(self) -> datetime:
        """Calculate the end time of this activity."""
        return self.start_time + timedelta(minutes=self.duration_minutes, seconds=self.duration_seconds)

    @property
    def total_duration_seconds(self) -> float:
        """Get total duration in seconds (including sub-minute precision)."""
        return self.duration_minutes * 60 + self.duration_seconds

    def __post_init__(self) -> None:
        """Validate the activity line after initialization."""
        if self.duration_minutes < 0:
            raise ValueError(f"Duration cannot be negative: {self.duration_minutes}")
        if self.duration_seconds < 0 or self.duration_seconds >= 60:
            raise ValueError(f"Duration seconds must be in [0, 60): {self.duration_seconds}")


@dataclass
class SplitActivityData:
    """Container for all activity lines in a split AFK period.

    Maintains consistency constraints:
    - No gaps between activities
    - No overlaps between activities
    - Total duration equals original AFK period duration
    - First activity starts at AFK period start
    - Last activity ends at AFK period end

    Attributes:
        original_start: Start time of the original AFK period
        original_duration_seconds: Total duration of the original AFK period in seconds
        activities: List of ActivityLine objects (must be chronologically ordered)
    """

    original_start: datetime
    original_duration_seconds: float
    activities: list[ActivityLine] = field(default_factory=list)

    @property
    def original_end(self) -> datetime:
        """Calculate the end time of the original AFK period."""
        return self.original_start + timedelta(seconds=self.original_duration_seconds)

    def validate(self) -> list[str]:
        """Validate the split activity data and return list of errors.

        Returns:
            List of error messages (empty if valid)
        """
        errors = []

        if not self.activities:
            errors.append("No activities defined")
            return errors

        # Check first activity starts at AFK period start
        if self.activities[0].start_time != self.original_start:
            errors.append(
                f"First activity must start at AFK period start "
                f"({self.original_start.isoformat()}), "
                f"got {self.activities[0].start_time.isoformat()}"
            )

        # Check for gaps and overlaps between consecutive activities
        for i in range(len(self.activities) - 1):
            current = self.activities[i]
            next_activity = self.activities[i + 1]

            # Check minimum duration
            if current.duration_minutes < 1:
                errors.append(f"Activity {i+1} duration must be at least 1 minute")

            # Check no gap between activities (allow ±1 second tolerance for rounding)
            if current.end_time != next_activity.start_time:
                gap_seconds = (next_activity.start_time - current.end_time).total_seconds()
                if abs(gap_seconds) > 1.0:
                    if gap_seconds > 0:
                        errors.append(
                            f"Gap detected between activity {i+1} and {i+2}: {gap_seconds:.1f} seconds"
                        )
                    else:
                        errors.append(
                            f"Overlap detected between activity {i+1} and {i+2}: {-gap_seconds:.1f} seconds"
                        )

        # Check last activity minimum duration
        if self.activities and self.activities[-1].duration_minutes < 1:
            errors.append(f"Activity {len(self.activities)} duration must be at least 1 minute")

        # Check last activity ends at AFK period end (with 30 second tolerance for rounding)
        if self.activities:
            last_end = self.activities[-1].end_time
            expected_end = self.original_end
            diff_seconds = abs((last_end - expected_end).total_seconds())
            if diff_seconds > 30.0:
                errors.append(
                    f"Last activity must end at AFK period end "
                    f"({expected_end.isoformat()}), "
                    f"got {last_end.isoformat()} (diff: {diff_seconds:.1f}s)"
                )

        # Check total duration matches original (with 30 second tolerance for rounding)
        if self.activities:
            total_seconds = sum(a.total_duration_seconds for a in self.activities)
            diff = abs(total_seconds - self.original_duration_seconds)
            if diff > 30.0:
                errors.append(
                    f"Total duration mismatch: expected {self.original_duration_seconds:.1f}s, "
                    f"got {total_seconds:.1f}s (diff: {diff:.1f}s)"
                )

        return errors

    def is_valid(self) -> bool:
        """Check if all activities form a valid, consistent timeline.

        Returns:
            True if valid, False otherwise
        """
        return len(self.validate()) == 0


class TimeCalculator:
    """Utility class for time calculations and consistency enforcement.

    Handles automatic adjustment of activity times to maintain consistency
    when user edits duration or start time fields.
    """

    @staticmethod
    def split_equal(
        start: datetime,
        duration_seconds: float,
        num_activities: int,
        descriptions: Optional[list[str]] = None
    ) -> list[ActivityLine]:
        """Split an AFK period into equal-duration activities.

        Args:
            start: Start time of the AFK period
            duration_seconds: Total duration in seconds
            num_activities: Number of activities to create
            descriptions: Optional list of descriptions (default: empty strings)

        Returns:
            List of ActivityLine objects with equal durations
        """
        if num_activities < 1:
            raise ValueError("Must create at least 1 activity")

        if descriptions is None:
            descriptions = [""] * num_activities
        elif len(descriptions) != num_activities:
            raise ValueError(f"Expected {num_activities} descriptions, got {len(descriptions)}")

        # Calculate duration per activity
        seconds_per_activity = duration_seconds / num_activities
        minutes_per_activity = int(seconds_per_activity // 60)

        activities = []
        current_start = start

        for i in range(num_activities):
            # For the last activity, calculate duration to exactly reach the end
            if i == num_activities - 1:
                remaining_seconds = duration_seconds - sum(a.total_duration_seconds for a in activities)
                duration_mins = int(remaining_seconds // 60)
                duration_secs = int(remaining_seconds % 60)
            else:
                duration_mins = minutes_per_activity
                duration_secs = int(seconds_per_activity % 60)

            activity = ActivityLine(
                description=descriptions[i],
                start_time=current_start,
                duration_minutes=duration_mins,
                duration_seconds=duration_secs
            )
            activities.append(activity)
            current_start = activity.end_time

        return activities

    @staticmethod
    def adjust_duration(
        activities: list[ActivityLine],
        index: int,
        new_duration_minutes: int,
        original_end: Optional[datetime] = None
    ) -> list[ActivityLine]:
        """Adjust the duration of an activity and update subsequent activities.

        When a user changes the duration of an activity:
        - All subsequent activities' start times shift accordingly
        - If original_end is provided, the last activity's duration adjusts to maintain total consistency

        Args:
            activities: Current list of activities
            index: Index of the activity to adjust
            new_duration_minutes: New duration in minutes
            original_end: Optional end time of original AFK period (for adjusting last activity)

        Returns:
            New list of activities with adjustments applied
        """
        if not activities or index < 0 or index >= len(activities):
            raise ValueError(f"Invalid index: {index}")

        if new_duration_minutes < 1:
            raise ValueError("Duration must be at least 1 minute")

        # Special case: if changing the LAST activity and original_end is provided,
        # adjust the PREVIOUS activity instead to maintain total duration
        if index == len(activities) - 1 and original_end is not None and len(activities) > 1:
            # The last activity must end at original_end, so calculate its new start time
            new_last_duration = timedelta(minutes=new_duration_minutes, seconds=activities[index].duration_seconds)
            new_last_start = original_end - new_last_duration

            # The previous activity must end at the new last activity's start
            prev_activity = activities[index - 1]
            prev_new_duration_seconds = (new_last_start - prev_activity.start_time).total_seconds()

            if prev_new_duration_seconds < 60:
                raise ValueError("Adjustment would make previous activity less than 1 minute")

            prev_new_duration_minutes = int(prev_new_duration_seconds // 60)

            # Recursively adjust the previous activity
            # This will handle cascading changes if there are more activities
            return TimeCalculator.adjust_duration(
                activities,
                index=index - 1,
                new_duration_minutes=prev_new_duration_minutes,
                original_end=original_end
            )

        # Create a copy to avoid mutating the original
        new_activities = []
        for i, activity in enumerate(activities):
            if i < index:
                # Activities before the changed one remain the same
                new_activities.append(ActivityLine(
                    description=activity.description,
                    start_time=activity.start_time,
                    duration_minutes=activity.duration_minutes,
                    duration_seconds=activity.duration_seconds
                ))
            elif i == index:
                # This is the activity being changed
                new_activities.append(ActivityLine(
                    description=activity.description,
                    start_time=activity.start_time,
                    duration_minutes=new_duration_minutes,
                    duration_seconds=activity.duration_seconds
                ))
            elif i == len(activities) - 1 and original_end is not None:
                # Last activity: adjust duration to reach original_end
                prev_end = new_activities[-1].end_time
                remaining_seconds = (original_end - prev_end).total_seconds()
                if remaining_seconds < 60:
                    raise ValueError("Adjusted duration would make last activity less than 1 minute")

                new_activities.append(ActivityLine(
                    description=activity.description,
                    start_time=prev_end,
                    duration_minutes=int(remaining_seconds // 60),
                    duration_seconds=int(remaining_seconds % 60)
                ))
            else:
                # Subsequent activities: shift start time based on previous activity's end
                prev_end = new_activities[-1].end_time
                new_activities.append(ActivityLine(
                    description=activity.description,
                    start_time=prev_end,
                    duration_minutes=activity.duration_minutes,
                    duration_seconds=activity.duration_seconds
                ))

        return new_activities

    @staticmethod
    def adjust_start_time(
        activities: list[ActivityLine],
        index: int,
        new_start: datetime,
        original_end: Optional[datetime] = None
    ) -> list[ActivityLine]:
        """Adjust the start time of an activity and update related activities.

        When a user changes the start time of an activity (not the first one):
        - Previous activity's duration adjusts to reach the new start time
        - All subsequent activities shift their start times accordingly
        - If original_end is provided, the last activity's duration adjusts to maintain total consistency

        Args:
            activities: Current list of activities
            index: Index of the activity to adjust (must be > 0)
            new_start: New start time
            original_end: Optional end time of original AFK period (for adjusting last activity)

        Returns:
            New list of activities with adjustments applied
        """
        if not activities or index <= 0 or index >= len(activities):
            raise ValueError(f"Invalid index: {index} (must be > 0)")

        # Create a copy to avoid mutating the original
        new_activities = []
        for i, activity in enumerate(activities):
            if i < index - 1:
                # Activities before the previous one remain the same
                new_activities.append(ActivityLine(
                    description=activity.description,
                    start_time=activity.start_time,
                    duration_minutes=activity.duration_minutes,
                    duration_seconds=activity.duration_seconds
                ))
            elif i == index - 1:
                # Previous activity: adjust duration to reach new start time
                new_duration_seconds = (new_start - activity.start_time).total_seconds()
                if new_duration_seconds < 60:
                    raise ValueError("Adjusted duration would be less than 1 minute")

                new_activities.append(ActivityLine(
                    description=activity.description,
                    start_time=activity.start_time,
                    duration_minutes=int(new_duration_seconds // 60),
                    duration_seconds=int(new_duration_seconds % 60)
                ))
            elif i == index:
                # This is the activity being changed
                if i == len(activities) - 1 and original_end is not None:
                    # This is also the last activity: adjust duration to reach original_end
                    remaining_seconds = (original_end - new_start).total_seconds()
                    if remaining_seconds < 60:
                        raise ValueError("Adjusted duration would make last activity less than 1 minute")

                    new_activities.append(ActivityLine(
                        description=activity.description,
                        start_time=new_start,
                        duration_minutes=int(remaining_seconds // 60),
                        duration_seconds=int(remaining_seconds % 60)
                    ))
                else:
                    # Not the last activity: keep original duration
                    new_activities.append(ActivityLine(
                        description=activity.description,
                        start_time=new_start,
                        duration_minutes=activity.duration_minutes,
                        duration_seconds=activity.duration_seconds
                    ))
            elif i == len(activities) - 1 and original_end is not None:
                # Last activity: adjust duration to reach original_end
                prev_end = new_activities[-1].end_time
                remaining_seconds = (original_end - prev_end).total_seconds()
                if remaining_seconds < 60:
                    raise ValueError("Adjusted duration would make last activity less than 1 minute")

                new_activities.append(ActivityLine(
                    description=activity.description,
                    start_time=prev_end,
                    duration_minutes=int(remaining_seconds // 60),
                    duration_seconds=int(remaining_seconds % 60)
                ))
            else:
                # Subsequent activities: shift start time based on previous activity's end
                prev_end = new_activities[-1].end_time
                new_activities.append(ActivityLine(
                    description=activity.description,
                    start_time=prev_end,
                    duration_minutes=activity.duration_minutes,
                    duration_seconds=activity.duration_seconds
                ))

        return new_activities

    @staticmethod
    def add_activity(
        activities: list[ActivityLine],
        original_end: datetime,
        equal_distribution: bool = False,
        original_start: Optional[datetime] = None,
        original_duration_seconds: Optional[float] = None
    ) -> list[ActivityLine]:
        """Add a new activity line.

        Args:
            activities: Current list of activities
            original_end: End time of the original AFK period
            equal_distribution: If True, redistribute time equally among all activities
            original_start: Required if equal_distribution is True
            original_duration_seconds: Required if equal_distribution is True

        Returns:
            New list of activities with the added line
        """
        if not activities:
            raise ValueError("Cannot add activity to empty list")

        if equal_distribution:
            if original_start is None or original_duration_seconds is None:
                raise ValueError("original_start and original_duration_seconds required for equal distribution")

            # Redistribute time equally
            descriptions = [a.description for a in activities] + [""]
            return TimeCalculator.split_equal(
                original_start,
                original_duration_seconds,
                len(activities) + 1,
                descriptions
            )
        else:
            # Borrow 1 minute from last activity
            last = activities[-1]
            if last.duration_minutes <= 1:
                raise ValueError("Last activity must have more than 1 minute to add a new line")

            # Create new list with adjusted last activity
            new_activities = activities[:-1] + [
                ActivityLine(
                    description=last.description,
                    start_time=last.start_time,
                    duration_minutes=last.duration_minutes - 1,
                    duration_seconds=last.duration_seconds
                )
            ]

            # Add new activity with 1 minute duration
            new_start = new_activities[-1].end_time
            remaining_seconds = (original_end - new_start).total_seconds()

            new_activities.append(ActivityLine(
                description="",
                start_time=new_start,
                duration_minutes=int(remaining_seconds // 60),
                duration_seconds=int(remaining_seconds % 60)
            ))

            return new_activities

    @staticmethod
    def remove_activity(activities: list[ActivityLine], index: int) -> list[ActivityLine]:
        """Remove an activity line and redistribute its duration.

        The removed activity's duration is added to the previous activity
        (or next activity if removing the first one).

        Args:
            activities: Current list of activities
            index: Index of the activity to remove

        Returns:
            New list of activities with the removed line
        """
        if not activities or index < 0 or index >= len(activities):
            raise ValueError(f"Invalid index: {index}")

        if len(activities) == 1:
            # Removing the last activity - return empty list (exits split mode)
            return []

        removed = activities[index]
        new_activities = []

        if index == 0:
            # Removing first activity: add its duration to the next one
            for i, activity in enumerate(activities):
                if i == 0:
                    continue  # Skip the removed activity
                elif i == 1:
                    # Next activity gets the removed activity's duration
                    total_seconds = removed.total_duration_seconds + activity.total_duration_seconds
                    new_activities.append(ActivityLine(
                        description=activity.description,
                        start_time=removed.start_time,  # Use removed activity's start time
                        duration_minutes=int(total_seconds // 60),
                        duration_seconds=int(total_seconds % 60)
                    ))
                else:
                    # Subsequent activities shift start times
                    prev_end = new_activities[-1].end_time
                    new_activities.append(ActivityLine(
                        description=activity.description,
                        start_time=prev_end,
                        duration_minutes=activity.duration_minutes,
                        duration_seconds=activity.duration_seconds
                    ))
        else:
            # Removing non-first activity: add its duration to the previous one
            for i, activity in enumerate(activities):
                if i == index:
                    continue  # Skip the removed activity
                elif i == index - 1:
                    # Previous activity gets the removed activity's duration
                    total_seconds = activity.total_duration_seconds + removed.total_duration_seconds
                    new_activities.append(ActivityLine(
                        description=activity.description,
                        start_time=activity.start_time,
                        duration_minutes=int(total_seconds // 60),
                        duration_seconds=int(total_seconds % 60)
                    ))
                elif i > index:
                    # Subsequent activities shift start times
                    prev_end = new_activities[-1].end_time
                    new_activities.append(ActivityLine(
                        description=activity.description,
                        start_time=prev_end,
                        duration_minutes=activity.duration_minutes,
                        duration_seconds=activity.duration_seconds
                    ))
                else:
                    # Activities before removed one remain the same
                    new_activities.append(ActivityLine(
                        description=activity.description,
                        start_time=activity.start_time,
                        duration_minutes=activity.duration_minutes,
                        duration_seconds=activity.duration_seconds
                    ))

        return new_activities


# ============================================================================
# UI Components
# ============================================================================

class ActivityLineWidget:
    """Widget for displaying and editing a single activity line.

    Shows description field, start time, duration in minutes, and remove button.
    Does not use a Frame - widgets are gridded directly into parent.
    """

    def __init__(self, parent, row: int, index: int, activity: ActivityLine,
                 is_first: bool, on_change_callback, on_remove_callback):
        """Initialize activity line widget.

        Args:
            parent: Parent frame to grid widgets into
            row: Grid row number for this activity
            index: Activity index in the list
            activity: ActivityLine data
            is_first: Whether this is the first activity (start time read-only)
            on_change_callback: Callback when any field changes
            on_remove_callback: Callback when remove button clicked
        """
        self.parent = parent
        self.row = row
        self.index = index
        self.is_first = is_first
        self.on_change = on_change_callback
        self.on_remove = on_remove_callback

        logger.debug(f"Creating widget for activity {index}: desc='{activity.description}', "
                    f"start={activity.start_time.strftime('%H:%M:%S')}, "
                    f"duration={activity.duration_minutes}m")

        # Description field (editable)
        self.desc_var = tk.StringVar(master=parent, value=activity.description)
        self.desc_var.trace_add("write", lambda *args: self._on_desc_change())
        self.desc_entry = ttk.Entry(parent, textvariable=self.desc_var, width=25)
        self.desc_entry.grid(row=row, column=0, padx=5, pady=2, sticky=tk.W+tk.E)

        # Start time field (read-only for first, editable for others)
        # Use locale-aware formatting with timezone conversion
        start_str = format_time_local(activity.start_time, include_seconds=is_first)
        self.start_var = tk.StringVar(master=parent, value=start_str)
        if not is_first:
            self.start_var.trace_add("write", lambda *args: self._on_start_change())
        self.start_entry = ttk.Entry(parent, textvariable=self.start_var, width=10,
                               state='readonly' if is_first else 'normal',
                               takefocus=0 if is_first else 1)
        self.start_entry.grid(row=row, column=1, padx=5, pady=2)

        # Duration field (minutes only, editable)
        self.duration_var = tk.IntVar(master=parent, value=activity.duration_minutes)
        self.duration_var.trace_add("write", lambda *args: self._on_duration_change())
        self.duration_spinbox = ttk.Spinbox(parent, from_=1, to=9999, width=6,
                                      textvariable=self.duration_var)
        self.duration_spinbox.grid(row=row, column=2, padx=5, pady=2)

        # Remove button
        self.remove_btn = ttk.Button(parent, text="−", width=3,
                               command=lambda: self.on_remove(index))
        self.remove_btn.grid(row=row, column=3, padx=5, pady=2)

    def _on_desc_change(self):
        """Handle description change."""
        desc = self.desc_var.get()
        logger.debug(f"Activity {self.index} description changed to: '{desc}'")
        # Notify parent about description change
        self.on_change(field='description', value=desc)

    def _on_start_change(self):
        """Handle start time change."""
        start = self.start_var.get()
        logger.debug(f"Activity {self.index} start time changed to: '{start}'")
        # Notify parent about start time change
        self.on_change(field='start_time', value=start)

    def _on_duration_change(self):
        """Handle duration change."""
        try:
            duration = self.duration_var.get()
            logger.debug(f"Activity {self.index} duration changed to: {duration}")
            # Notify parent about duration change
            self.on_change(field='duration', value=duration)
        except tk.TclError as e:
            logger.warning(f"Invalid duration value for activity {self.index}: {e}")

    def destroy(self):
        """Destroy all widgets in this line."""
        self.desc_entry.destroy()
        self.start_entry.destroy()
        self.duration_spinbox.destroy()
        self.remove_btn.destroy()

    def get_description(self) -> str:
        """Get the current description value."""
        return self.desc_var.get()

    def get_start_time_str(self) -> str:
        """Get the current start time string."""
        return self.start_var.get()

    def get_duration_minutes(self) -> int:
        """Get the current duration in minutes."""
        try:
            return self.duration_var.get()
        except tk.TclError:
            return 1  # Default to 1 if invalid

    def update_from_activity(self, activity: ActivityLine, is_first: bool):
        """Update widget values from an ActivityLine without triggering callbacks."""
        # Temporarily remove traces to avoid triggering callbacks
        desc_trace_id = self.desc_var.trace_info()[0][1] if self.desc_var.trace_info() else None
        duration_trace_id = self.duration_var.trace_info()[0][1] if self.duration_var.trace_info() else None
        start_trace_id = self.start_var.trace_info()[0][1] if self.start_var.trace_info() and not is_first else None

        if desc_trace_id:
            self.desc_var.trace_remove("write", desc_trace_id)
        if duration_trace_id:
            self.duration_var.trace_remove("write", duration_trace_id)
        if start_trace_id:
            self.start_var.trace_remove("write", start_trace_id)

        # Update values
        self.desc_var.set(activity.description)
        start_str = format_time_local(activity.start_time, include_seconds=is_first)
        self.start_var.set(start_str)
        self.duration_var.set(activity.duration_minutes)

        # Re-add traces
        self.desc_var.trace_add("write", lambda *args: self._on_desc_change())
        self.duration_var.trace_add("write", lambda *args: self._on_duration_change())
        if not is_first:
            self.start_var.trace_add("write", lambda *args: self._on_start_change())


class SplitActivityDialog(simpledialog.Dialog):
    """Dialog for splitting an AFK period into multiple activities.
    
    Allows users to:
    - Split a single AFK period into multiple sequential activities
    - Add/remove activity lines
    - Edit descriptions, start times, and durations
    - Automatic time consistency enforcement
    """
    
    def __init__(self, parent, title: str, prompt: str,
                 afk_start: datetime, afk_duration_seconds: float,
                 history: list[str]):
        """Initialize the split activity dialog.

        Args:
            parent: Parent tkinter widget
            title: Dialog window title
            prompt: Prompt text to display
            afk_start: Start time of the AFK period
            afk_duration_seconds: Duration of the AFK period in seconds
            history: List of previous descriptions for abbreviation expansion
        """
        self.prompt = prompt
        self.afk_start = afk_start
        self.afk_duration_seconds = afk_duration_seconds
        self.afk_end = afk_start + timedelta(seconds=afk_duration_seconds)
        self.history = history

        # Initialize with 2 equal activities
        self.activities = TimeCalculator.split_equal(
            afk_start, afk_duration_seconds, 2
        )
        self.equal_distribution_mode = True  # Track if user has edited durations

        self.activity_widgets = []
        self.result = None  # Will be set to list of ActivityLine on OK, None on Cancel
        self.return_to_single_mode = False  # Flag to indicate returning to single-entry mode
        self.single_mode_description = ""  # Description to use when returning to single mode

        super().__init__(parent, title)
    
    def body(self, master):
        """Create the dialog body with activity line widgets."""
        self.master_frame = ttk.Frame(master)
        self.master_frame.grid(sticky=tk.W+tk.E+tk.N+tk.S)

        # Prompt label
        prompt_label = ttk.Label(self.master_frame, text=self.prompt, justify=tk.LEFT)
        prompt_label.grid(row=0, column=0, columnspan=5, padx=5, pady=5, sticky=tk.W)

        # Header row
        ttk.Label(self.master_frame, text="Description", font=('TkDefaultFont', 9, 'bold')).grid(
            row=1, column=0, padx=5, pady=2, sticky=tk.W)
        ttk.Label(self.master_frame, text="Start", font=('TkDefaultFont', 9, 'bold')).grid(
            row=1, column=1, padx=5, pady=2, sticky=tk.W)
        ttk.Label(self.master_frame, text="Mins", font=('TkDefaultFont', 9, 'bold')).grid(
            row=1, column=2, padx=5, pady=2, sticky=tk.W)

        # Activities will be drawn starting at row 2
        self.first_activity_row = 2

        # Draw initial activity widgets
        self.redraw_activities()

        # Configure column resizing
        self.master_frame.columnconfigure(0, weight=1)

        # Focus on first description field
        if self.activity_widgets:
            return self.activity_widgets[0].desc_entry
        return None
    
    def redraw_activities(self):
        """Redraw all activity line widgets."""
        # Clear existing widgets
        for widget in self.activity_widgets:
            widget.destroy()
        self.activity_widgets = []

        # Destroy add button if it exists
        if hasattr(self, 'add_btn'):
            self.add_btn.destroy()

        # Create new widgets for each activity
        for i, activity in enumerate(self.activities):
            row = self.first_activity_row + i
            widget = ActivityLineWidget(
                parent=self.master_frame,
                row=row,
                index=i,
                activity=activity,
                is_first=(i == 0),
                on_change_callback=lambda field, value, idx=i: self.on_activity_changed(idx, field, value),
                on_remove_callback=self.remove_activity_line
            )
            self.activity_widgets.append(widget)

        # Add button below all activities
        add_row = self.first_activity_row + len(self.activities)
        self.add_btn = ttk.Button(self.master_frame, text="+", command=self.add_activity_line)
        self.add_btn.grid(row=add_row, column=0, padx=5, pady=5, sticky=tk.W)
    
    def on_activity_changed(self, changed_index: int, field: str, value):
        """Handle changes to any activity field.

        Args:
            changed_index: Index of the activity that was changed
            field: Which field was changed ('description', 'start_time', or 'duration')
            value: The new value
        """
        # Mark that user has made edits (disable equal distribution mode)
        self.equal_distribution_mode = False

        try:
            if field == 'description':
                # Just update the description in the activity
                activity = self.activities[changed_index]
                self.activities[changed_index] = ActivityLine(
                    description=value,
                    start_time=activity.start_time,
                    duration_minutes=activity.duration_minutes,
                    duration_seconds=activity.duration_seconds
                )
                logger.info(f"Activity {changed_index} description updated to: '{value}'")

            elif field == 'duration':
                # Use TimeCalculator to adjust the duration
                logger.info(f"Activity {changed_index} duration changed to {value} minutes")
                self.activities = TimeCalculator.adjust_duration(
                    self.activities,
                    index=changed_index,
                    new_duration_minutes=value,
                    original_end=self.afk_end
                )

                # Log all activity durations after recalculation
                for i, activity in enumerate(self.activities):
                    logger.info(
                        f"  Activity {i}: '{activity.description}' - "
                        f"{activity.start_time.strftime('%H:%M:%S')} - "
                        f"{activity.duration_minutes}m {activity.duration_seconds}s"
                    )

                # Update all widgets to reflect changes (without triggering callbacks)
                for i, (widget, activity) in enumerate(zip(self.activity_widgets, self.activities)):
                    widget.update_from_activity(activity, i == 0)

            elif field == 'start_time':
                # Parse start time string (HH:MM format) and adjust
                if changed_index == 0:
                    # First activity start time is not editable
                    logger.warning(f"Cannot edit start time of first activity")
                    return

                try:
                    # Parse HH:MM format
                    parts = value.split(':')
                    if len(parts) != 2:
                        logger.warning(f"Invalid start time format: {value}")
                        return

                    hours = int(parts[0])
                    minutes = int(parts[1])

                    if hours < 0 or hours > 23 or minutes < 0 or minutes > 59:
                        logger.warning(f"Invalid time values: {hours}:{minutes}")
                        return

                    # Create new datetime with same date but updated time
                    old_start = self.activities[changed_index].start_time
                    new_start = old_start.replace(hour=hours, minute=minutes, second=0, microsecond=0)

                    logger.info(f"Activity {changed_index} start time changed to {new_start.strftime('%H:%M')}")

                    # Use TimeCalculator to adjust the start time
                    self.activities = TimeCalculator.adjust_start_time(
                        self.activities,
                        index=changed_index,
                        new_start=new_start,
                        original_end=self.afk_end
                    )

                    # Log all activities after recalculation
                    for i, activity in enumerate(self.activities):
                        logger.info(
                            f"  Activity {i}: '{activity.description}' - "
                            f"{activity.start_time.strftime('%H:%M:%S')} - "
                            f"{activity.duration_minutes}m {activity.duration_seconds}s"
                        )

                    # Update all widgets to reflect changes
                    for i, (widget, activity) in enumerate(zip(self.activity_widgets, self.activities)):
                        widget.update_from_activity(activity, i == 0)

                except (ValueError, IndexError) as e:
                    logger.warning(f"Error parsing start time '{value}': {e}")

        except (ValueError, tk.TclError) as e:
            logger.warning(f"Error updating activity {changed_index}: {e}")
            pass
    
    def add_activity_line(self):
        """Add a new activity line."""
        try:
            self.activities = TimeCalculator.add_activity(
                self.activities,
                self.afk_end,
                equal_distribution=self.equal_distribution_mode,
                original_start=self.afk_start if self.equal_distribution_mode else None,
                original_duration_seconds=self.afk_duration_seconds if self.equal_distribution_mode else None
            )
            self.redraw_activities()
        except ValueError as e:
            # Show error message
            tk.messagebox.showerror("Cannot Add Activity", str(e))
    
    def remove_activity_line(self, index: int):
        """Remove an activity line."""
        self.activities = TimeCalculator.remove_activity(self.activities, index)

        # If only 1 activity left, return to single-entry mode (exit split mode)
        if len(self.activities) <= 1:
            logger.info("Only 1 activity remaining, returning to single-entry mode")
            self.return_to_single_mode = True
            if self.activities:
                self.single_mode_description = self.activities[0].description
            else:
                self.single_mode_description = ""
            # Close the dialog
            self.destroy()
            return

        self.redraw_activities()
    
    def buttonbox(self):
        """Create OK and Cancel buttons."""
        box = ttk.Frame(self)
        
        ok_btn = ttk.Button(box, text="OK", width=10, command=self.ok, default=tk.ACTIVE)
        ok_btn.pack(side=tk.LEFT, padx=5, pady=5)
        
        cancel_btn = ttk.Button(box, text="Cancel", width=10, command=self.cancel)
        cancel_btn.pack(side=tk.LEFT, padx=5, pady=5)
        
        self.bind("<Return>", self.ok)
        self.bind("<Escape>", self.cancel)
        
        # Keyboard shortcuts for add/remove
        self.bind("<Control-plus>", lambda e: self.add_activity_line())
        self.bind("<Control-equal>", lambda e: self.add_activity_line())  # + without shift
        
        box.pack()
    
    def validate(self) -> bool:
        """Validate the split activity data before accepting."""
        # Create SplitActivityData and validate
        data = SplitActivityData(
            original_start=self.afk_start,
            original_duration_seconds=self.afk_duration_seconds,
            activities=self.activities
        )

        errors = data.validate()
        if errors:
            # Log validation errors
            logger.error("Validation failed:")
            for err in errors:
                logger.error(f"  • {err}")

            error_msg = "Validation errors:\n\n" + "\n".join(f"• {err}" for err in errors)
            tk.messagebox.showerror("Invalid Split", error_msg)
            return False

        return True
    
    def apply(self):
        """Called when OK is clicked and validation passes."""
        self.result = self.activities


def ask_split_activities(title: str, prompt: str, afk_start: datetime,
                         afk_duration_seconds: float, history: list[str],
                         parent=None) -> Optional[list[ActivityLine]] | str:
    """Show split activity dialog and return list of activities, description, or None.

    Args:
        title: Dialog window title
        prompt: Prompt text to display
        afk_start: Start time of the AFK period
        afk_duration_seconds: Duration of the AFK period in seconds
        history: List of previous descriptions for abbreviation expansion
        parent: Parent tkinter widget (optional)

    Returns:
        - List of ActivityLine objects if OK clicked in split mode
        - String description if user removed activities down to 1 (return to single mode)
        - None if cancelled
    """
    if parent is None:
        # Create hidden root if needed
        import tkinter as tk
        root = tk.Tk()
        root.withdraw()
        parent = root

    dialog = SplitActivityDialog(parent, title, prompt, afk_start,
                                 afk_duration_seconds, history)

    # Check if user removed activities down to 1 (return to single mode)
    if dialog.return_to_single_mode:
        return dialog.single_mode_description

    return dialog.result
