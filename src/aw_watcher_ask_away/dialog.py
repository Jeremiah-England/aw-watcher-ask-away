import tkinter as tk
from tkinter import simpledialog


def open_link(link: str):
    import webbrowser

    webbrowser.open(link)


# TODO: This widget pops up off-center when using multiple screes on Linux, possibly other platforms.
# See https://stackoverflow.com/questions/30312875/tkinter-winfo-screenwidth-when-used-with-dual-monitors/57866046#57866046
class AWAskAwayDialog(simpledialog.Dialog):
    def __init__(self, title: str, prompt: str) -> None:
        self.prompt = prompt
        super().__init__(None, title)

    def body(self, master):
        # Prompt
        # Copied from the simpledialog source code.
        w = tk.Label(master, text=self.prompt, justify=tk.LEFT)
        w.grid(row=0, padx=5, sticky=tk.W)

        # Input field
        self.entry = tk.Entry(master, name="entry", width=40)
        self.entry.grid(row=1, padx=5, sticky=tk.W + tk.E)

        # README link
        doc_label = tk.Label(master, text="Documentation", fg="blue", cursor="hand2", justify=tk.RIGHT)
        doc_label.grid(row=0, padx=5, sticky=tk.W, column=1)
        doc_label.bind("<Button-1>", self.open_readme)

        # Issue link
        issue_label = tk.Label(master, text="Report an issue", fg="blue", cursor="hand2", justify=tk.RIGHT)
        issue_label.grid(row=1, padx=5, sticky=tk.W, column=1)
        issue_label.bind("<Button-1>", self.open_an_issue)

        # Add some remove-word shortcuts
        self.bind("<Control-BackSpace>", self.remove_word)
        self.bind("<Control-w>", self.remove_word)
        self.bind("<Control-u>", self.remove_to_start)
        self.bind("<Control-o>", self.open_web_interface)
        # TODO: Bind the up arrow to the previous entry.

        return self.entry

    def open_an_issue(self, event=None):  # noqa: ARG002
        open_link("https://github.com/Jeremiah-England/aw-watcher-ask-away/issues/new")

    def open_readme(self, event=None):  # noqa: ARG002
        open_link("https://github.com/Jeremiah-England/aw-watcher-ask-away#aw-watcher-ask-away")

    def open_web_interface(self, event=None):  # noqa: ARG002
        open_link("http://localhost:5600/#/timeline")

    def remove_word(self, event=None):  # noqa: ARG002
        # Get the current entry content
        text = self.entry.get()

        # Split into words and remove the last word
        words = text.split()
        if words:
            words.pop()

        # Update the entry content
        self.entry.delete(0, tk.END)
        self.entry.insert(0, " ".join(words) + " ")

    def remove_to_start(self, event=None):  # noqa: ARG002
        # TODO: Tehcnically should only remove to the start of the line from where the cursor is.
        self.entry.delete(0, tk.END)
        self.entry.insert(0, "")

    # If you want to retrieve the entered text when the dialog closes:
    def apply(self):
        self.result = self.entry.get()


def ask_string(title: str, prompt: str):
    d = AWAskAwayDialog(title, prompt)
    return d.result


if __name__ == "__main__":
    print(ask_string("Testing testing", "123"))  # noqa: T201
