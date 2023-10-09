import json
import logging
import re
import time
import tkinter as tk
from collections import UserDict
from pathlib import Path
from tkinter import messagebox, simpledialog, ttk

import appdirs

logger = logging.getLogger(__name__)


def open_link(link: str):
    import webbrowser

    webbrowser.open(link)


class _AbbreviationStore(UserDict[str, str]):
    """A class to store abbreviations and their expansions.

    And to manage saving this information to the config directory.
    """

    def __init__(self, *args, **kwargs):
        super().__init__(self, *args, **kwargs)
        config_dir = Path(appdirs.user_config_dir("aw-watcher-ask-away"))
        config_dir.mkdir(parents=True, exist_ok=True)
        self._config_file = config_dir / "abbreviations.json"
        self._load_from_config()

    def _load_from_config(self):
        if self._config_file.exists():
            with self._config_file.open() as f:
                try:
                    self.update(json.load(f))
                except json.JSONDecodeError:
                    logger.exception("Failed to load abbreviations from config file.")

    def __setitem__(self, key: str, value: str):
        self.data[key] = value
        with self._config_file.open("w") as f:
            json.dump(self.data, f, indent=4)


# Singleton
abbreviations = _AbbreviationStore()


# TODO: This widget pops up off-center when using multiple screes on Linux, possibly other platforms.
# See https://stackoverflow.com/questions/30312875/tkinter-winfo-screenwidth-when-used-with-dual-monitors/57866046#57866046
class AWAskAwayDialog(simpledialog.Dialog):
    def __init__(self, title: str, prompt: str, history: list[str]) -> None:
        self.prompt = prompt
        self.history = history
        self.history_index = len(history)
        super().__init__(None, title)

    # @override (when we get to 3.12)
    def body(self, master):
        # Make the whole body a ttk fram as recommended by the tkdocs.com guy.
        # It should help the formatting be more consistent with the ttk children widgets.
        master = ttk.Frame(master)
        master.grid()

        # Prompt
        # Copied from the simpledialog source code.
        w = ttk.Label(master, text=self.prompt, justify=tk.LEFT)
        w.grid(row=0, padx=5, sticky=tk.W)

        # Input field
        self.entry = ttk.Entry(master, name="entry", width=40)
        self.entry.grid(row=1, padx=5, sticky=tk.W + tk.E)

        # README link
        doc_label = ttk.Label(master, text="Documentation", foreground="blue", cursor="hand2", justify=tk.RIGHT)
        doc_label.grid(row=0, padx=5, sticky=tk.W, column=1)
        doc_label.bind("<Button-1>", self.open_readme)

        # Issue link
        issue_label = ttk.Label(master, text="Report an issue", foreground="blue", cursor="hand2", justify=tk.RIGHT)
        issue_label.grid(row=1, padx=5, sticky=tk.W, column=1)
        issue_label.bind("<Button-1>", self.open_an_issue)

        # Text editing shortcuts
        self.bind("<Control-BackSpace>", self.remove_word)
        self.bind("<Control-u>", self.remove_to_start)
        self.bind("<Control-w>", self.remove_word)

        # Open web interface shortcut
        self.bind("<Control-o>", self.open_web_interface)

        # History navigation shotcuts
        self.bind("<Up>", self.previous_entry)
        self.bind("<Down>", self.next_entry)
        self.bind("<Control-j>", self.next_entry)
        self.bind("<Control-k>", self.previous_entry)

        # Expand abbreviations the user types
        self.entry.bind("<KeyRelease>", self.expand_abbreviations)

        # Add a new abbreviation from a highlighted section of text.
        self.entry.bind("<Control-n>", self.save_new_abbreviation)
        # TODO: Add a way to remove unwanted abbreviations.
        # What if someone uses "a" without thinking?

        return self.entry

    def save_new_abbreviation(self, event=None):  # noqa: ARG002
        # Get the highlighted Text
        highlighted_text = self.entry.selection_get().strip()
        result = simpledialog.askstring(
            "Set Abbreviation", "What would you like to abbreviate this as?", parent=self, initialvalue=highlighted_text
        )
        if result:
            result = result.strip()
            if not re.fullmatch(r"\w+", result):
                messagebox.showerror("Invalid abbreviation", "Abbreviations must be alphanumeric.")
                return

            if existing := abbreviations.get(result):
                if not messagebox.askyesno(
                    f"That abbreviation ({result}) already exists as '{existing}', would you like to over write?"
                ):
                    return
            abbreviations[result] = highlighted_text

    def expand_abbreviations(self, event=None):  # noqa: ARG002
        text = self.entry.get()
        cursor_index = self.entry.index(tk.INSERT)

        # Get the potential appreviation
        abbr_regex = r"(\w+)\s$"
        abbr = re.search(abbr_regex, text[:cursor_index])
        if abbr and abbr.group(1) in abbreviations:
            before_index = len(re.sub(abbr_regex, "", text[:cursor_index]))
            self.entry.delete(before_index, cursor_index - 1)
            self.entry.insert(before_index, abbreviations[abbr.group(1)])

    def set_text(self, text: str):
        self.entry.delete(0, tk.END)
        self.entry.insert(0, text)

    def previous_entry(self, event=None):  # noqa: ARG002
        self.history_index = max(0, self.history_index - 1)
        self.set_text(self.history[self.history_index])

    def next_entry(self, event=None):  # noqa: ARG002
        self.history_index = min(len(self.history) - 1, self.history_index + 1)
        self.set_text(self.history[self.history_index])

    def open_an_issue(self, event=None):  # noqa: ARG002
        open_link("https://github.com/Jeremiah-England/aw-watcher-ask-away/issues/new")

    def open_readme(self, event=None):  # noqa: ARG002
        open_link("https://github.com/Jeremiah-England/aw-watcher-ask-away#aw-watcher-ask-away")

    def open_web_interface(self, event=None):  # noqa: ARG002
        open_link("http://localhost:5600/#/timeline")

    def remove_word(self, event=None):  # noqa: ARG002
        text = self.entry.get()
        cursor_index = self.entry.index(tk.INSERT)
        new_before = re.sub(r"\w+\W*$", "", text[:cursor_index])

        self.entry.delete(0, cursor_index)
        self.entry.insert(0, new_before)

    def remove_to_start(self, event=None):  # noqa: ARG002
        cursor = self.entry.index(tk.INSERT)
        self.entry.delete(0, cursor)
        self.entry.insert(0, "")

    # If you want to retrieve the entered text when the dialog closes:
    def apply(self):
        self.result = self.entry.get().strip()

    def snooze(self):
        self.cancel()
        logging.log(logging.INFO, "Snoozing for 10 minutes.")
        time.sleep(60 * 10)

    # @override (when we get to 3.12)
    def buttonbox(self):
        """The buttons at the bottom of the dialog.

        This is overridden to add a "snooze" button.
        """
        box = ttk.Frame(self)

        w = ttk.Button(box, text="OK", width=10, command=self.ok, default=tk.ACTIVE)
        w.pack(side=tk.LEFT, padx=5, pady=5)
        w = ttk.Button(box, text="Cancel", width=10, command=self.cancel)
        w.pack(side=tk.LEFT, padx=5, pady=5)

        # TODO: Figure out a quick easy way to pick how long to snooze for.
        w = ttk.Button(box, text="Snooze (10m)", command=self.snooze)
        w.pack(side=tk.LEFT, padx=5, pady=5)

        self.bind("<Return>", self.ok)
        self.bind("<Escape>", self.cancel)

        box.pack()


def ask_string(title: str, prompt: str, history: list[str]):
    d = AWAskAwayDialog(title, prompt, history)
    return d.result


if __name__ == "__main__":
    print(ask_string("Testing testing", "123", ["1", "2", "3", "4"]))  # noqa: T201
