import json
import tkinter as tk
from tkinter import ttk, messagebox


def apply_map_calibration(pal_ai):
    """Calibrate PAL-AI map to Palworld's in-game coordinate system and track player position."""

    cfg = pal_ai.CONFIG.setdefault("map_overlay", {})
    bounds = cfg.setdefault("world_bounds", {})

    # Correct legacy oversized bounds from earlier PAL-AI builds.
    old_values = (
        float(bounds.get("min_x", -1000)),
        float(bounds.get("max_x", 1000)),
        float(bounds.get("min_y", -1000)),
        float(bounds.get("max_y", 1000)),
    )
    if old_values[0] < -1200 or old_values[1] > 1200 or old_values[2] < -1200 or old_values[3] > 1200:
        bounds.update({"min_x": -1000.0, "max_x": 1000.0, "min_y": -1000.0, "max_y": 1000.0})

    cfg.setdefault("player_position", {"known": False, "x": 0.0, "y": 0.0})

    try:
        pal_ai.CONFIG_PATH.write_text(
            json.dumps(pal_ai.CONFIG, indent=2, ensure_ascii=False), encoding="utf-8"
        )
    except Exception:
        pass

    old_open_map = pal_ai.App.open_map
    old_refresh_map = pal_ai.App.refresh_map

    def calibration_dialog(self):
        win = tk.Toplevel(self.root)
        win.title("Calibrate PAL-AI Map")
        win.geometry("430x300")
        win.resizable(False, False)

        ttk.Label(win, text="Calibrate your current Palworld position", font=("Segoe UI", 12, "bold")).pack(padx=14, pady=(14, 6))
        ttk.Label(
            win,
            text=(
                "1. Open the in-game map in Palworld.\n"
                "2. Move the map cursor onto your player marker.\n"
                "3. Read the X/Y coordinates shown by Palworld.\n"
                "4. Enter those exact values below.\n\n"
                "Example: X = -12   Y = -285"
            ),
            justify="left",
            wraplength=390,
        ).pack(anchor="w", padx=18, pady=6)

        form = ttk.Frame(win)
        form.pack(fill="x", padx=18, pady=10)
        ttk.Label(form, text="X:").grid(row=0, column=0, sticky="w", padx=(0, 6), pady=6)
        x_entry = ttk.Entry(form, width=18)
        x_entry.grid(row=0, column=1, sticky="w", pady=6)
        ttk.Label(form, text="Y:").grid(row=1, column=0, sticky="w", padx=(0, 6), pady=6)
        y_entry = ttk.Entry(form, width=18)
        y_entry.grid(row=1, column=1, sticky="w", pady=6)

        current = pal_ai.CONFIG.get("map_overlay", {}).get("player_position", {})
        if current.get("known"):
            x_entry.insert(0, str(current.get("x", 0)))
            y_entry.insert(0, str(current.get("y", 0)))

        def save_position():
            try:
                x = float(x_entry.get().strip().replace(",", "."))
                y = float(y_entry.get().strip().replace(",", "."))
            except ValueError:
                messagebox.showerror("Calibration", "Enter valid numeric X and Y coordinates.", parent=win)
                return

            if not (-1000 <= x <= 1000 and -1000 <= y <= 1000):
                if not messagebox.askyesno(
                    "Calibration",
                    "These coordinates are outside the usual in-game -1000 to +1000 map range. Save anyway?",
                    parent=win,
                ):
                    return

            pos = pal_ai.CONFIG.setdefault("map_overlay", {}).setdefault("player_position", {})
            pos.update({"known": True, "x": x, "y": y})
            pal_ai.CONFIG_PATH.write_text(
                json.dumps(pal_ai.CONFIG, indent=2, ensure_ascii=False), encoding="utf-8"
            )
            self._say_ui("System", f"✓ Map calibrated. Your current position is ({x:.0f}, {y:.0f}).")
            if getattr(self, "map_window", None) is not None and self.map_window.winfo_exists():
                self.refresh_map()
            win.destroy()

        ttk.Button(win, text="Save / Calibrate", command=save_position).pack(pady=10)

    def clear_player_position(self):
        pos = pal_ai.CONFIG.setdefault("map_overlay", {}).setdefault("player_position", {})
        pos.update({"known": False, "x": 0.0, "y": 0.0})
        pal_ai.CONFIG_PATH.write_text(
            json.dumps(pal_ai.CONFIG, indent=2, ensure_ascii=False), encoding="utf-8"
        )
        self._say_ui("System", "Player map position cleared.")
        if getattr(self, "map_window", None) is not None and self.map_window.winfo_exists():
            self.refresh_map()

    def open_map(self):
        old_open_map(self)
        if self.map_window is None or not self.map_window.winfo_exists():
            return

        strip = tk.Frame(self.map_window, bg="#0b1118")
        strip.pack(fill="x", side="bottom", padx=10, pady=(0, 8))
        ttk.Button(strip, text="◎ Calibrate / Set My Position", command=self.calibration_dialog).pack(side="left", padx=(0, 8))
        ttk.Button(strip, text="Clear My Position", command=self.clear_player_position).pack(side="left")

        pos = pal_ai.CONFIG.get("map_overlay", {}).get("player_position", {})
        text = "Position: not calibrated"
        if pos.get("known"):
            text = f"Your position: {float(pos.get('x',0)):.0f}, {float(pos.get('y',0)):.0f}"
        self.map_player_position_label = tk.Label(
            strip, text=text, fg="#7ee7b7", bg="#0b1118", font=("Segoe UI", 9, "bold")
        )
        self.map_player_position_label.pack(side="right")

    def refresh_map(self):
        old_refresh_map(self)
        if self.map_window is None or not self.map_window.winfo_exists():
            return
        canvas = getattr(self.map_window, "_map_canvas", None)
        if canvas is None:
            return

        pos = pal_ai.CONFIG.get("map_overlay", {}).get("player_position", {})
        if not pos.get("known"):
            label = getattr(self, "map_player_position_label", None)
            if label is not None and label.winfo_exists():
                label.configure(text="Position: not calibrated")
            return

        x = float(pos.get("x", 0))
        y = float(pos.get("y", 0))
        w = max(100, canvas.winfo_width())
        h = max(100, canvas.winfo_height())
        px, py = self.world_to_canvas(x, y, w, h)

        # High-visibility player marker layered above pins and map art.
        canvas.create_oval(px-16, py-16, px+16, py+16, fill="#00d084", outline="white", width=3, tags=("player_position",))
        canvas.create_text(px, py, text="YOU", fill="#07120d", font=("Segoe UI", 7, "bold"), tags=("player_position",))
        canvas.create_text(
            px+20, py-18, text=f"YOU ARE HERE  ({x:.0f}, {y:.0f})",
            fill="#7fffc0", anchor="sw", font=("Segoe UI", 9, "bold"), tags=("player_position",)
        )

        label = getattr(self, "map_player_position_label", None)
        if label is not None and label.winfo_exists():
            label.configure(text=f"Your position: {x:.0f}, {y:.0f}")

    # Give the local model access to current calibrated position for relative recommendations.
    old_ask = pal_ai.App.ask

    def ask(self, text, *args, **kwargs):
        pos = pal_ai.CONFIG.get("map_overlay", {}).get("player_position", {})
        if pos.get("known"):
            text = (
                str(text)
                + f"\n\nPLAYER CURRENT MAP POSITION: X={float(pos.get('x',0)):.0f}, Y={float(pos.get('y',0)):.0f}. "
                  "Use this when estimating direction or distance."
            )
        return old_ask(self, text, *args, **kwargs)

    pal_ai.App.calibration_dialog = calibration_dialog
    pal_ai.App.clear_player_position = clear_player_position
    pal_ai.App.open_map = open_map
    pal_ai.App.refresh_map = refresh_map
    pal_ai.App.ask = ask
