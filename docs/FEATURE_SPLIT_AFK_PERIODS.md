# Feature Specification: Split AFK Periods

## Overview

Allow users to split a single AFK period into multiple activities with different descriptions and time allocations.

## Background

Currently, when a user returns from an extended AFK period during which they performed multiple activities, they can only enter a single description for the entire period. This feature enables users to split the AFK period into multiple segments, each with its own description and duration.

## User Stories

1. **As a user**, I want to split a 30-minute AFK period into "lunch" (20 min) and "phone call" (10 min), so that my time tracking accurately reflects what I did.

2. **As a user**, I want to easily add or remove activity segments without manually calculating time adjustments, so that I can quickly log my activities.

3. **As a user**, I want the time calculations to remain consistent, so that the total duration always matches my actual AFK period.

4. **As a developer**, I want to test the split dialog without waiting for an actual AFK period, so that I can verify functionality quickly.

## Functional Requirements

### FR1: Split Button

**Description**: Add a "Split" button to the main dialog that expands the interface to show multiple activity lines.

**Acceptance Criteria**:
- Button labeled "Split" appears in the main dialog (next to OK/Cancel/Settings)
- Clicking "Split" expands the dialog to show split mode
- In split mode, the single entry field is replaced with multiple activity lines
- Removing all extra lines (down to 1 line) automatically exits split mode and returns to normal single-entry mode

### FR2: Activity Lines

**Description**: Each activity line represents a time segment with description, start time, and duration.

**Acceptance Criteria**:
- Each line displays:
  - Activity description (text entry field)
  - Start time (HH:MM format, read-only for first line, editable for others)
  - Duration in minutes (numeric input, editable)
- First line's start time is fixed to the AFK period's start time (not editable)
- All other fields are editable
- Minimum 2 lines when in split mode
- Maximum 20 lines (reasonable limit)

### FR3: Add/Remove Lines

**Description**: Users can dynamically add or remove activity lines.

**Acceptance Criteria**:
- "+" button to add a new line (appears at the bottom)
- "−" button on each line to remove that line
- Removing the last extra line (down to 1 remaining line) exits split mode and returns to normal single-entry mode
- When adding a line with no prior edits, time is divided equally among all lines
- When adding a line after edits, new line gets minimum duration (1 minute), borrowed from last line
- Removing a line redistributes its duration to the previous line (or next line if removing first line)
- Add/remove operations maintain time consistency

### FR4: Equal Time Distribution (Default) & Time Precision

**Description**: When first entering split mode or adding lines without edits, time is distributed equally. Time precision is handled intelligently to balance accuracy with usability.

**Acceptance Criteria - Equal Distribution**:
- Initially splitting shows 2 lines with equal time distribution (±1 minute for odd durations)
- Adding a 3rd line redistributes time equally among 3 lines
- Equal distribution only applies when user hasn't manually edited any durations yet
- After first manual edit, equal distribution no longer applies to new lines

**Acceptance Criteria - Time Precision**:
- **Internal precision**: Keep second precision for all timestamps and durations internally
- **First activity start time**: Display with second precision (HH:MM:SS format), matches AFK period start exactly
- **Additional activity start times**: Round to nearest minute by default (HH:MM format), but allow user to edit seconds if desired
- **Duration fields**: Display and accept input in minutes only (integer values)
- **Rounding tolerance**: Up to ±30 seconds of rounding on first and last activities is acceptable and hidden from user
- **Total duration**: Internal calculations maintain second precision to match original AFK period duration exactly
- User can optionally click on start time fields to edit seconds if needed (progressive disclosure)

### FR5: Automatic Time Adjustment

**Description**: Editing any time field automatically adjusts related fields to maintain consistency.

**Acceptance Criteria**:
- Total duration always equals the original AFK period duration
- When editing a line's duration:
  - All subsequent lines' start times shift accordingly
  - If the duration increase would exceed available time, it's capped at maximum
  - The last line's duration adjusts to maintain total consistency
- When editing a line's start time (not first line):
  - Previous line's duration adjusts to reach the new start time
  - All subsequent lines shift their start times accordingly
- All changes update in real-time as user types
- Invalid states (negative durations, gaps, overlaps) are prevented

### FR6: Validation Rules

**Description**: Ensure data integrity and prevent invalid states. Note that the split feature is specifically for dividing a single AFK period into sequential non-overlapping activities. While overlapping activities are normal in ActivityWatch generally, the split feature models TimeWarrior-style sequential tracking where activities don't overlap.

**Acceptance Criteria**:
- No gaps between activities (end time of activity N = start time of activity N+1)
- No overlaps between activities (this is specific to the split feature's sequential model)
- All durations must be at least 1 minute
- Total duration must equal original AFK period duration (within 1 second tolerance for rounding)
- Start time of first activity = AFK period start time
- End time of last activity = AFK period end time
- Empty description fields trigger a warning but allow submission
- Only numeric input accepted for duration fields

### FR7: Data Submission & Error Handling

**Description**: Submit split activities as separate events to ActivityWatch with robust error handling.

**Acceptance Criteria**:
- Clicking "OK" in split mode posts N separate events (one per activity line)
- Each event has:
  - `timestamp`: The activity's start time
  - `duration`: The activity's duration in seconds
  - `data.message`: The activity description
- Events are posted to the same `aw-watcher-ask-away_{hostname}` bucket
- **Error handling** (fixes current bug where posting failures cause data loss):
  - Only mark events as "seen" (add to recent_events) AFTER successful posting
  - If posting fails, queue the events for retry
  - Display notification to user about queued events
  - Retry queued events on next iteration
  - Log posting failures for debugging
- Clicking "Cancel" discards all changes (same as current behavior)

### FR8: Testing Mode

**Description**: Enable testing without actual AFK periods.

**Acceptance Criteria**:
- New command-line flag: `--test-dialog`
- When `--test-dialog` is used:
  - Shows dialog immediately without waiting for AFK event
  - Uses test data: Start time = now - 30 minutes, Duration = 30 minutes
  - Optionally accepts parameters: `--test-dialog-duration MINUTES`
- When `--testing` flag is set (existing flag):
  - Posts to test server (localhost:5666) if running
  - Discards data silently if test server not running
  - Logs whether data was posted or discarded
- Regular `--testing` flag behavior preserved for existing tests

### FR9: UI/UX Requirements

**Description**: Maintain consistency with existing dialog design and usability.

**Acceptance Criteria**:
- Split mode dialog maintains the same styling as current dialog
- Dialog resizes appropriately when entering/exiting split mode
- Smooth transition animation preferred (but not required)
- Keyboard shortcuts:
  - `Tab`: Move to next field
  - `Shift+Tab`: Move to previous field
  - `Ctrl+Enter`: Submit (same as clicking OK)
  - `Escape`: Cancel (existing behavior)
  - `Ctrl+Plus` or `Ctrl+=`: Add line
  - `Ctrl+Minus`: Remove current line (if more than 2 remain)
- Clear visual indication of which fields are editable vs read-only
- Duration fields support both typing and scroll wheel (increment/decrement by 1 minute)

### FR10: Backward Compatibility

**Description**: Existing functionality must not be affected.

**Acceptance Criteria**:
- Users can continue using the dialog without split mode (default behavior)
- Single-line mode works exactly as before
- Command-line arguments remain compatible
- Existing tests continue to pass
- Configuration file format unchanged

## Non-Functional Requirements

### NFR1: Performance

- Dialog must remain responsive when handling up to 20 activity lines
- Time recalculations must appear instantaneous (<100ms)
- No memory leaks from adding/removing lines repeatedly

### NFR2: Code Quality

- Unit test coverage: >90% for split feature code
- Integration tests for end-to-end split workflow
- Type hints for all new functions (Python 3.11+ annotations)
- Documentation strings for all public methods
- Code follows existing project style (ruff + black formatting)

### NFR3: User Experience

- Clear error messages for validation failures
- Helpful tooltips on UI elements explaining behavior
- Consistent with existing dialog aesthetics
- No modal dialogs blocking user input (use inline validation)

### NFR4: Maintainability

- Split functionality isolated in dedicated module/class where feasible
- Minimal changes to existing core logic
- Clear separation between UI and business logic
- Comprehensive inline comments for complex time calculations

## Technical Design Notes

### Recommended Architecture

1. **New Module**: `src/aw_watcher_ask_away/split_dialog.py`
   - `SplitActivityDialog` class extending `AWAskAwayDialog`
   - `ActivityLine` dataclass representing a single activity
   - `TimeCalculator` utility class for consistency enforcement

2. **Modified Files**:
   - `__main__.py`: Add `--test-dialog` flag, handle split event posting
   - `core.py`: Add method to post multiple events atomically
   - `dialog.py`: Add split button to main dialog

3. **New Test File**: `tests/test_split.py`
   - Test time calculations
   - Test add/remove lines
   - Test validation rules
   - Test event posting
   - Test equal distribution logic

### Data Structures

```python
@dataclass
class ActivityLine:
    """Represents a single activity in a split AFK period."""
    description: str
    start_time: datetime
    duration_minutes: int

    @property
    def end_time(self) -> datetime:
        return self.start_time + timedelta(minutes=self.duration_minutes)

@dataclass
class SplitActivityData:
    """Container for all activity lines in a split period."""
    original_start: datetime
    original_duration_seconds: float
    activities: list[ActivityLine]

    def validate(self) -> list[str]:
        """Return list of validation errors, empty if valid."""
        ...

    def is_valid(self) -> bool:
        """Check if all activities form a valid, consistent timeline."""
        ...
```

### Time Calculation Algorithm

When user edits duration of line N:
1. Calculate delta: `new_duration - old_duration`
2. If delta > 0 (increasing):
   - Check if remaining time available in last line >= delta
   - If yes: subtract delta from last line's duration
   - If no: cap the new duration at maximum available
3. If delta < 0 (decreasing):
   - Add abs(delta) to last line's duration
4. Recalculate start times for lines N+1 through end

When user edits start time of line N (N > 1):
1. Calculate delta: `new_start - old_start`
2. Adjust line N-1's duration by delta
3. Validate that line N-1's duration >= 1 minute
4. Recalculate start times for lines N+1 through end

## Testing Strategy

### Unit Tests
- `test_activity_line_dataclass()`: Test dataclass properties
- `test_time_calculator_increase_duration()`: Test duration increase logic
- `test_time_calculator_decrease_duration()`: Test duration decrease logic
- `test_time_calculator_change_start_time()`: Test start time adjustment
- `test_equal_distribution()`: Test initial equal time split
- `test_add_line_no_edits()`: Test adding line with equal distribution
- `test_add_line_after_edits()`: Test adding line after manual edits
- `test_remove_line()`: Test removing a line
- `test_validation_no_gaps()`: Test gap detection
- `test_validation_no_overlaps()`: Test overlap detection
- `test_validation_min_duration()`: Test minimum duration enforcement
- `test_validation_total_duration()`: Test total duration consistency

### Integration Tests
- `test_split_dialog_creates_multiple_events()`: Test end-to-end workflow
- `test_split_dialog_cancel_no_events()`: Test cancel behavior
- `test_split_with_testing_flag()`: Test with --testing mode

### Manual Testing Checklist
- [ ] Test with very short AFK period (2 minutes)
- [ ] Test with very long AFK period (2 hours)
- [ ] Test with odd-duration periods (e.g., 37 minutes 35 seconds)
- [ ] Test rapid add/remove operations
- [ ] Test all keyboard shortcuts
- [ ] Test tab order through fields
- [ ] Test with empty descriptions
- [ ] Test `--test-dialog` flag with various durations
- [ ] Test on different platforms (Linux primary, optional: Windows/macOS)
- [ ] Test with actual ActivityWatch server running
- [ ] Test with `--testing` flag and test server

## Implementation Phases

### Phase 1: Core Data Structures & Logic
- Create `ActivityLine` and `SplitActivityData` dataclasses
- Implement `TimeCalculator` class
- Write unit tests for time calculations
- **Deliverable**: Fully tested time calculation logic

### Phase 2: UI Components
- Create `SplitActivityDialog` class
- Implement activity line widgets
- Add split button to main dialog
- Implement add/remove line buttons
- **Deliverable**: Functional UI (without event posting)

### Phase 3: Integration
- Add `--test-dialog` CLI flag
- Implement multi-event posting in `core.py`
- Connect split dialog to event posting
- Update main loop to handle split mode
- **Deliverable**: End-to-end working feature

### Phase 4: Testing & Polish
- Write integration tests
- Add tooltips and help text
- Implement keyboard shortcuts
- Performance testing with 20 lines
- Manual QA testing
- **Deliverable**: Production-ready feature

## Design Decisions (Resolved)

1. **Q**: Should we persist the "split" state if user clicks Split, then Cancel, then gets prompted again for the same event?
   **A**: No. Clicking Cancel discards all data and the user will be prompted again (current behavior). The cancel functionality needs more thought in general, so minimum effort should be spent on this for now.

2. **Q**: Should there be a "Split" option directly on the first dialog, or only appear after clicking a button?
   **A**: Yes, the "Split" button should be directly visible on the first dialog (not hidden in a menu).

3. **Q**: If posting events fails partway through (e.g., 2 of 5 events posted), what's the recovery strategy?
   **A**: Queue failed postings for retry and inform the user that some events haven't been posted yet. This addresses a current bug where posting failures cause data loss.

4. **Q**: Should abbreviation expansion work in split mode?
   **A**: Yes, for consistency with the main dialog (though some users may handle this in aw-export-timewarrior instead).

5. **Q**: Should we store split configuration (number of lines, time distribution) for future use?
   **A**: Out of scope for v1. May be a future improvement.

## Success Criteria

The feature is considered complete when:
- [ ] All functional requirements implemented
- [ ] All unit tests pass with >90% coverage
- [ ] Integration tests pass
- [ ] Manual testing checklist completed
- [ ] Documentation updated (README.md)
- [ ] User acceptance testing passed
- [ ] GitHub issue closed
- [ ] Pull request merged

## References

- Project Repository: https://github.com/Jeremiah-England/aw-watcher-ask-away
- ActivityWatch API Docs: https://docs.activitywatch.net/
- Related Issue: [TBD - will be created]
