# ruff: noqa: EM101, EM102
import argparse
import datetime
import logging
import time
from functools import cached_property
from itertools import pairwise
from tkinter import simpledialog
from typing import Any

import aw_core
import aw_transform
from aw_client.client import ActivityWatchClient
from aw_core.log import setup_logging
from requests.exceptions import HTTPError

WATCHER_NAME = "aw-watcher-ask-away"
LOCAL_TIMEZONE = datetime.datetime.now().astimezone().tzinfo

class AWWatcherAskAwayError(Exception):
    pass

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def find_afk_bucket(buckets: dict[str, Any]):
    match [bucket for bucket in buckets if "afk" in bucket]:
        case []:
            raise AWWatcherAskAwayError("Cannot find the afk bucket.")
        case [bucket]:
            return bucket
        case _:
            raise AWWatcherAskAwayError(f"Found too many afk buckets: {buckets}.")


def is_afk(event: aw_core.Event) -> bool:
    return event.data["status"] == "afk"


def squash_overlaps(events: list[aw_core.Event]) -> list[aw_core.Event]:
    return aw_transform.sort_by_timestamp(aw_transform.period_union(events, []))


def get_utc_now():
    return datetime.datetime.now().astimezone(datetime.UTC)


def get_gaps(events: list[aw_core.Event]):
    flattened_events = aw_transform.sort_by_timestamp(squash_overlaps(events))
    for first, second in pairwise(flattened_events):
        first_end = first.timestamp + first.duration
        if first_end < second.timestamp:
            yield aw_core.Event(None, first_end, second.timestamp - first_end)


class AWAskAwayState:
    def __init__(self, client: ActivityWatchClient):
        self.client = client
        self.bucket_id = f"{WATCHER_NAME}_{self.client.client_hostname}"

        if self.bucket_id not in self._all_buckets:
            # TODO: Look into why aw-watcher-afk uses queued=True here.
            client.create_bucket(self.bucket_id, event_type="afktask")

        self.recent_events = {(event.timestamp, event.duration): event for event in client.get_events(self.bucket_id, limit=10)}
        """The recent events we have posted to the aw-watcher-ask-away bucket.

        This is used to avoid asking the user to log an absence that they have already logged."""

        self.afk_bucket_id = find_afk_bucket(self._all_buckets)


    @cached_property
    def _all_buckets(self):
        return self.client.get_buckets()

    def has_event(self, event: aw_core.Event):
        return (event.timestamp, event.duration) in self.recent_events

    def post_event(self, event: aw_core.Event, message: str):
        assert not self.has_event(event)
        event.data["message"] = message
        event["id"] = None  # Wipe the ID so we don't edit the AFK event.
        self.recent_events[(event.timestamp, event.duration)] = event
        self.client.insert_event(self.bucket_id, event)


    def get_afk_events_to_note(self, seconds: float, durration_thresh: float):
        """Check whether we recently finished a large AFK event."""
        try:
            events = self.client.get_events(self.afk_bucket_id, limit=10)
        except HTTPError:
            logger.exception("Failed to get events from the server.")
            return

        if is_afk(events[0]):  # Currently AFK, wait to bring up the prompt.
            return

        # Use gaps in non-afk events instead of the afk-events themselves to handle when the computer
        # is suspended or powered off.
        non_afk_events = squash_overlaps([e for e in events if not is_afk(e)])
        pseudo_afk_events = list(get_gaps(non_afk_events))

        # Merge close events. This sounds like a good idea but I haven't tested to see if it is really needed.
        pseudo_afk_events = aw_transform.heartbeat_reduce(pseudo_afk_events, pulsetime=10)
        pseudo_afk_events = [e for e in pseudo_afk_events if not self.has_event(e)]
        buffered_now = get_utc_now() - datetime.timedelta(seconds=seconds)
        for event in pseudo_afk_events:
            long_enough = event.duration.seconds > durration_thresh
            recent_enough = event.timestamp + event.duration > buffered_now
            if long_enough and recent_enough:
                yield event

def prompt(event: aw_core.Event):
    # TODO: Allow for customizing the prompt from the prompt interface.
    # TODO: Figure how why standard text editing keyboard shortcuts do not work. Maybe use something besides tkinter.
    start_time_str = event.timestamp.astimezone(LOCAL_TIMEZONE).strftime("%I:%M")
    end_time_str = (event.timestamp + event.duration).astimezone(LOCAL_TIMEZONE).strftime("%I:%M")
    prompt = f"What were you doing from {start_time_str} - {end_time_str} ({event.duration.seconds / 60:.1f} minutes)?"
    title = "AFK Checkin"

    return simpledialog.askstring(title, prompt)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--depth", type=float, default=5, help="The number of minutes to look into the past for events.")
    parser.add_argument("--frequency", type=float, default=3, help="The number of seconds to wait before checking for AFK events again.")
    parser.add_argument("--length", type=float, default=3, help="The number of minutes you need to be away before reporting on it.")
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
        state = AWAskAwayState(client)

        while True:
            for event in state.get_afk_events_to_note(seconds=args.depth * 60, durration_thresh=args.length * 60):
                if response := prompt(event):
                    logger.info(response)
                    state.post_event(event, response)
            time.sleep(args.frequency)

if __name__ == "__main__":
    main()
