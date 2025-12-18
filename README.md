# AW Watcher Ask Away

[![PyPI - Version](https://img.shields.io/pypi/v/aw-watcher-ask-away.svg)](https://pypi.org/project/aw-watcher-ask-away)
[![PyPI - Python Version](https://img.shields.io/pypi/pyversions/aw-watcher-ask-away.svg)](https://pypi.org/project/aw-watcher-ask-away)

---

This [ActivityWatch](https://activitywatch.net) "watcher" asks you what you were doing in a pop-up dialogue when you get back to your computer from an AFK (away from keyboard) break.

## Installation

```console
pipx install aw-watcher-ask-away
```

([Need to install `pipx` first?](https://pypa.github.io/pipx/installation/))

## Running

### Recommended: Using aw-qt

The recommended way to run this watcher is through [aw-qt](https://github.com/ActivityWatch/aw-qt), which manages both the server and watchers automatically. After installing aw-watcher-ask-away, aw-qt should detect and start it automatically.

### Alternative: Manual Start

If not using aw-qt, you can run it manually:
```console
aw-watcher-ask-away
```

Make sure `aw-server` and `aw-watcher-afk` are running first, as this watcher monitors AFK events.

### Alternative: systemd (Linux)

For users not using aw-qt who want automatic startup via systemd:

**Quick setup with Makefile:**
```console
make enable-service
```

**For Wayland users, also run:**
```console
make setup-wayland
```

This automatically configures your compositor to import the WAYLAND_DISPLAY environment variable.

## Configuration

The watcher can be configured via a config file or command-line arguments. Command-line arguments override config file settings.

### Config File

Configuration is stored in the ActivityWatch standard location:
```
~/.config/activitywatch/aw-watcher-ask-away/aw-watcher-ask-away.toml
```

The config file is created automatically with default values on first run if it doesn't exist.

### Command-line Arguments

You can override config file settings using command-line arguments:
```console
aw-watcher-ask-away --depth 15 --frequency 10 --length 3
```

Available options:
- `--depth`: Minutes to look into the past for events (default: from config or 10)
- `--frequency`: Seconds between AFK event checks (default: from config or 5)
- `--length`: Minimum AFK minutes before prompting (default: from config or 5)
- `--testing`: Run in testing mode
- `--verbose`: Enable verbose logging

### Lid Watcher Integration (Optional)

This watcher can integrate with [aw-watcher-lid](https://github.com/tobixen/aw-watcher-lid) to also prompt you about laptop lid closures and system suspends, not just regular AFK periods.

**Why use both watchers?**
- Regular AFK: Detects when you step away from keyboard but leave computer running
- Lid events: Provides exact timestamps for when you close/open your laptop lid or suspend/resume the system
- Combined: More complete picture of when you're away from your computer

**Setup:**
1. Install aw-watcher-lid: `pipx install aw-watcher-lid`
2. Start it (see [aw-watcher-lid README](https://github.com/tobixen/aw-watcher-lid#readme) for setup)
3. aw-watcher-ask-away will automatically detect and use it

**To disable lid integration:**
Set `enable_lid_events = false` in your config file.

**Note:** aw-watcher-lid is an optional third-party watcher, not part of the standard ActivityWatch distribution.

## Roadmap

Most of the improvements involve a more complicated pop-up window.

- Use `pyinstaller` or something for distribution to people who are not developers and know how to install things from PyPI.
  - Set up a website, probably with a GitHub organization.
- Handle calls better/stop asking what you were doing every couple minutes when in a call.
- See whether people would rather add data to AFK events instead of creating a separate bucket. Maybe make that an option/configurable.

## Contributing

Here are some helpful links:

- [How to create an ActivityWatch watcher](https://docs.activitywatch.net/en/latest/examples/writing-watchers.html).
- ["Manually tracking away/offline-time" forum discussion](https://forum.activitywatch.net/t/manually-tracking-away-offline-time/284)

Note: I am using this project to get experience with the `hatch` project manager.
I have never use it before and I'm probably doing some things wrong there.

## License

`aw-watcher-ask-away` is distributed under the terms of the [MIT](https://spdx.org/licenses/MIT.html) license.
