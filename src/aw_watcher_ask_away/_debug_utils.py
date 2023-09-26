# ruff: noqa: T203, T201
import pprint
from functools import cache
from itertools import pairwise

import aw_transform
from aw_client.client import ActivityWatchClient

from aw_watcher_ask_away.core import AWAskAwayClient


@cache
def get_client():
    return ActivityWatchClient("aw-watcher-ask-away-debugger")


def find_overlapping_events():
    """Find overlapping aw-watcher-ask-away events.

    If any of these exist it means the user was asked for something twice which is annoying and should be fixed.
    """
    with get_client() as client:
        state = AWAskAwayClient(client)
        for e1, e2 in pairwise(aw_transform.sort_by_timestamp(client.get_events(state.bucket_id, limit=100))):
            if e1.timestamp + e1.duration > e2.timestamp:
                print("---" * 10)
                print("Overlapping events:")
                pprint.pprint(e1)
                pprint.pprint(e2)


if __name__:
    find_overlapping_events()
