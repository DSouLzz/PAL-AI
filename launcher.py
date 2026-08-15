import threading
import tkinter as tk
from tkinter import messagebox

import pal_ai
import updater
from voice_fix import reliable_speak

# Apply the reliable Windows voice implementation before the app starts.
pal_ai.Voice.speak = reliable_speak


def safe_check_updates(self, silent=False):
    """Python 3.14-safe update checker.

    Exception variables from an except block are cleared when that block exits.
    Therefore any Tkinter callback scheduled for later must capture plain text now,
    rather than closing over `e`.
    """
    def worker():
        try:
            result = updater.check_for_update()
            status = result.get("status")

            if status == "no_release":
                if not silent:
                    self.root.after(0, lambda: messagebox.showinfo(
                        "Updates", "No GitHub Release has been published yet."
                    ))
                return

            if status == "disabled":
                return

            if status == "up_to_date":
                current = result.get("current", "?")
                if not silent:
                    self.root.after(0, lambda current=current: messagebox.showinfo(
                        "Updates", f"PAL-AI {current} is up to date."
                    ))
                return

            if status == "update_available":
                def ask(result=result):
                    latest = result.get("latest", "?")
                    notes = result.get("notes", "")
                    if messagebox.askyesno(
                        "PAL-AI update",
                        f"PAL-AI {latest} is available.\n\n{notes}\n\n"
                        "Apply the update now?\n"
                        "The ZIP will be verified with SHA-256 before installation."
                    ):
                        try:
                            updater.prepare_update(
                                result["download_url"],
                                result["latest"],
                                result["sha256"],
                            )
                            messagebox.showinfo(
                                "PAL-AI update",
                                "Update prepared. PAL-AI will close and restart automatically."
                            )
                            self.root.after(300, self.root.destroy)
                        except Exception as exc:
                            messagebox.showerror("Update failed", str(exc))
                self.root.after(0, ask)
                return

        except Exception as exc:
            error_text = str(exc)
            if not silent:
                self.root.after(
                    0,
                    lambda error_text=error_text: messagebox.showerror(
                        "Update check failed", error_text
                    )
                )

    threading.Thread(target=worker, daemon=True).start()


# Patch the buggy v0.7 checker without rewriting the user's whole app file.
pal_ai.App.check_updates = safe_check_updates


if __name__ == "__main__":
    root = tk.Tk()
    app = pal_ai.App(root)
    root.mainloop()
