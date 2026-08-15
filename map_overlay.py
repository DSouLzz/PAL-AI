import re
import tkinter as tk
from tkinter import ttk, messagebox


def apply_map_overlay(pal_ai):
    """Add a safe PAL-AI companion map without modifying Palworld itself."""

    if "MAP OVERLAY:" not in pal_ai.SYSTEM_PROMPT:
        pal_ai.SYSTEM_PROMPT += """

MAP OVERLAY:
When you recommend a specific place that would genuinely help the player navigate,
you may append ONE hidden marker token at the very end of your answer:
[[MAP_PIN|short name|x|y|short note]]
x and y must be normalized positions from 0 to 100, where x=0 is west/left,
x=100 is east/right, y=0 is north/top, and y=100 is south/bottom.
Only create a pin when you have a reasonable basis for the location. Never invent
coordinates when uncertain. The application removes the token before display/speech.
"""

    old_db_init = pal_ai.MemoryDB.__init__

    def db_init(self, path):
        old_db_init(self, path)
        self.conn.execute("""CREATE TABLE IF NOT EXISTS map_pins(
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            ts TEXT NOT NULL,
            name TEXT NOT NULL,
            x REAL NOT NULL,
            y REAL NOT NULL,
            note TEXT DEFAULT ''
        )""")
        self.conn.commit()

    def add_map_pin(self, name, x, y, note=""):
        self.conn.execute(
            "INSERT INTO map_pins(ts,name,x,y,note) VALUES(datetime('now'),?,?,?,?)",
            (name, float(x), float(y), note),
        )
        self.conn.commit()

    def list_map_pins(self):
        return self.conn.execute(
            "SELECT id,name,x,y,note FROM map_pins ORDER BY id ASC"
        ).fetchall()

    def clear_map_pins(self):
        self.conn.execute("DELETE FROM map_pins")
        self.conn.commit()

    pal_ai.MemoryDB.__init__ = db_init
    pal_ai.MemoryDB.add_map_pin = add_map_pin
    pal_ai.MemoryDB.list_map_pins = list_map_pins
    pal_ai.MemoryDB.clear_map_pins = clear_map_pins

    old_app_init = pal_ai.App.__init__
    old_build = pal_ai.App._build
    old_finish_answer = pal_ai.App._finish_answer

    def app_init(self, root):
        self.map_window = None
        old_app_init(self, root)

    def build(self):
        old_build(self)
        row = ttk.Frame(self.root, padding=(8, 0, 8, 6))
        row.pack(fill="x")
        ttk.Button(row, text="🗺 Map", command=self.toggle_map).pack(side="left")
        ttk.Label(row, text="Safe PAL-AI companion map — no game modification").pack(side="left", padx=8)

    def toggle_map(self):
        if self.map_window is not None and self.map_window.winfo_exists():
            self.map_window.destroy()
            self.map_window = None
        else:
            self.open_map()

    def open_map(self):
        cfg = pal_ai.CONFIG.get("map_overlay", {})
        win = tk.Toplevel(self.root)
        self.map_window = win
        win.title("PAL-AI Companion Map")
        win.geometry(f"{int(cfg.get('width', 620))}x{int(cfg.get('height', 620))}")
        try:
            win.attributes("-topmost", bool(cfg.get("always_on_top", True)))
            win.attributes("-alpha", float(cfg.get("opacity", 0.92)))
        except Exception:
            pass

        bar = ttk.Frame(win, padding=6)
        bar.pack(fill="x")
        ttk.Label(bar, text="PAL-AI Companion Map").pack(side="left")
        ttk.Button(bar, text="Refresh", command=self.refresh_map).pack(side="right")
        ttk.Button(bar, text="Clear pins", command=self.clear_map_pins_ui).pack(side="right", padx=6)

        canvas = tk.Canvas(win, bg="#171717", highlightthickness=0)
        canvas.pack(fill="both", expand=True, padx=6, pady=(0, 6))
        win._map_canvas = canvas
        canvas.bind("<Configure>", lambda _event: self.refresh_map())
        self.refresh_map()

    def refresh_map(self):
        if self.map_window is None or not self.map_window.winfo_exists():
            return
        canvas = getattr(self.map_window, "_map_canvas", None)
        if canvas is None:
            return
        canvas.delete("all")
        w = max(100, canvas.winfo_width())
        h = max(100, canvas.winfo_height())

        for i in range(11):
            x = i * w / 10
            y = i * h / 10
            canvas.create_line(x, 0, x, h, fill="#303030")
            canvas.create_line(0, y, w, y, fill="#303030")

        canvas.create_text(w/2, 18, text="NORTH", fill="white")
        canvas.create_text(w/2, h-18, text="SOUTH", fill="white")
        canvas.create_text(24, h/2, text="WEST", fill="white", angle=90)
        canvas.create_text(w-24, h/2, text="EAST", fill="white", angle=90)

        for number, (_pin_id, name, x, y, note) in enumerate(self.db.list_map_pins(), start=1):
            px = max(0, min(100, float(x))) / 100 * w
            py = max(0, min(100, float(y))) / 100 * h
            canvas.create_oval(px-9, py-9, px+9, py+9, fill="white", outline="black", width=2)
            canvas.create_text(px, py, text=str(number), fill="black", font=("Segoe UI", 8, "bold"))
            canvas.create_text(px+12, py-12, text=name, fill="white", anchor="sw", font=("Segoe UI", 9, "bold"))
            if note:
                canvas.create_text(px+12, py+2, text=note[:48], fill="#cccccc", anchor="nw", font=("Segoe UI", 8))

    def clear_map_pins_ui(self):
        if messagebox.askyesno("PAL-AI map", "Clear all saved PAL-AI map pins?"):
            self.db.clear_map_pins()
            self.refresh_map()

    def parse_map_pin(self, answer):
        pattern = r"\[\[MAP_PIN\|([^|\]]{1,60})\|([0-9]+(?:\.[0-9]+)?)\|([0-9]+(?:\.[0-9]+)?)\|([^\]]{0,120})\]\]"
        match = re.search(pattern, answer)
        if not match:
            return answer, None
        name = match.group(1).strip()
        x = float(match.group(2))
        y = float(match.group(3))
        note = match.group(4).strip()
        clean = re.sub(pattern, "", answer).strip()
        if not (0 <= x <= 100 and 0 <= y <= 100):
            return clean, None
        self.db.add_map_pin(name, x, y, note)
        return clean, (name, x, y, note)

    def finish_answer(self, answer):
        clean, pin = self.parse_map_pin(answer)
        old_finish_answer(self, clean)
        if pin:
            name, x, y, _note = pin
            self._say_ui("System", f"Map pin added: {name} ({x:.0f}, {y:.0f})")
            if pal_ai.CONFIG.get("map_overlay", {}).get("auto_open_on_new_pin", True):
                if self.map_window is None or not self.map_window.winfo_exists():
                    self.open_map()
                else:
                    self.refresh_map()

    pal_ai.App.__init__ = app_init
    pal_ai.App._build = build
    pal_ai.App.toggle_map = toggle_map
    pal_ai.App.open_map = open_map
    pal_ai.App.refresh_map = refresh_map
    pal_ai.App.clear_map_pins_ui = clear_map_pins_ui
    pal_ai.App.parse_map_pin = parse_map_pin
    pal_ai.App._finish_answer = finish_answer
