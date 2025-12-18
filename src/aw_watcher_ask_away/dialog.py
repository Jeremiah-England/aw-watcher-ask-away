import json
import logging
import re
import time
import tkinter as tk
from collections import UserDict
from itertools import chain
from pathlib import Path
from tkinter import messagebox, simpledialog, ttk

import appdirs

logger = logging.getLogger(__name__)

root = tk.Tk()
root.withdraw()


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

    def _save_to_config(self):
        with self._config_file.open("w") as f:
            json.dump(self.data, f, indent=4)

    def __setitem__(self, key: str, value: str):
        self.data[key] = value
        self._save_to_config()

    def __delitem__(self, key: str) -> None:
        super().__delitem__(key)
        self._save_to_config()


class ConfigDialog(simpledialog.Dialog):
    def __init__(self, master):
        super().__init__(master, "Configuration")

    def body(self, master):
        master = ttk.Frame(master)
        master.grid()
        notebook = ttk.Notebook(master)
        notebook.grid(row=1, column=0)

        # Setup abbreviations as a tab
        abbr_tab = ttk.Frame(notebook)
        notebook.add(abbr_tab, text="Abbreviations")
        self.abbr_pane = AbbreviationPane(abbr_tab)
        self.abbr_pane.grid()


class AddAbbreviationDialog(simpledialog.Dialog):
    def __init__(self, master, expansion: str | None = None):
        self.expansion_value = expansion
        super().__init__(master, "Add Abbreviation")

    def body(self, master):
        master = ttk.Frame(master)
        master.grid()

        ttk.Label(master, text="Abbreviation").grid(row=0, column=0)
        ttk.Label(master, text="Expansion").grid(row=1, column=0)

        self.abbr = ttk.Entry(master)
        self.abbr.grid(row=0, column=1)
        self.expansion = ttk.Entry(master)
        if self.expansion_value:
            self.expansion.insert(0, self.expansion_value)
        self.expansion.grid(row=1, column=1)
        return self.abbr

    def apply(self):
        self.result = (self.abbr.get(), self.expansion.get())


# TODO: Link the abbreviations json file for editing directly.
class AbbreviationPane(ttk.Frame):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        # Set up a canvas so we can get a scroll bar.
        # TODO: Think of a better way to display these abbreviations?
        self.canvas = tk.Canvas(self, borderwidth=0, background="#ffffff")
        self.canvas.grid(row=0, column=0, sticky=tk.N + tk.S + tk.E + tk.W)
        self.scrollbar = ttk.Scrollbar(self, orient=tk.VERTICAL, command=self.canvas.yview)
        self.scrollbar.grid(row=0, column=1, sticky=tk.N + tk.S)
        self.canvas.configure(yscrollcommand=self.scrollbar.set)
        self.canvas.bind("<Configure>", lambda _: self.canvas.configure(scrollregion=self.canvas.bbox("all")))
        self.canvas.bind_all("<MouseWheel>", lambda e: self.canvas.yview_scroll(int(-1 * (e.delta / 120)), "units"))
        # enable scroll on a track pad
        self.canvas.bind_all("<Button-4>", lambda _: self.canvas.yview_scroll(-1, "units"))
        self.canvas.bind_all("<Button-5>", lambda _: self.canvas.yview_scroll(1, "units"))

        self.frame = ttk.Frame(self.canvas)
        self.frame.grid(row=0, column=0, sticky=tk.N + tk.S + tk.E + tk.W)

        self.canvas.create_window((0, 0), window=self.frame, anchor="nw")

        ttk.Label(self.frame, text="Abbr", justify=tk.LEFT).grid(row=0, column=0, sticky=tk.W)
        ttk.Label(self.frame, text="Expansion", justify=tk.LEFT).grid(row=0, column=1, sticky=tk.W)

        self.new_abbr = ttk.Entry(self.frame)
        self.new_abbr.grid(row=1, column=0)
        self.new_expansion = ttk.Entry(self.frame)
        self.new_expansion.grid(row=1, column=1)
        ttk.Button(self.frame, text="+", command=self.add_abbreviation).grid(row=1, column=2)

        self.other_rows = []

        self.draw_abbreviations()

    def _make_del_function(self, key):
        def del_function():
            abbreviations.pop(key)
            self.draw_abbreviations()

        return del_function

    def draw_abbreviations(self):
        for child in chain(*self.other_rows):
            child.destroy()
        self.other_rows = []

        for i, (abbr_key, abbr_value) in enumerate(sorted(abbreviations.items())):
            row_index = i + 2
            # TODO: Allow _editing_ abbreviations in place instead of remove and re-add.
            # Maybe by using a readonly entry and double clicking to activate it?
            abbr = ttk.Label(self.frame, text=abbr_key, justify=tk.LEFT)
            abbr.grid(row=row_index, column=0, sticky=tk.W)
            expansion = ttk.Label(self.frame, text=abbr_value, justify=tk.LEFT)
            expansion.grid(row=row_index, column=1, sticky=tk.W)
            button = ttk.Button(self.frame, text="-", command=self._make_del_function(abbr_key))
            button.grid(row=row_index, column=2)
            self.other_rows.append((abbr, expansion, button))

    def add_abbreviation(self):
        abbr = self.new_abbr.get()
        expansion = self.new_expansion.get()
        if not abbr or not expansion:
            return
        abbreviations[abbr] = expansion
        self.new_abbr.delete(0, tk.END)
        self.new_expansion.delete(0, tk.END)
        self.draw_abbreviations()


# Singleton
abbreviations = _AbbreviationStore()


# TODO: This widget pops up off-center when using multiple screes on Linux, possibly other platforms.
# See https://stackoverflow.com/questions/30312875/tkinter-winfo-screenwidth-when-used-with-dual-monitors/57866046#57866046
class AWAskAwayDialog(simpledialog.Dialog):
    def __init__(self, title: str, prompt: str, history: list[str]) -> None:
        self.prompt = prompt
        self.history = history
        self.history_index = len(history)
        super().__init__(root, title)

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
        # TODO: Wrap the Entry widget so we can reuse these in other dialogs.
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
        self.entry.bind("<Control-N>", lambda e: self.save_new_abbreviation(e, long=True))

        self.bind("<Control-comma>", self.open_config)

        return self.entry

    def save_new_abbreviation(self, event=None, *, long: bool = False):  # noqa: ARG002
        if self.entry.selection_present():
            # Get the highlighted Text
            initial_expansion = self.entry.selection_get().strip()
        elif long:
            # Get all the text before the cursor
            cursor_index = self.entry.index(tk.INSERT)
            initial_expansion = self.entry.get()[:cursor_index].strip()
        else:
            # Get the word under or before the cursor
            cursor_index = self.entry.index(tk.INSERT)
            words = re.split(r"(\W+)", self.entry.get())
            char_count = 0
            initial_expansion = ""
            for word in words:
                char_count += len(word)
                if re.fullmatch(r"\w+", word):
                    initial_expansion = word
                if char_count >= cursor_index:
                    break

        # Prompt for the abbreviation
        result = AddAbbreviationDialog(self, initial_expansion).result

        if result:
            abbr, expansion = result
            abbr = abbr.strip()
            expansion = expansion.strip()
            if not re.fullmatch(r"\w+", abbr):
                messagebox.showerror("Invalid abbreviation", "Abbreviations must be alphanumeric and without spaces.")
                return

            if existing := abbreviations.get(abbr):
                if not messagebox.askyesno(
                    "Overwrite confirmation",
                    f"That abbreviation ({abbr}) already exists as '{existing}', would you like to over write?",
                ):
                    return
            abbreviations[abbr] = expansion

        # Refocus on the main text entry
        self.entry.focus_set()

    def expand_abbreviations(self, event=None):  # noqa: ARG002
        text = self.entry.get()
        cursor_index = self.entry.index(tk.INSERT)

        # Get the potential appreviation
        abbr_regex = r"(['\w]+)\s$"  # Include ' so if you has s as an abbreviation "what's" doesn't expand to what is.
        abbr = re.search(abbr_regex, text[:cursor_index])
        if abbr and abbr.group(1) in abbreviations:
            before_index = len(re.sub(abbr_regex, "", text[:cursor_index]))
            self.entry.delete(before_index, cursor_index - 1)
            self.entry.insert(before_index, abbreviations[abbr.group(1)])

    def set_text(self, text: str):
        self.entry.delete(0, tk.END)
        self.entry.insert(0, text)

    def previous_entry(self, event=None):  # noqa: ARG002
        if not self.historiy:
            return None
        self.history_index = max(0, self.history_index - 1)
        self.set_text(self.history[self.history_index])

    def next_entry(self, event=None):  # noqa: ARG002
        if not self.historiy:
            return None
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

    def open_config(self, event=None):  # noqa: ARG002
        ConfigDialog(self)

    def cancel(self, event=None):  # noqa: ARG002
        # Call withdraw first because it is faster.
        # The process should wait on the destroy instead of the human.
        self.withdraw()
        self.destroy()
        # Wait a minute so we do not spam the user with the prompt again in like 5 seconds.
        # TODO: Make this configurable in the settings dialog.
        time.sleep(60)

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
        w = ttk.Button(box, text="Settings", command=self.open_config)
        w.pack(side=tk.LEFT, padx=5, pady=5)

        self.bind("<Return>", self.ok)
        self.bind("<Escape>", self.cancel)

        box.pack()


def ask_string(title: str, prompt: str, history: list[str]):
    d = AWAskAwayDialog(title, prompt, history)
    return d.result


if __name__ == "__main__":
    print(ask_string("Testing testing", "123", ["1", "2", "3", "4"]))  # noqa: T201
