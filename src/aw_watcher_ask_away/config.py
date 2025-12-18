"""Configuration management for aw-watcher-ask-away."""

from aw_core.config import load_config_toml

DEFAULT_CONFIG = """
# Number of minutes to look into the past for events
depth = 10.0

# Number of seconds to wait before checking for AFK events again
frequency = 5.0

# Number of minutes you need to be away before reporting on it
length = 5.0

# Enable integration with aw-watcher-lid for lid/suspend events
# OPTIONAL: Requires aw-watcher-lid to be installed and running
# See: https://github.com/tobixen/aw-watcher-lid
# When enabled, you'll be prompted about lid closures in addition to regular AFK
enable_lid_events = true
""".strip()


def load_config() -> dict:
    """Load configuration using ActivityWatch standard approach.

    Config location: ~/.config/activitywatch/aw-watcher-ask-away/aw-watcher-ask-away.toml
    """
    return load_config_toml("aw-watcher-ask-away", DEFAULT_CONFIG)
