import logging
import time
import tkinter as tk
from tkinter import simpledialog, ttk

logger = logging.getLogger(__name__)


def open_link(link: str):
    import webbrowser

    webbrowser.open(link)


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

        return self.entry

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
        # Split into words and remove the last word
        words = self.entry.get().split()
        if words:
            words.pop()

        # Update the entry content
        self.entry.delete(0, tk.END)
        if words:
            self.entry.insert(0, " ".join(words) + " ")

    def remove_to_start(self, event=None):  # noqa: ARG002
        # TODO: Tehcnically should only remove to the start of the line from where the cursor is.
        self.entry.delete(0, tk.END)
        self.entry.insert(0, "")

    # If you want to retrieve the entered text when the dialog closes:
    def apply(self):
        self.result = self.entry.get()

    def snooze(self):
        self.cancel()
        logging.log(logging.INFO, "Snoozing for 1 hour.")
        time.sleep(60 * 60)

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
        w = ttk.Button(box, text="Snooze (1h)", command=self.snooze)
        w.pack(side=tk.LEFT, padx=5, pady=5)

        self.bind("<Return>", self.ok)
        self.bind("<Escape>", self.cancel)

        box.pack()


def ask_string(title: str, prompt: str, history: list[str]):
    d = AWAskAwayDialog(title, prompt, history)
    return d.result


if __name__ == "__main__":
    print(ask_string("Testing testing", "123", ["1", "2", "3", "4"]))  # noqa: T201
