# ruff: noqa: EM101, EM102
import argparse
import datetime
import time
from tkinter import simpledialog

import aw_core
from aw_client.client import ActivityWatchClient
from aw_core.log import setup_logging
from requests.exceptions import ConnectionError

from aw_watcher_ask_away.core import WATCHER_NAME, AWAskAwayState, AWWatcherAskAwayError, logger

LOCAL_TIMEZONE = datetime.datetime.now().astimezone().tzinfo


def prompt(event: aw_core.Event):
    # TODO: Allow for customizing the prompt from the prompt interface.
    # TODO: Figure how why standard text editing keyboard shortcuts do not work. Maybe use something besides tkinter.
    start_time_str = event.timestamp.astimezone(LOCAL_TIMEZONE).strftime("%I:%M")
    end_time_str = (event.timestamp + event.duration).astimezone(LOCAL_TIMEZONE).strftime("%I:%M")
    prompt = f"What were you doing from {start_time_str} - {end_time_str} ({event.duration.seconds / 60:.1f} minutes)?"
    title = "AFK Checkin"

    return simpledialog.askstring(title, prompt)


def get_state_retries(client: ActivityWatchClient):
    """When the computer is starting up sometimes the aw-server is not ready for requests yet.

    So we sit and retry for a while before giving up.
    """
    for _ in range(10):
        try:
            # This works because the constructor of AWAskAwayState tries to get bucket names.
            # If it didn't we'd need to do something else here.
            return AWAskAwayState(client)
        except ConnectionError:
            logger.exception("Cannot connect to client.")
            time.sleep(10)  # 10 * 10 = wait for 100s before giving up.
    raise AWWatcherAskAwayError("Could not get a connection to the server.")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--depth", type=float, default=5, help="The number of minutes to look into the past for events."
    )
    parser.add_argument(
        "--frequency", type=float, default=3, help="The number of seconds to wait before checking for AFK events again."
    )
    parser.add_argument(
        "--length", type=float, default=3, help="The number of minutes you need to be away before reporting on it."
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

    client = ActivityWatchClient(  # pyright: ignore[reportPrivateImportUsage]
        client_name=WATCHER_NAME, testing=args.testing
    )
    with client:
        state = get_state_retries(client)
        logger.info("Successfully connected to the server.")

        while True:
            for event in state.get_afk_events_to_note(seconds=args.depth * 60, durration_thresh=args.length * 60):
                if response := prompt(event):
                    logger.info(response)
                    state.post_event(event, response)
            time.sleep(args.frequency)


if __name__ == "__main__":
    main()
