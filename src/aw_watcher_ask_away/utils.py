"""Utility functions for aw-watcher-ask-away."""

import datetime
import locale

LOCAL_TIMEZONE = datetime.datetime.now().astimezone().tzinfo


def format_time_local(dt: datetime.datetime, include_seconds: bool = False) -> str:
    """Format a datetime as local time using locale-appropriate format.

    Uses 24-hour clock unless the locale prefers 12-hour format.
    Always converts to local timezone first.

    Args:
        dt: Datetime to format (can be any timezone, will be converted to local)
        include_seconds: Whether to include seconds in the output

    Returns:
        Formatted time string (e.g., "14:30" or "2:30 PM" depending on locale)
    """
    # Convert to local timezone
    local_dt = dt.astimezone(LOCAL_TIMEZONE)

    # Check locale preference for time format
    # %X gives the locale's preferred time representation
    # We check if it contains AM/PM indicators to detect 12-hour preference
    try:
        locale_time_format = locale.nl_langinfo(locale.T_FMT)
        use_12_hour = '%p' in locale_time_format or '%P' in locale_time_format or \
                      '%I' in locale_time_format or '%r' in locale_time_format
    except (AttributeError, locale.Error):
        # Fallback: use 24-hour format if we can't determine locale
        use_12_hour = False

    if use_12_hour:
        if include_seconds:
            return local_dt.strftime("%I:%M:%S %p").lstrip("0")
        else:
            return local_dt.strftime("%I:%M %p").lstrip("0")
    else:
        if include_seconds:
            return local_dt.strftime("%H:%M:%S")
        else:
            return local_dt.strftime("%H:%M")
