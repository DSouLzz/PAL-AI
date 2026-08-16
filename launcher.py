import threading
import tkinter as tk
from tkinter import messagebox

import pal_ai
import updater
from voice_fix import reliable_speak
from map_overlay import apply_map_overlay
from map_precision import apply_map_precision
from performance_patch import apply_performance_patch
from online_research import apply_online_research
from activity_indicator import apply_activity_indicator
from map_pin_fix import apply_map_pin_fix
from map_calibration import apply_map_calibration
from ingame_map_capture import apply_ingame_map_capture
from detailed_map_background import apply_detailed_map_background
from server_sync import apply_server_sync

# Apply runtime patches before the app starts.
pal_ai.Voice.speak = reliable_speak
apply_map_overlay(pal_ai)
apply_map_precision(pal_ai)
apply_performance_patch(pal_ai)
apply_online_research(pal_ai)
apply_activity_indicator(pal_ai)
apply_map_pin_fix(pal_ai)
apply_map_calibration(pal_ai)
apply_ingame_map_capture(pal_ai)
apply_detailed_map_background(pal_ai)
apply_server_sync(pal_ai)


def safe_check_updates(self, silent=False):
    """Python 3.14-safe update checker."""
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


pal_ai.App.check_updates = safe_check_updates


if __name__ == "__main__":
    root = tk.Tk()
    app = pal_ai.App(root)
    root.mainloop()
