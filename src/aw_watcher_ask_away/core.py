# ruff: noqa: EM101, EM102
import datetime
import logging
from collections import deque
from functools import cached_property
from itertools import pairwise
from typing import Any

import aw_core
import aw_transform
from aw_client.client import ActivityWatchClient
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


# TODO: This class needs to be unit testable.
# There are a lot of edge casesto handle.
# Also need to update the debug logs so it is trivial to create unit tests from issues that happen.
class AWAskAwayState:
    def __init__(self, client: ActivityWatchClient):
        self.client = client
        self.bucket_id = f"{WATCHER_NAME}_{self.client.client_hostname}"

        if self.bucket_id not in self._all_buckets:
            # TODO: Look into why aw-watcher-afk uses queued=True here.
            client.create_bucket(self.bucket_id, event_type="afktask")

        self.recent_events: deque[aw_core.Event] = deque(maxlen=10)
        self.recent_events.extend(aw_transform.sort_by_timestamp(client.get_events(self.bucket_id, limit=10)))
        """The recent events we have posted to the aw-watcher-ask-away bucket.

        This is used to avoid asking the user to log an absence that they have already logged."""

        self.afk_bucket_id = find_afk_bucket(self._all_buckets)

    @cached_property
    def _all_buckets(self):
        return self.client.get_buckets()

    def has_event(self, new: aw_core.Event, overlap_thresh: float = 0.95) -> bool:
        """Check whether we have already posted an event that overlaps with the new event.

        The self.recent_events data structure used to be a dictionary with keys as timestamp/durration.
        This method merely checked to see if the new event's (timestamp, durration) tuple was in the dictionary.

        However, for some reason the events coming from the aw-server seem to be slightly inconsistent at times.
        For example, look at the logs below:

            2023-09-23 19:33:45 [DEBUG]: Got events from the server: [('2023-09-23T23:33:37.730000+00:00', 'not-afk'), ...]
            2023-09-23 19:33:58 [DEBUG]: Got events from the server: [('2023-09-23T23:33:37.730000+00:00', 'not-afk'), ('2023-09-23T23:33:37.729000+00:00', 'not-afk'), ...]

        The second query returns an overlapping 'not-afk' event with a slightly earlier timestamp.
        This duplication + offset combination was causing us to double ask the user for input.
        Using overlaps with a percentage is more robust against this kind of thing.
        """  # noqa: E501
        for recent in self.recent_events:
            overlap_start = max(recent.timestamp, new.timestamp)
            overlap_end = min(recent.timestamp + recent.duration, new.timestamp + new.duration)
            overlap = overlap_end - overlap_start
            if overlap / new.duration > overlap_thresh:
                return True
        return False

    def post_event(self, event: aw_core.Event, message: str):
        assert not self.has_event(event)  # noqa: S101
        event.data["message"] = message
        event["id"] = None  # Wipe the ID so we don't edit the AFK event.
        logger.debug(f"Posting event: {event}")
        self.recent_events.append(event)
        self.client.insert_event(self.bucket_id, event)


    # TODO: Handle this case which caused me to need to say what I did twice.
    # 2023-09-24 09:00:19 [DEBUG]: Got events from the server: [                                                                                              ('2023-09-24T09:00:06.384000-04:00', 'not-afk'),                                                                                           ('2023-09-24T08:53:32.497000-04:00', 'afk'), ('2023-09-24T08:53:32.497000-04:00', 'afk'), ('2023-09-24T08:53:07.001000-04:00', 'not-afk'), ('2023-09-24T08:53:07.001000-04:00', 'not-afk'), ('2023-09-24T08:47:08.600000-04:00', 'afk'), ('2023-09-24T08:47:08.600000-04:00', 'afk'), ('2023-09-24T08:43:36.555000-04:00', 'not-afk'), ('2023-09-24T07:31:55.840000-04:00', 'afk'), ('2023-09-24T07:31:55.840000-04:00', 'afk')]  (aw_watcher_ask_away.core:113)  # noqa: E501
    # 2023-09-24 09:04:59 [DEBUG]: Got events from the server: [('2023-09-24T09:04:53.758000-04:00', 'not-afk'), ('2023-09-24T09:00:06.383000-04:00', 'afk'), ('2023-09-24T09:00:06.383000-04:00', 'not-afk'), ('2023-09-24T09:00:06.383000-04:00', 'afk'), ('2023-09-24T09:00:06.383000-04:00', 'afk'), ('2023-09-24T08:53:32.497000-04:00', 'afk'), ('2023-09-24T08:53:32.497000-04:00', 'afk'), ('2023-09-24T08:53:07.001000-04:00', 'not-afk'), ('2023-09-24T08:53:07.001000-04:00', 'not-afk'), ('2023-09-24T08:47:08.600000-04:00', 'afk')]  (aw_watcher_ask_away.core:113)  # noqa: E501
    # Removing heartbeat_reduce seems like it would fix the issue but is that the right behavior?
    def get_afk_events_to_note(self, seconds: float, durration_thresh: float):
        """Check whether we recently finished a large AFK event."""
        try:
            events = self.client.get_events(self.afk_bucket_id, limit=10)
            events_log = [
                (e.timestamp.astimezone(LOCAL_TIMEZONE).isoformat(), e.duration.seconds, e.data["status"])
                for e in events
            ]
            logger.debug(f"Got events from the server: {events_log}")
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
        logger.debug(f"Events before heartbeat_reduce: {len(pseudo_afk_events)}")
        pseudo_afk_events = aw_transform.heartbeat_reduce(pseudo_afk_events, pulsetime=10)
        logger.debug(f"Events after heartbeat_reduce: {len(pseudo_afk_events)}")
        pseudo_afk_events = [e for e in pseudo_afk_events if not self.has_event(e)]
        buffered_now = get_utc_now() - datetime.timedelta(seconds=seconds)
        for event in pseudo_afk_events:
            long_enough = event.duration.seconds > durration_thresh
            recent_enough = event.timestamp + event.duration > buffered_now
            if long_enough and recent_enough:
                logger.debug(f"Found event to note: {event}")
                yield event
