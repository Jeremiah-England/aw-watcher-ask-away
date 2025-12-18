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
    LOCAL_TIMEZONE,
    WATCHER_NAME,
    AWAskAwayClient,
    AWWatcherAskAwayError,
    logger,
)


def prompt(event: aw_core.Event, recent_events: Iterable[aw_core.Event]):
    # TODO: Allow for customizing the prompt from the prompt interface.
    start_time_str = event.timestamp.astimezone(LOCAL_TIMEZONE).strftime("%I:%M")
    end_time_str = (event.timestamp + event.duration).astimezone(LOCAL_TIMEZONE).strftime("%I:%M")
    prompt = f"What were you doing from {start_time_str} - {end_time_str} ({event.duration.seconds / 60:.1f} minutes)?"
    title = "AFK Checkin"

    return aw_dialog.ask_string(title, prompt, [event.data.get(DATA_KEY, '') for event in recent_events])


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
    args = parser.parse_args()

    # Set up logging
    setup_logging(
        WATCHER_NAME,
        testing=args.testing,
        verbose=args.verbose,
        log_stderr=True,
        log_file=True,
    )

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
                    if response := prompt(event, state.state.recent_events):
                        logger.info(response)
                        state.post_event(event, response)
                time.sleep(args.frequency)
    except Exception as e:
        messagebox.showerror("AW Watcher Ask Away: Error", f"An unhandled exception occurred: {e}")
        raise


if __name__ == "__main__":
    main()
