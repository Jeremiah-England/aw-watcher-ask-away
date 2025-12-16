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

**Manual setup (if preferred):**
```console
cp misc/aw-watcher-ask-away.service ~/.config/systemd/user/
systemctl --user daemon-reload
systemctl --user enable aw-watcher-ask-away.service
systemctl --user start aw-watcher-ask-away.service
```

For Wayland, manually add to your compositor config:
```
exec systemctl --user import-environment WAYLAND_DISPLAY
```

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
