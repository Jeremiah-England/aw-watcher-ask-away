"""Tests for lid watcher integration."""

import aw_core
import pytest

from aw_watcher_ask_away.core import AWWatcherAskAwayError, find_lid_bucket, is_afk


def test_find_lid_bucket_found() -> None:
    """Test finding lid bucket when it exists."""
    buckets = {
        "aw-watcher-afk_hostname": {},
        "aw-watcher-lid_hostname": {},
    }

    lid_bucket = find_lid_bucket(buckets)
    assert lid_bucket == "aw-watcher-lid_hostname"


def test_find_lid_bucket_not_found() -> None:
    """Test finding lid bucket when it doesn't exist."""
    buckets = {
        "aw-watcher-afk_hostname": {},
    }

    lid_bucket = find_lid_bucket(buckets)
    assert lid_bucket is None


def test_find_lid_bucket_multiple() -> None:
    """Test error when multiple lid buckets found."""
    buckets = {
        "aw-watcher-lid_hostname1": {},
        "aw-watcher-lid_hostname2": {},
    }

    with pytest.raises(AWWatcherAskAwayError, match="too many lid buckets"):
        find_lid_bucket(buckets)


def test_is_afk_regular() -> None:
    """Test is_afk with regular AFK event."""
    event = aw_core.Event(data={"status": "afk"})
    assert is_afk(event) is True


def test_is_afk_system() -> None:
    """Test is_afk with system-afk event from lid watcher."""
    event = aw_core.Event(data={"status": "system-afk"})
    assert is_afk(event) is True


def test_is_afk_not_afk() -> None:
    """Test is_afk with not-afk event."""
    event = aw_core.Event(data={"status": "not-afk"})
    assert is_afk(event) is False
