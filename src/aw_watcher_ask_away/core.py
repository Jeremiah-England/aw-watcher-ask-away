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
    match [bucket for bucket in buckets if "afk" in bucket and "lid" not in bucket]:
        case []:
            raise AWWatcherAskAwayError("Cannot find the afk bucket.")
        case [bucket]:
            return bucket
        case _:
            raise AWWatcherAskAwayError(f"Found too many afk buckets: {buckets}.")


def find_lid_bucket(buckets: dict[str, Any]):
    """Find the lid watcher bucket (aw-watcher-lid).

    Returns None if not found (lid watcher is optional).
    """
    lid_buckets = [bucket for bucket in buckets if "lid" in bucket]
    if len(lid_buckets) == 0:
        return None
    if len(lid_buckets) == 1:
        return lid_buckets[0]
    raise AWWatcherAskAwayError(f"Found too many lid buckets: {buckets}.")


def is_afk(event: aw_core.Event) -> bool:
    """Check if event represents an AFK state.

    Handles both regular AFK ("afk") and system-level AFK ("system-afk" from lid/suspend events).
    """
    return event.data["status"] in ("afk", "system-afk")


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
    def __init__(self, client: ActivityWatchClient, enable_lid_events: bool = True):
        self.client = client
        self.bucket_id = f"{WATCHER_NAME}_{self.client.client_hostname}"
        self.enable_lid_events = enable_lid_events

        if self.bucket_id not in self._all_buckets:
            # TODO: Look into why aw-watcher-afk uses queued=True here.
            client.create_bucket(self.bucket_id, event_type="afktask")

        recent_events = deque(maxlen=10)
        recent_events.extend(aw_transform.sort_by_timestamp(client.get_events(self.bucket_id, limit=10)))
        self.state = AWAskAwayState(recent_events)

        self.afk_bucket_id = find_afk_bucket(self._all_buckets)

        # Check for optional lid watcher integration (aw-watcher-lid)
        # See: https://github.com/tobixen/aw-watcher-lid
        self.lid_bucket_id = None
        if enable_lid_events:
            self.lid_bucket_id = find_lid_bucket(self._all_buckets)
            if self.lid_bucket_id:
                logger.info(f"Lid watcher detected: {self.lid_bucket_id}")
            else:
                logger.info("Lid watcher not found, will only use regular AFK events")
        else:
            logger.info("Lid watcher integration disabled in config")

    @cached_property
    def _all_buckets(self):
        return self.client.get_buckets()

    def post_event(self, event: aw_core.Event, message: str):
        self.state.add_event(event, message)
        self.client.insert_event(self.bucket_id, event)

    def get_new_afk_events_to_note(self, seconds: float, durration_thresh: float):
        """Check whether we recently finished a large AFK event.

        Fetches events from both regular AFK watcher and lid watcher (if enabled),
        then merges them to get a complete picture of away time.

        Parameters
        ----------
        seconds : float
            The number of seconds to look into the past for events.
        durration_thresh : float
            The number of seconds you need to be away before reporting on it.
        """
        try:
            # Fetch regular AFK events
            afk_events = self.client.get_events(self.afk_bucket_id, limit=10)

            # Fetch lid events if enabled and bucket exists
            lid_events = []
            if self.lid_bucket_id:
                try:
                    lid_events = self.client.get_events(self.lid_bucket_id, limit=10)
                except HTTPError:
                    logger.warning("Failed to get lid events, continuing with AFK events only")

            # Merge and sort events from both sources by timestamp
            # Note: sort_by_timestamp() sorts in ASCENDING order (oldest first)
            all_events = aw_transform.sort_by_timestamp(afk_events + lid_events)

            # Check if currently AFK (from either source)
            # Most recent event is LAST after sorting (ascending order)
            if all_events:
                most_recent = all_events[-1]  # Last element is most recent
                currently_afk = is_afk(most_recent)
                if currently_afk:
                    # Currently AFK, wait to bring up the prompt
                    return

            yield from self.state.get_unseen_afk_events(all_events, seconds, durration_thresh)
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
        """  # noqa: E501
        for recent in self.recent_events:
            overlap_start = max(recent.timestamp, new.timestamp)
            overlap_end = min(recent.timestamp + recent.duration, new.timestamp + new.duration)
            overlap = overlap_end - overlap_start
            if overlap / new.duration > overlap_thresh:
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
