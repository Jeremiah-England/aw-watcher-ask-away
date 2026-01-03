# ruff: noqa: EM101, EM102
import argparse
import time
from collections.abc import Iterable
from tkinter import messagebox

import aw_core
from aw_client.client import ActivityWatchClient
from aw_core.log import setup_logging
from requests.exceptions import ConnectionError

import aw_watcher_ask_away.dialog as aw_dialog
from aw_watcher_ask_away.config import load_config
from aw_watcher_ask_away.core import (
    DATA_KEY,
    WATCHER_NAME,
    AWAskAwayClient,
    AWWatcherAskAwayError,
    logger,
)
from aw_watcher_ask_away.utils import format_time_local


def prompt(event: aw_core.Event, recent_events: Iterable[aw_core.Event]):
    # TODO: Allow for customizing the prompt from the prompt interface.
    start_time_str = format_time_local(event.timestamp)
    end_time_str = format_time_local(event.timestamp + event.duration)
    prompt_text = f"What were you doing from {start_time_str} - {end_time_str} ({event.duration.seconds / 60:.1f} minutes)?"
    title = "AFK Checkin"

    # Pass afk_start and afk_duration_seconds to enable Split button
    return aw_dialog.ask_string(
        title,
        prompt_text,
        [event.data.get(DATA_KEY, '') for event in recent_events],
        afk_start=event.timestamp,
        afk_duration_seconds=event.duration.total_seconds()
    )


def get_state_retries(client: ActivityWatchClient, enable_lid_events: bool = True):
    """When the computer is starting up sometimes the aw-server is not ready for requests yet.

    So we sit and retry for a while before giving up.
    """
    for _ in range(10):
        try:
            # This works because the constructor of AWAskAwayState tries to get bucket names.
            # If it didn't we'd need to do something else here.
            return AWAskAwayClient(client, enable_lid_events=enable_lid_events)
        except ConnectionError:
            logger.exception("Cannot connect to client.")
            time.sleep(10)  # 10 * 10 = wait for 100s before giving up.
    raise AWWatcherAskAwayError("Could not get a connection to the server.")


def main():
    # Load config from file (falls back to defaults if file doesn't exist)
    config = load_config()

    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--depth",
        type=float,
        default=config.get("depth", 10),
        help="The number of minutes to look into the past for events. (default: from config or 10)",
    )
    parser.add_argument(
        "--frequency",
        type=float,
        default=config.get("frequency", 5),
        help="The number of seconds to wait before checking for AFK events again. (default: from config or 5)",
    )
    parser.add_argument(
        "--length",
        type=float,
        default=config.get("length", 5),
        help="The number of minutes you need to be away before reporting on it. (default: from config or 5)",
    )
    parser.add_argument("--testing", action="store_true", help="Run in testing mode.")
    parser.add_argument("--verbose", action="store_true", help="I want to see EVERYTHING!")
    parser.add_argument(
        "--test-dialog",
        action="store_true",
        help="Show test dialog immediately (for UI testing without AFK period).",
    )
    parser.add_argument(
        "--test-dialog-duration",
        type=float,
        default=30,
        help="Duration in minutes for test dialog (default: 30).",
    )
    args = parser.parse_args()

    # Set up logging
    setup_logging(
        WATCHER_NAME,
        testing=args.testing,
        verbose=args.verbose,
        log_stderr=True,
        log_file=True,
    )

    # Test dialog mode - show dialog immediately for UI testing
    if args.test_dialog:
        from datetime import datetime, timedelta, UTC
        import aw_watcher_ask_away.dialog as aw_dialog

        # Create test AFK event data
        test_start = datetime.now(UTC) - timedelta(minutes=args.test_dialog_duration)
        test_duration_seconds = args.test_dialog_duration * 60

        start_time_str = format_time_local(test_start)
        end_time_str = format_time_local(test_start + timedelta(seconds=test_duration_seconds))
        test_prompt = f"What were you doing from {start_time_str} - {end_time_str} ({args.test_dialog_duration:.1f} minutes)?"
        title = "AFK Checkin (TEST MODE)"

        # Show dialog with split mode support
        result = aw_dialog.ask_string(
            title, test_prompt, history=["test1", "test2", "lunch", "meeting"],
            afk_start=test_start, afk_duration_seconds=test_duration_seconds
        )

        logger.info("Test dialog closed, processing result...")

        if result is None:
            logger.info("Test dialog cancelled")
        elif isinstance(result, tuple) and result[0] == "SPLIT_MODE":
            activities = result[1]
            logger.info(f"Test dialog returned {len(activities)} activities:")
            for i, activity in enumerate(activities, 1):
                logger.info(
                    f"  {i}. '{activity.description}' - "
                    f"{activity.start_time.strftime('%H:%M:%S')} - "
                    f"{activity.duration_minutes}m {activity.duration_seconds}s"
                )
        else:
            logger.info(f"Test dialog result: '{result}'")

        logger.info("Exiting test dialog mode")
        # Exit after showing test dialog
        return

    try:
        client = ActivityWatchClient(  # pyright: ignore[reportPrivateImportUsage]
            client_name=WATCHER_NAME, testing=args.testing
        )
        with client:
            state = get_state_retries(client, enable_lid_events=config.get("enable_lid_events", True))
            logger.info("Successfully connected to the server.")

            while True:
                for event in state.get_new_afk_events_to_note(
                    seconds=args.depth * 60, durration_thresh=args.length * 60
                ):
                    response = prompt(event, state.state.recent_events)
                    if response is None:
                        # User cancelled
                        continue
                    elif isinstance(response, tuple) and response[0] == "SPLIT_MODE":
                        # User used split mode
                        activities = response[1]
                        logger.info(f"Posting {len(activities)} split activities")
                        state.post_split_events(event, activities)
                    else:
                        # Normal single-entry mode
                        logger.info(response)
                        state.post_event(event, response)
                time.sleep(args.frequency)
    except Exception as e:
        messagebox.showerror("AW Watcher Ask Away: Error", f"An unhandled exception occurred: {e}")
        raise


if __name__ == "__main__":
    main()
