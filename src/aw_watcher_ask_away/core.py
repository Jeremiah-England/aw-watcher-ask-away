# ruff: noqa: EM101, EM102
import datetime
import logging
from collections import deque
from collections.abc import Iterable
from copy import deepcopy
from functools import cached_property
from itertools import pairwise
from typing import Any

import aw_core
import aw_transform
from aw_client.client import ActivityWatchClient
from requests.exceptions import HTTPError

WATCHER_NAME = "aw-watcher-ask-away"
LOCAL_TIMEZONE = datetime.datetime.now().astimezone().tzinfo
DATA_KEY = "message"
"""What field in the event data to store the user's message in."""


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
    # Make a deep copy because the period_union function edits the events instead of returning new ones.
    return aw_transform.sort_by_timestamp(aw_transform.period_union(deepcopy(events), []))


def get_utc_now():
    return datetime.datetime.now().astimezone(datetime.UTC)


def get_gaps(events: list[aw_core.Event]):
    flattened_events = aw_transform.sort_by_timestamp(squash_overlaps(events))
    for first, second in pairwise(flattened_events):
        first_end = first.timestamp + first.duration
        if first_end < second.timestamp:
            yield aw_core.Event(None, first_end, second.timestamp - first_end)


class AWAskAwayClient:
    def __init__(self, client: ActivityWatchClient):
        self.client = client
        self.bucket_id = f"{WATCHER_NAME}_{self.client.client_hostname}"

        if self.bucket_id not in self._all_buckets:
            # TODO: Look into why aw-watcher-afk uses queued=True here.
            client.create_bucket(self.bucket_id, event_type="afktask")

        recent_events = deque(maxlen=10)
        recent_events.extend(aw_transform.sort_by_timestamp(client.get_events(self.bucket_id, limit=10)))
        self.state = AWAskAwayState(recent_events)

        self.afk_bucket_id = find_afk_bucket(self._all_buckets)

    @cached_property
    def _all_buckets(self):
        return self.client.get_buckets()

    def post_event(self, event: aw_core.Event, message: str):
        self.state.add_event(event, message)
        self.client.insert_event(self.bucket_id, event)

    def get_new_afk_events_to_note(self, seconds: float, durration_thresh: float):
        """Check whether we recently finished a large AFK event.

        Parameters
        ----------
        seconds : float
            The number of seconds to look into the past for events.
        durration_thresh : float
            The number of seconds you need to be away before reporting on it.
        """
        try:
            events = self.client.get_events(self.afk_bucket_id, limit=10)
            if is_afk(events[0]):  # Currently AFK, wait to bring up the prompt.
                return
            yield from self.state.get_unseen_afk_events(events, seconds, durration_thresh)
        except HTTPError:
            logger.exception("Failed to get events from the server.")
            return


class AWAskAwayState:
    def __init__(self, recent_events: Iterable[aw_core.Event]):
        self.recent_events = recent_events if isinstance(recent_events, deque) else deque(recent_events, 10)
        """The recent events we have posted to the aw-watcher-ask-away bucket.

        This is used to avoid asking the user to log an absence that they have already logged.

        Sorted from earliest to most recent."""

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

        Note: We compare overlap against the SMALLER of the two durations because gaps can
        extend over time as new activity data comes in. If we compared against the new (larger)
        duration, we'd fail to recognize the same gap and ask the user again.
        """  # noqa: E501
        for recent in self.recent_events:
            overlap_start = max(recent.timestamp, new.timestamp)
            overlap_end = min(recent.timestamp + recent.duration, new.timestamp + new.duration)
            overlap = overlap_end - overlap_start
            if overlap.total_seconds() <= 0:
                continue  # No overlap
            min_duration = min(recent.duration, new.duration)
            if overlap / min_duration > overlap_thresh:
                return True
        return False

    def add_event(self, event: aw_core.Event, message: str):
        assert not self.has_event(event)  # noqa: S101
        event.data[DATA_KEY] = message
        event["id"] = None  # Wipe the ID so we don't edit the AFK event.
        logger.debug(f"Posting event: {event}")
        self.recent_events.append(event)

    def get_unseen_afk_events(self, events: list[aw_core.Event], recency_thresh: float, durration_thresh: float):
        """Check whether we recently finished a large AFK event.

        Parameters
        ----------
        events : list[aw_core.Event]
            The events to check for AFK events.
        seconds : float
            Events more than this many seconds ago will be ignored.
        durration_thresh : float
            Events with a durration less than this many seconds will be ignored.
        """
        events_log = [
            (e.timestamp.astimezone(LOCAL_TIMEZONE).isoformat(), e.duration.total_seconds(), e.data["status"])
            for e in events
        ]
        logger.debug(f"Checking for unseen in: {events_log}")

        # Filter out events that have zero length. Sometimes a zero length not-afk event is generated if you open
        # up your computer from being suspended but don't do anything with it. This event is overwritten soon and
        # doesn't exist in later queries. If we don't filter them out we can ask the user to fill the time in twice.
        events = [e for e in events if e.duration.total_seconds() > 0]

        # Use gaps in non-afk events instead of the afk-events themselves to handle when the computer
        # is suspended or powered off.
        non_afk_events = squash_overlaps([e for e in events if not is_afk(e)])
        pseudo_afk_events = list(get_gaps(non_afk_events))

        pseudo_afk_events = [e for e in pseudo_afk_events if not self.has_event(e)]
        buffered_now = get_utc_now() - datetime.timedelta(seconds=recency_thresh)
        for event in pseudo_afk_events:
            long_enough = event.duration.seconds > durration_thresh
            recent_enough = event.timestamp + event.duration > buffered_now
            if long_enough and recent_enough:
                logger.debug(f"Found event to note: {event}")
                yield event
