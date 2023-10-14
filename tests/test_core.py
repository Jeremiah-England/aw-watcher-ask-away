# ruff: noqa: E501
import datetime

import aw_core

from aw_watcher_ask_away.core import AWAskAwayState

AFK = "afk"
NOT_AFK = "not-afk"
INF = 1000 * 365 * 24 * 60 * 60  # About 1000 years of seconds. Cannot use float("inf") in timedeltas.
FIRST_DATE = datetime.datetime(1970, 1, 1, tzinfo=datetime.UTC)


TupleEvent = tuple[int | datetime.datetime, int, str]


def _tuple_to_event(tup: TupleEvent) -> aw_core.Event:
    match tup[0]:
        case int():
            timestamp = FIRST_DATE + datetime.timedelta(seconds=tup[0])
        case datetime.datetime():
            timestamp = tup[0]
        case str():
            timestamp = datetime.datetime.fromisoformat(tup[0])
    return aw_core.Event(timestamp=timestamp, duration=tup[1], data={"status": tup[2]})


def _event_to_tuple(event: aw_core.Event) -> tuple[int, int]:
    return (int(event.timestamp.timestamp()), event.duration.seconds)


def test_get_unseen_afk_events_initial():
    # Just some initial tests not meant to handle particular bugs or anything.
    init_events_tups: list[TupleEvent] = [
        (0, 60, NOT_AFK),
        (60, 20, AFK),
        (80, 100, NOT_AFK),
    ]
    init_events = [_tuple_to_event(tup) for tup in init_events_tups]

    state = AWAskAwayState([])

    # Nothing should pass the recency threshold.
    assert list(state.get_unseen_afk_events(init_events, 100, 10)) == []

    assert [_event_to_tuple(e) for e in state.get_unseen_afk_events(init_events, INF, 10)] == [(60, 20)]

    # Should be excluded by the duration threshold.
    assert list(state.get_unseen_afk_events(init_events, INF, 21)) == []

    # Test that recency works by end timestamp and not beginning timestamp.
    now = datetime.datetime.now().astimezone(datetime.UTC)
    events = list(state.get_unseen_afk_events([*init_events, _tuple_to_event((now, 10, NOT_AFK))], 10, 21))
    assert len(events) == 1
    assert events[0].timestamp == FIRST_DATE + datetime.timedelta(seconds=80 + 100)
    assert int(events[0].duration.total_seconds()) == int(
        (now - (FIRST_DATE + datetime.timedelta(seconds=80 + 100))).total_seconds()
    )


def test_double_ask_1():
    # 2023-09-26 12:08:03 [DEBUG]: Checking for unseen in: [('2023-09-26T12:04:55.820000-04:00', 5, 'not-afk'), ('2023-09-26T11:58:16.969000-04:00', 398, 'afk'), ('2023-09-26T11:58:16.969000-04:00', 190, 'afk'), ('2023-09-26T11:55:10.545000-04:00', 186, 'not-afk'), ('2023-09-26T11:55:10.545000-04:00', 15, 'not-afk'), ('2023-09-26T11:49:27.192000-04:00', 343, 'afk'), ('2023-09-26T11:49:27.192000-04:00', 190, 'afk'), ('2023-09-26T11:11:22.127000-04:00', 2285, 'not-afk'), ('2023-09-26T11:00:43.666000-04:00', 638, 'afk'), ('2023-09-26T11:00:43.666000-04:00', 190, 'afk')]  (aw_watcher_ask_away.core:164)  # noqa: E501
    # 2023-09-26 12:08:03 [DEBUG]: Found event to note: {'id': None, 'timestamp': datetime.datetime(2023, 9, 26, 15, 58, 16, 969000, tzinfo=datetime.timezone.utc), 'duration': datetime.timedelta(seconds=398, microseconds=851000), 'data': {'message': 'talk to nikhil'}}  (aw_watcher_ask_away.core:181)  # noqa: E501
    # 2023-09-26 12:08:22 [DEBUG]: Checking for unseen in: [('2023-09-26T12:08:11.328000-04:00', 10, 'not-afk'), ('2023-09-26T12:05:00.965000-04:00', 190, 'afk'), ('2023-09-26T12:05:00.965000-04:00', 190, 'afk'), ('2023-09-26T12:04:55.820000-04:00', 5, 'not-afk'), ('2023-09-26T11:58:16.969000-04:00', 398, 'afk'), ('2023-09-26T11:58:16.969000-04:00', 190, 'afk'), ('2023-09-26T11:55:10.545000-04:00', 186, 'not-afk'), ('2023-09-26T11:55:10.545000-04:00', 15, 'not-afk'), ('2023-09-26T11:49:27.192000-04:00', 343, 'afk'), ('2023-09-26T11:49:27.192000-04:00', 190, 'afk')]  (aw_watcher_ask_away.core:164)  # noqa: E501
    # 2023-09-26 12:08:22 [DEBUG]: Found event to note: {'id': None, 'timestamp': datetime.datetime(2023, 9, 26, 15, 58, 16, 969000, tzinfo=datetime.timezone.utc), 'duration': datetime.timedelta(seconds=594, microseconds=359000), 'data': {'message': 'Lunch: Talking to James and Ben about virtualization'}}  (aw_watcher_ask_away.core:181)  # noqa: E501

    # fmt: off
    first = [                                                                                                                                                          ("2023-09-26T12:04:55.820000-04:00", 5, "not-afk"), ("2023-09-26T11:58:16.969000-04:00", 398, "afk"), ("2023-09-26T11:58:16.969000-04:00", 190, "afk"), ("2023-09-26T11:55:10.545000-04:00", 186, "not-afk"), ("2023-09-26T11:55:10.545000-04:00", 15, "not-afk"), ("2023-09-26T11:49:27.192000-04:00", 343, "afk"), ("2023-09-26T11:49:27.192000-04:00", 190, "afk"), ("2023-09-26T11:11:22.127000-04:00", 2285, "not-afk"), ("2023-09-26T11:00:43.666000-04:00", 638, "afk"), ("2023-09-26T11:00:43.666000-04:00", 190, "afk")]  # noqa: E501
    second = [("2023-09-26T12:08:11.328000-04:00", 10, "not-afk"), ("2023-09-26T12:05:00.965000-04:00", 190, "afk"), ("2023-09-26T12:05:00.965000-04:00", 190, "afk"), ("2023-09-26T12:04:55.820000-04:00", 5, "not-afk"), ("2023-09-26T11:58:16.969000-04:00", 398, "afk"), ("2023-09-26T11:58:16.969000-04:00", 190, "afk"), ("2023-09-26T11:55:10.545000-04:00", 186, "not-afk"), ("2023-09-26T11:55:10.545000-04:00", 15, "not-afk"), ("2023-09-26T11:49:27.192000-04:00", 343, "afk"), ("2023-09-26T11:49:27.192000-04:00", 190, "afk")]  # noqa: E501
    # fmt: on
    first = [_tuple_to_event(tup) for tup in first]
    second = [_tuple_to_event(tup) for tup in second]

    state = AWAskAwayState([])
    first_unseen = list(state.get_unseen_afk_events(first, INF, 3 * 60))
    for event in first_unseen:
        state.add_event(event, "message")

    second_unseen = list(state.get_unseen_afk_events(second, INF, 3 * 60))
    assert len(second_unseen) == 1
    assert second_unseen[0].timestamp == datetime.datetime.fromisoformat("2023-09-26T12:05:00.820000-04:00")
    assert int(second_unseen[0].duration.total_seconds()) == 190


def test_double_ask_suspend_afk():
    # This happened after opening up my computer after it was suspended but then not actually doing anything for a while.
    # 2023-10-13 08:44:54 [DEBUG]: Checking for unseen in: [('2023-10-13T08:41:50.337000-04:00', 0.0, 'not-afk'), ('2023-10-13T07:09:50.154000-04:00', 1724.216, 'not-afk'), ('2023-10-12T23:40:00.083000-04:00', 26990.07, 'afk'), ('2023-10-12T23:40:00.083000-04:00', 26984.982452, 'afk'), ('2023-10-12T23:39:49.928000-04:00', 10.155, 'not-afk'), ('2023-10-12T22:19:22.173000-04:00', 4827.754, 'afk'), ('2023-10-12T22:19:22.173000-04:00', 190.570087, 'afk'), ('2023-10-12T22:01:01.254000-04:00', 1100.919, 'not-afk'), ('2023-10-12T17:31:40.928000-04:00', 16160.325, 'afk'), ('2023-10-12T17:31:40.928000-04:00', 190.403036, 'afk')]  (aw_watcher_ask_away.core:160)
    # 2023-10-13 08:44:54 [DEBUG]: Found event to note: {'id': None, 'timestamp': datetime.datetime(2023, 10, 13, 11, 38, 34, 370000, tzinfo=datetime.timezone.utc), 'duration': datetime.timedelta(seconds=3795, microseconds=967000), 'data': {'message': 'Sleeping / Feeding Jupiter / Eating / Playing with Jupiter / Composter'}}  (aw_watcher_ask_away.core:173)
    # 2023-10-13 08:47:54 [DEBUG]: Checking for unseen in: [('2023-10-13T08:47:38.792000-04:00', 10.149, 'not-afk'), ('2023-10-13T08:41:50.337000-04:00', 348.454, 'afk'), ('2023-10-13T08:41:50.337000-04:00', 195.633261, 'afk'), ('2023-10-13T08:41:50.337000-04:00', 190.507251, 'afk'), ('2023-10-13T07:09:50.154000-04:00', 1724.216, 'not-afk'), ('2023-10-12T23:40:00.083000-04:00', 26990.07, 'afk'), ('2023-10-12T23:40:00.083000-04:00', 26984.982452, 'afk'), ('2023-10-12T23:39:49.928000-04:00', 10.155, 'not-afk'), ('2023-10-12T22:19:22.173000-04:00', 4827.754, 'afk'), ('2023-10-12T22:19:22.173000-04:00', 190.570087, 'afk')]  (aw_watcher_ask_away.core:160)
    # 2023-10-13 08:47:54 [DEBUG]: Found event to note: {'id': None, 'timestamp': datetime.datetime(2023, 10, 13, 11, 38, 34, 370000, tzinfo=datetime.timezone.utc), 'duration': datetime.timedelta(seconds=4144, microseconds=422000), 'data': {'message': 'Driving to work'}}  (aw_watcher_ask_away.core:173)

    # fmt: off
    #                                                                                                                                                                                 Notice: not-afk with zero length...                      From here back things are the same.
    first = [                                                                                                                                                                         ("2023-10-13T08:41:50.337000-04:00", 0.0, "not-afk"),    ("2023-10-13T07:09:50.154000-04:00", 1724.216, "not-afk"), ("2023-10-12T23:40:00.083000-04:00", 26990.07, "afk"), ("2023-10-12T23:40:00.083000-04:00", 26984.982452, "afk"), ("2023-10-12T23:39:49.928000-04:00", 10.155, "not-afk"), ("2023-10-12T22:19:22.173000-04:00", 4827.754, "afk"), ("2023-10-12T22:19:22.173000-04:00", 190.570087, "afk"), ("2023-10-12T22:01:01.254000-04:00", 1100.919, "not-afk"), ("2023-10-12T17:31:40.928000-04:00", 16160.325, "afk"), ("2023-10-12T17:31:40.928000-04:00", 190.403036, "afk")]
    second = [("2023-10-13T08:47:38.792000-04:00", 10.149, "not-afk"), ("2023-10-13T08:41:50.337000-04:00", 348.454, "afk"), ("2023-10-13T08:41:50.337000-04:00", 195.633261, "afk"), ("2023-10-13T08:41:50.337000-04:00", 190.507251, "afk"), ("2023-10-13T07:09:50.154000-04:00", 1724.216, "not-afk"), ("2023-10-12T23:40:00.083000-04:00", 26990.07, "afk"), ("2023-10-12T23:40:00.083000-04:00", 26984.982452, "afk"), ("2023-10-12T23:39:49.928000-04:00", 10.155, "not-afk"), ("2023-10-12T22:19:22.173000-04:00", 4827.754, "afk"), ("2023-10-12T22:19:22.173000-04:00", 190.570087, "afk")]
    # fmt: on

    first = [_tuple_to_event(tup) for tup in first]
    second = [_tuple_to_event(tup) for tup in second]

    state = AWAskAwayState([])
    first_unseen = list(state.get_unseen_afk_events(first, INF, 3 * 60))
    for event in first_unseen:
        state.add_event(event, "message")
    # This is the main thing being tested. If there are three events then we will be asked to put in duplicate information in the next step.
    assert len(first_unseen) == 2

    second_unseen = list(state.get_unseen_afk_events(second, INF, 3 * 60))
    assert len(second_unseen) == 1
    expected_start = datetime.datetime.fromisoformat("2023-10-13T07:09:50.154000-04:00") + datetime.timedelta(
        seconds=1724.216
    )
    expected_end = datetime.datetime.fromisoformat("2023-10-13T08:47:38.792000-04:00")
    assert second_unseen[0].timestamp == expected_start
    assert second_unseen[0].duration.total_seconds() == (expected_end - expected_start).total_seconds()
