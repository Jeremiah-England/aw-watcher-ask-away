"""Tests for configuration loading."""

from unittest.mock import patch

from aw_watcher_ask_away.config import DEFAULT_CONFIG, load_config


def test_default_config_has_expected_keys() -> None:
    """Test that DEFAULT_CONFIG contains all expected configuration keys."""
    # Parse the default config string to check it's valid TOML
    import tomllib

    config = tomllib.loads(DEFAULT_CONFIG)

    assert "depth" in config
    assert "frequency" in config
    assert "length" in config


def test_default_config_values() -> None:
    """Test that DEFAULT_CONFIG has expected default values."""
    import tomllib

    config = tomllib.loads(DEFAULT_CONFIG)

    assert config["depth"] == 10.0
    assert config["frequency"] == 5.0
    assert config["length"] == 5.0


def test_load_config_returns_defaults_when_no_file() -> None:
    """Test that load_config returns defaults when config file doesn't exist."""
    # Mock aw_core.config.load_config_toml to return parsed defaults
    with patch("aw_watcher_ask_away.config.load_config_toml") as mock_load:
        import tomllib

        mock_load.return_value = tomllib.loads(DEFAULT_CONFIG)

        config = load_config()

        # Verify load_config_toml was called with correct arguments
        mock_load.assert_called_once_with("aw-watcher-ask-away", DEFAULT_CONFIG)

        # Verify returned config has expected values
        assert config["depth"] == 10.0
        assert config["frequency"] == 5.0
        assert config["length"] == 5.0


def test_load_config_returns_custom_values() -> None:
    """Test that load_config returns custom values when config file exists."""
    custom_config = {"depth": 15.0, "frequency": 10.0, "length": 3.0}

    with patch("aw_watcher_ask_away.config.load_config_toml") as mock_load:
        mock_load.return_value = custom_config

        config = load_config()

        assert config["depth"] == 15.0
        assert config["frequency"] == 10.0
        assert config["length"] == 3.0
