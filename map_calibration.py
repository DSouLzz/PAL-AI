import json
import tkinter as tk
from tkinter import ttk, messagebox


def apply_map_calibration(pal_ai):
    """Calibrate PAL-AI by clicking the player's position directly on the companion map."""

    cfg = pal_ai.CONFIG.setdefault("map_overlay", {})
    bounds = cfg.setdefault("world_bounds", {})

    # Correct older oversized bounds. PAL-AI's companion map is centered around 0,0.
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

    def canvas_to_world(self, px, py, w, h):
        min_x, max_x, min_y, max_y = self.map_bounds()
        x = min_x + (float(px) / max(1.0, float(w))) * (max_x - min_x)
        y = max_y - (float(py) / max(1.0, float(h))) * (max_y - min_y)
        return x, y

    def save_clicked_position(self, event):
        if not getattr(self, "_map_calibration_armed", False):
            return

        canvas = getattr(self.map_window, "_map_canvas", None)
        if canvas is None:
            return

        w = max(100, canvas.winfo_width())
        h = max(100, canvas.winfo_height())
        x, y = self.canvas_to_world(event.x, event.y, w, h)

        pos = pal_ai.CONFIG.setdefault("map_overlay", {}).setdefault("player_position", {})
        pos.update({"known": True, "x": x, "y": y})
        pal_ai.CONFIG_PATH.write_text(
            json.dumps(pal_ai.CONFIG, indent=2, ensure_ascii=False), encoding="utf-8"
        )

        self._map_calibration_armed = False
        try:
            canvas.configure(cursor="")
            canvas.unbind("<Button-1>", getattr(self, "_map_calibration_bind_id", None))
        except Exception:
            pass

        label = getattr(self, "map_calibration_hint_label", None)
        if label is not None and label.winfo_exists():
            label.configure(text=f"✓ Position set by map click: {x:.0f}, {y:.0f}", fg="#7ee7b7")

        self._say_ui("System", f"✓ Map calibrated by click. Your position is ({x:.0f}, {y:.0f}).")
        self.refresh_map()

    def calibration_dialog(self):
        """Arm one-click calibration instead of asking the player to type coordinates."""
        if self.map_window is None or not self.map_window.winfo_exists():
            self.open_map()
            return

        canvas = getattr(self.map_window, "_map_canvas", None)
        if canvas is None:
            return

        self._map_calibration_armed = True
        canvas.configure(cursor="crosshair")

        # Bind a temporary calibration click. add='+' keeps existing pin click handlers intact.
        self._map_calibration_bind_id = canvas.bind(
            "<Button-1>", self.save_clicked_position, add="+"
        )

        label = getattr(self, "map_calibration_hint_label", None)
        if label is not None and label.winfo_exists():
            label.configure(
                text="CALIBRATION ACTIVE — click your real position on the map",
                fg="#ffd166",
            )

        messagebox.showinfo(
            "Click to calibrate",
            "Calibration is active.\n\n"
            "Look at your Palworld in-game map, find where your player is, then click the matching spot on the PAL-AI map.\n\n"
            "PAL-AI will save that clicked position as YOU ARE HERE.",
            parent=self.map_window,
        )

    def cancel_calibration(self):
        self._map_calibration_armed = False
        canvas = None
        if getattr(self, "map_window", None) is not None and self.map_window.winfo_exists():
            canvas = getattr(self.map_window, "_map_canvas", None)
        if canvas is not None:
            try:
                canvas.configure(cursor="")
                canvas.unbind("<Button-1>", getattr(self, "_map_calibration_bind_id", None))
            except Exception:
                pass
        label = getattr(self, "map_calibration_hint_label", None)
        if label is not None and label.winfo_exists():
            label.configure(text="Click Calibrate, then click your position on the map", fg="#8fa0ad")

    def clear_player_position(self):
        self.cancel_calibration()
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

        self._map_calibration_armed = False
        self._map_calibration_bind_id = None

        strip = tk.Frame(self.map_window, bg="#0b1118")
        strip.pack(fill="x", side="bottom", padx=10, pady=(0, 8))
        ttk.Button(strip, text="◎ Calibrate — Click My Position", command=self.calibration_dialog).pack(side="left", padx=(0, 8))
        ttk.Button(strip, text="Cancel Calibration", command=self.cancel_calibration).pack(side="left", padx=(0, 8))
        ttk.Button(strip, text="Clear My Position", command=self.clear_player_position).pack(side="left")

        self.map_calibration_hint_label = tk.Label(
            strip,
            text="Click Calibrate, then click your position on the map",
            fg="#8fa0ad",
            bg="#0b1118",
            font=("Segoe UI", 8),
        )
        self.map_calibration_hint_label.pack(side="left", padx=14)

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

        canvas.create_oval(
            px-17, py-17, px+17, py+17,
            fill="#00d084", outline="white", width=3,
            tags=("player_position",)
        )
        canvas.create_text(
            px, py, text="YOU", fill="#07120d",
            font=("Segoe UI", 7, "bold"), tags=("player_position",)
        )
        canvas.create_text(
            px+21, py-19, text=f"YOU ARE HERE  ({x:.0f}, {y:.0f})",
            fill="#7fffc0", anchor="sw",
            font=("Segoe UI", 9, "bold"), tags=("player_position",)
        )

        label = getattr(self, "map_player_position_label", None)
        if label is not None and label.winfo_exists():
            label.configure(text=f"Your position: {x:.0f}, {y:.0f}")

    # Give the local model access to the clicked/calibrated position.
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

    pal_ai.App.canvas_to_world = canvas_to_world
    pal_ai.App.save_clicked_position = save_clicked_position
    pal_ai.App.calibration_dialog = calibration_dialog
    pal_ai.App.cancel_calibration = cancel_calibration
    pal_ai.App.clear_player_position = clear_player_position
    pal_ai.App.open_map = open_map
    pal_ai.App.refresh_map = refresh_map
    pal_ai.App.ask = ask
