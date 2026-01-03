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

from aw_watcher_ask_away.utils import LOCAL_TIMEZONE, format_time_local

# Import ActivityLine for split mode support
try:
    from aw_watcher_ask_away.split_dialog import ActivityLine
except ImportError:
    # Fallback if split_dialog not available
    ActivityLine = None

WATCHER_NAME = "aw-watcher-ask-away"
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
        """Post a single event with error handling.

        Only marks the event as "seen" after successful posting to avoid data loss.
        """
        try:
            # Update event with message
            event.data[DATA_KEY] = message
            event["id"] = None  # Wipe the ID so we don't edit the AFK event

            # Post to ActivityWatch FIRST
            self.client.insert_event(self.bucket_id, event)
            logger.info(f"Successfully posted event: {message}")

            # Only mark as seen AFTER successful posting
            self.state.mark_event_as_seen(event)

        except Exception as e:
            logger.error(f"Failed to post event: {e}")
            logger.error("Event will be queued for retry on next iteration")
            # Don't mark as seen - event will be prompted again
            raise

    def post_split_events(self, original_event: aw_core.Event, activities: list):
        """Post multiple events from split mode with error handling.

        Args:
            original_event: The original AFK event that was split
            activities: List of ActivityLine objects from split mode
        """
        if ActivityLine is None:
            logger.error("ActivityLine not available, cannot post split events")
            return

        posted_count = 0
        failed_count = 0

        # Generate a unique split ID based on original event timestamp
        split_id = str(original_event.timestamp.timestamp())

        for i, activity in enumerate(activities):
            try:
                # Create a new event for this activity with split metadata
                event = aw_core.Event(
                    timestamp=activity.start_time,
                    duration=datetime.timedelta(
                        minutes=activity.duration_minutes,
                        seconds=activity.duration_seconds
                    ),
                    data={
                        DATA_KEY: activity.description,
                        "split": True,
                        "split_count": len(activities),
                        "split_index": i,
                        "split_id": split_id,
                    }
                )

                # Post to ActivityWatch
                self.client.insert_event(self.bucket_id, event)
                logger.info(f"Posted activity {i+1}/{len(activities)}: '{activity.description}' "
                          f"({activity.duration_minutes}m {activity.duration_seconds}s)")
                posted_count += 1

            except Exception as e:
                logger.error(f"Failed to post activity {i+1}/{len(activities)}: {e}")
                failed_count += 1
                # Continue trying to post remaining activities

        # Only mark original event as seen if ALL activities were posted successfully
        if failed_count == 0:
            self.state.mark_event_as_seen(original_event)
            logger.info(f"Successfully posted all {posted_count} split activities")
        else:
            logger.warning(f"Posted {posted_count}/{len(activities)} activities, "
                         f"{failed_count} failed. Event will be prompted again.")
            # Don't mark as seen - user will be prompted again

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
                logger.debug(f"Most recent event: {most_recent.timestamp.astimezone(LOCAL_TIMEZONE).strftime('%H:%M:%S')} | "
                           f"status={most_recent.data.get('status')} | currently_afk={currently_afk}")
                if currently_afk:
                    # Currently AFK, wait to bring up the prompt
                    logger.debug("Currently AFK, waiting for user to return")
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

    def mark_event_as_seen(self, event: aw_core.Event):
        """Mark an event as seen (add to recent_events) to prevent re-prompting.

        This should only be called AFTER the event has been successfully posted.
        """
        if not self.has_event(event):
            logger.debug(f"Marking event as seen: {event}")
            self.recent_events.append(event)
        else:
            logger.debug(f"Event already marked as seen: {event}")

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
        logger.debug(f"Non-AFK events after squash: {len(non_afk_events)}")
        for evt in non_afk_events[-3:]:  # Last 3 events
            start = evt.timestamp.astimezone(LOCAL_TIMEZONE).strftime('%H:%M:%S')
            end = (evt.timestamp + evt.duration).astimezone(LOCAL_TIMEZONE).strftime('%H:%M:%S')
            logger.debug(f"  Event: {start} - {end} ({evt.duration.total_seconds():.1f}s)")
        pseudo_afk_events = list(get_gaps(non_afk_events))
        logger.debug(f"Gaps found: {len(pseudo_afk_events)}")
        for gap in pseudo_afk_events:
            logger.debug(f"  Gap: {gap.timestamp.astimezone(LOCAL_TIMEZONE).strftime('%H:%M:%S')} | {gap.duration.total_seconds():.1f}s")

        pseudo_afk_events = [e for e in pseudo_afk_events if not self.has_event(e)]
        logger.debug(f"Gaps after filtering seen: {len(pseudo_afk_events)}")
        buffered_now = get_utc_now() - datetime.timedelta(seconds=recency_thresh)
        for event in pseudo_afk_events:
            long_enough = event.duration.seconds > durration_thresh
            recent_enough = event.timestamp + event.duration > buffered_now
            logger.debug(f"  Checking gap at {event.timestamp.astimezone(LOCAL_TIMEZONE).strftime('%H:%M:%S')}: "
                       f"long_enough={long_enough} ({event.duration.seconds}s > {durration_thresh}s), "
                       f"recent_enough={recent_enough}")
            if long_enough and recent_enough:
                logger.debug(f"Found event to note: {event}")
                yield event
