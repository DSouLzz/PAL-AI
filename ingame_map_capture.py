import json
import threading
import time
import tkinter as tk
from tkinter import ttk, messagebox, simpledialog

import mss
from PIL import Image, ImageTk
from pynput import keyboard


def apply_ingame_map_capture(pal_ai):
    """Calibrate player position from a captured Palworld in-game map screenshot."""

    cfg = pal_ai.CONFIG.setdefault("map_overlay", {})
    cfg.setdefault("ingame_capture", {
        "enabled": True,
        "hotkey": "f8",
        "transform_known": False,
        "px1": 0.0,
        "py1": 0.0,
        "x1": 0.0,
        "y1": 0.0,
        "px2": 0.0,
        "py2": 0.0,
        "x2": 0.0,
        "y2": 0.0,
    })

    old_open_map = pal_ai.App.open_map
    old_init = pal_ai.App.__init__

    def save_config():
        pal_ai.CONFIG_PATH.write_text(
            json.dumps(pal_ai.CONFIG, indent=2, ensure_ascii=False), encoding="utf-8"
        )

    def app_init(self, root):
        self.ingame_capture_listener = None
        old_init(self, root)
        self.root.after(800, self._setup_ingame_map_hotkey)

    def _setup_ingame_map_hotkey(self):
        if self.ingame_capture_listener is not None:
            return
        wanted = str(
            pal_ai.CONFIG.get("map_overlay", {}).get("ingame_capture", {}).get("hotkey", "f8")
        ).lower()

        def on_press(key):
            try:
                name = str(key).lower().replace("key.", "")
            except Exception:
                name = ""
            if name == wanted:
                try:
                    self.root.after(0, self.capture_ingame_map_position)
                except Exception:
                    pass

        self.ingame_capture_listener = keyboard.Listener(on_press=on_press)
        self.ingame_capture_listener.daemon = True
        self.ingame_capture_listener.start()

    def capture_monitor_image(self):
        # Hide PAL-AI windows briefly so the screenshot contains the game map, not PAL-AI.
        hidden = []
        try:
            if self.root.state() != "withdrawn":
                hidden.append(self.root)
                self.root.withdraw()
        except Exception:
            pass
        try:
            if getattr(self, "map_window", None) is not None and self.map_window.winfo_exists():
                hidden.append(self.map_window)
                self.map_window.withdraw()
        except Exception:
            pass

        self.root.update_idletasks()
        self.root.update()
        time.sleep(0.35)

        with mss.mss() as sct:
            mon = sct.monitors[1]
            shot = sct.grab(mon)
            image = Image.frombytes("RGB", shot.size, shot.rgb)

        for win in hidden:
            try:
                win.deiconify()
            except Exception:
                pass
        return image

    def ask_world_coords(parent, title, hint):
        x = simpledialog.askfloat(title, f"{hint}\n\nWorld X:", parent=parent)
        if x is None:
            return None
        y = simpledialog.askfloat(title, "World Y:", parent=parent)
        if y is None:
            return None
        return float(x), float(y)

    def compute_world_from_pixel(capture, px, py):
        # Axis-aligned linear transform. Two reference points must differ in both axes.
        dxp = float(capture.get("px2", 0)) - float(capture.get("px1", 0))
        dyp = float(capture.get("py2", 0)) - float(capture.get("py1", 0))
        if abs(dxp) < 5 or abs(dyp) < 5:
            raise ValueError("Reference points are too close together. Recalibrate using points far apart on the map.")

        sx = (float(capture.get("x2", 0)) - float(capture.get("x1", 0))) / dxp
        sy = (float(capture.get("y2", 0)) - float(capture.get("y1", 0))) / dyp
        x = float(capture.get("x1", 0)) + (px - float(capture.get("px1", 0))) * sx
        y = float(capture.get("y1", 0)) + (py - float(capture.get("py1", 0))) * sy
        return x, y

    def show_capture_overlay(self, image, mode):
        overlay = tk.Toplevel(self.root)
        overlay.title("PAL-AI — In-Game Map Capture")
        overlay.attributes("-fullscreen", True)
        overlay.attributes("-topmost", True)
        overlay.configure(bg="black")

        sw = overlay.winfo_screenwidth()
        sh = overlay.winfo_screenheight()
        iw, ih = image.size
        scale = min(sw / iw, sh / ih)
        rw, rh = int(iw * scale), int(ih * scale)
        shown = image.resize((rw, rh), Image.Resampling.LANCZOS)
        photo = ImageTk.PhotoImage(shown)

        canvas = tk.Canvas(overlay, width=sw, height=sh, bg="black", highlightthickness=0, cursor="crosshair")
        canvas.pack(fill="both", expand=True)
        ox, oy = (sw-rw)//2, (sh-rh)//2
        canvas.create_image(ox, oy, image=photo, anchor="nw")
        canvas._photo = photo

        instruction = (
            "FIRST-TIME CALIBRATION: click reference point 1 on the captured Palworld map"
            if mode == "ref1" else
            "FIRST-TIME CALIBRATION: click reference point 2, far from point 1"
            if mode == "ref2" else
            "CLICK YOUR PLAYER MARKER on the captured Palworld map"
        )
        canvas.create_rectangle(0, 0, sw, 54, fill="#081018", outline="")
        canvas.create_text(sw/2, 27, text=instruction + "   •   ESC cancels", fill="white", font=("Segoe UI", 13, "bold"))

        def cancel(_event=None):
            try:
                overlay.destroy()
            except Exception:
                pass

        overlay.bind("<Escape>", cancel)

        def click(event):
            # Convert displayed pixel back to source screenshot pixel.
            px = (event.x - ox) / scale
            py = (event.y - oy) / scale
            if not (0 <= px <= iw and 0 <= py <= ih):
                return

            capture = pal_ai.CONFIG.setdefault("map_overlay", {}).setdefault("ingame_capture", {})

            if mode == "ref1":
                coords = ask_world_coords(overlay, "Reference point 1", "Enter the exact Palworld X/Y for the point you clicked.")
                if coords is None:
                    return
                capture.update({"px1": px, "py1": py, "x1": coords[0], "y1": coords[1]})
                save_config()
                overlay.destroy()
                self.root.after(150, lambda: self._continue_ingame_capture(image, "ref2"))
                return

            if mode == "ref2":
                coords = ask_world_coords(overlay, "Reference point 2", "Enter the exact Palworld X/Y for this second point.")
                if coords is None:
                    return
                capture.update({"px2": px, "py2": py, "x2": coords[0], "y2": coords[1], "transform_known": True})
                save_config()
                overlay.destroy()
                self.root.after(150, lambda: self._continue_ingame_capture(image, "player"))
                return

            try:
                x, y = compute_world_from_pixel(capture, px, py)
            except Exception as exc:
                messagebox.showerror("In-game map calibration", str(exc), parent=overlay)
                return

            pos = pal_ai.CONFIG.setdefault("map_overlay", {}).setdefault("player_position", {})
            pos.update({"known": True, "x": x, "y": y})
            save_config()
            overlay.destroy()
            self._say_ui("System", f"✓ In-game map position captured: ({x:.0f}, {y:.0f}).")
            if getattr(self, "map_window", None) is not None and self.map_window.winfo_exists():
                self.refresh_map()

        canvas.bind("<Button-1>", click)
        overlay.focus_force()

    def _continue_ingame_capture(self, image, mode):
        self.show_capture_overlay(image, mode)

    def capture_ingame_map_position(self):
        try:
            capture = pal_ai.CONFIG.setdefault("map_overlay", {}).setdefault("ingame_capture", {})
            self.set_status("Capturing in-game map...")
            image = capture_monitor_image(self)
            mode = "player" if capture.get("transform_known", False) else "ref1"
            self.show_capture_overlay(image, mode)
            self.set_status("Ready")
        except Exception as exc:
            messagebox.showerror("In-game map capture", str(exc))
            self.set_status("Ready")

    def reset_ingame_map_calibration(self):
        capture = pal_ai.CONFIG.setdefault("map_overlay", {}).setdefault("ingame_capture", {})
        capture["transform_known"] = False
        save_config()
        self._say_ui("System", "In-game map calibration reset. Press F8 with the Palworld map open to recalibrate.")

    def open_map(self):
        old_open_map(self)
        if self.map_window is None or not self.map_window.winfo_exists():
            return

        strip = tk.Frame(self.map_window, bg="#0b1118")
        strip.pack(fill="x", side="bottom", padx=10, pady=(0, 6))
        ttk.Button(
            strip,
            text="🎯 Capture Position from In-Game Map (F8)",
            command=self.capture_ingame_map_position,
        ).pack(side="left", padx=(0, 8))
        ttk.Button(
            strip,
            text="Reset In-Game Calibration",
            command=self.reset_ingame_map_calibration,
        ).pack(side="left")

    pal_ai.App.__init__ = app_init
    pal_ai.App._setup_ingame_map_hotkey = _setup_ingame_map_hotkey
    pal_ai.App.capture_ingame_map_position = capture_ingame_map_position
    pal_ai.App._continue_ingame_capture = _continue_ingame_capture
    pal_ai.App.show_capture_overlay = show_capture_overlay
    pal_ai.App.reset_ingame_map_calibration = reset_ingame_map_calibration
    pal_ai.App.open_map = open_map
