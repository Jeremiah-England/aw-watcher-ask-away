"""Configuration management for aw-watcher-ask-away."""

from aw_core.config import load_config_toml

DEFAULT_CONFIG = """
# Number of minutes to look into the past for events
depth = 10.0

# Number of seconds to wait before checking for AFK events again
frequency = 5.0

# Number of minutes you need to be away before reporting on it
length = 5.0
""".strip()


def load_config() -> dict:
    """Load configuration using ActivityWatch standard approach.

    Config location: ~/.config/activitywatch/aw-watcher-ask-away/aw-watcher-ask-away.toml
    """
    return load_config_toml("aw-watcher-ask-away", DEFAULT_CONFIG)
