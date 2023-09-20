# ruff: noqa: EM101, EM102
import argparse
import datetime
import logging
import time
from dataclasses import dataclass
from functools import cache
from itertools import pairwise
from tkinter import simpledialog

import aw_core
import aw_transform
from aw_client.client import ActivityWatchClient
from aw_transform.filter_period_intersect import period_union

system_timezone = datetime.datetime.now().astimezone().tzinfo

class AWWatcherAskAwayError(Exception):
    pass


logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


@cache
def get_buckets(client: ActivityWatchClient):
    return client.get_buckets()


@cache
def get_afk_bucket(client: ActivityWatchClient):
    match [bucket for bucket in get_buckets(client) if "afk" in bucket]:
        case []:
            raise AWWatcherAskAwayError("Cannot find the afk bucket.")
        case [bucket]:
            return bucket
        case buckets:
            raise AWWatcherAskAwayError(f"Found too many afk buckets: {buckets}.")

@dataclass
class Note:
    user_message: str
    event: aw_core.Event


class AWAskAwayState:
    def __init__(self, client: ActivityWatchClient):
        self.client = client
        self.bucket_name = f"aw-watcher-ask-away_{self.client.client_hostname}"
        if self.bucket_name not in get_buckets(self.client):
            client.create_bucket(self.bucket_name, event_type="afktask")

        self.recent_events = {(event.timestamp, event.duration): event for event in client.get_events(self.bucket_name, limit=10)}
        """The recent events we have posted to the aw-watcher-ask-away bucket.

        This is used to avoid asking the user to log an absence that they have already logged."""

    def has_event(self, event: aw_core.Event):
        return (event.timestamp, event.duration) in self.recent_events

    def post_event(self, event: aw_core.Event, message: str):
        assert not self.has_event(event)
        event.data["message"] = message
        event["id"] = None  # Wipe the ID so we don't edit the AFK event.
        self.recent_events[(event.timestamp, event.duration)] = event
        self.client.insert_event(self.bucket_name, event)


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


def get_afk_events_to_note(seconds: float, durration_thresh: float, client: ActivityWatchClient):
    """Check whether we recently finished a large AFK event."""
    events = client.get_events(get_afk_bucket(client), limit=10)
    if is_afk(events[0]):  # Currently AFK, wait to bring up the prompt.
        return

    # Use gaps in non-afk events instead of the afk-events themselves to handle when the computer
    # is suspended or powered off.
    non_afk_events = squash_overlaps([e for e in events if not is_afk(e)])
    pseudo_afk_events = list(get_gaps(non_afk_events))

    # Remove overlaps between AFK events. This is needed after testing the app without it.
    # afk_events = aw_transform.period_union([event for event in events if is_afk(event)], [])
    # Merge close events. This sounds like a good idea but I haven't tested to see if it is really needed.
    pseudo_afk_events = aw_transform.heartbeat_reduce(pseudo_afk_events, pulsetime=10)
    buffered_now = get_utc_now() - datetime.timedelta(seconds=seconds)
    for event in pseudo_afk_events:
        long_enough = event.duration.seconds > durration_thresh
        recent_enough = event.timestamp + event.duration > buffered_now
        if long_enough and recent_enough:
            yield event

def prompt(event: aw_core.Event):
    start_time_str = event.timestamp.astimezone(system_timezone).strftime("%I:%M")
    end_time_str = (event.timestamp + event.duration).astimezone(system_timezone).strftime("%I:%M")
    prompt = f"What were you doing from {start_time_str} - {end_time_str} ({event.duration.seconds / 60:f0.1} minutes)?"
    title = "AFK Checkin"

    return simpledialog.askstring(title, prompt)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--depth", type=float, default=5, help="The number of minutes to look into the past for events.")
    parser.add_argument("--frequency", type=float, default=3, help="The number of seconds to wait before checking for AFK events again.")
    parser.add_argument("--length", type=float, default=3, help="The number of minutes you need to be away before reporting on it.")
    parser.add_argument("--testing", action="store_true", help="Run in testing mode.")
    args = parser.parse_args()

    client = ActivityWatchClient(testing=args.testing)  # pyright: ignore[reportPrivateImportUsage]
    state = AWAskAwayState(client)

    while True:
        for event in get_afk_events_to_note(seconds=args.depth * 60, durration_thresh=args.length * 60, client=client):
            if not state.has_event(event):
                if response := prompt(event):
                    logger.info(response)
                    state.post_event(event, response)
        time.sleep(args.frequency)

if __name__ == "__main__":
    main()

# TODOS:
#   - Get the recent history and summarize it in the dialogue.
#     The point is to jog someone's memory of what they were doing last time they were on their computer.
#     This will help them place when their "time away" started and we will get a more accurate summary of what they did.
#   - Handle more than just AFK (e.g. suspending the computer).
