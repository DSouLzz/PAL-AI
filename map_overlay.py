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
        self.map_zoom = 1.0
        self.map_pin_list_frame = None
        self.map_suggestion_label = None
        old_app_init(self, root)

    def build(self):
        old_build(self)
        row = ttk.Frame(self.root, padding=(8, 0, 8, 6))
        row.pack(fill="x")
        ttk.Button(row, text="🗺 Map", command=self.toggle_map).pack(side="left")
        ttk.Label(row, text="PAL-AI tactical companion map").pack(side="left", padx=8)

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
        win.title("PAL-AI Map")
        win.geometry(f"{int(cfg.get('width', 1180))}x{int(cfg.get('height', 760))}")
        win.minsize(900, 600)
        win.configure(bg="#0b1118")
        try:
            win.attributes("-topmost", bool(cfg.get("always_on_top", True)))
            win.attributes("-alpha", float(cfg.get("opacity", 0.98)))
        except Exception:
            pass

        header = tk.Frame(win, bg="#0b1118", height=58)
        header.pack(fill="x")
        header.pack_propagate(False)
        tk.Label(header, text="◈ PAL-AI", fg="#f3f6f9", bg="#0b1118", font=("Segoe UI", 18, "bold")).pack(side="left", padx=(18, 8))
        tk.Label(header, text="MAP", fg="#24d17e", bg="#0b1118", font=("Segoe UI", 9, "bold")).pack(side="left")
        tk.Label(header, text="● Online", fg="#39d98a", bg="#111a23", font=("Segoe UI", 9, "bold"), padx=10, pady=6).pack(side="left", padx=18)
        ttk.Button(header, text="Close map", command=self.toggle_map).pack(side="right", padx=16, pady=12)

        body = tk.Frame(win, bg="#0b1118")
        body.pack(fill="both", expand=True, padx=10, pady=(0, 10))

        left = tk.Frame(body, bg="#111a23", width=250)
        left.pack(side="left", fill="y", padx=(0, 8))
        left.pack_propagate(False)
        tk.Label(left, text="PAL-AI Companion", fg="#f2f5f7", bg="#111a23", font=("Segoe UI", 12, "bold")).pack(anchor="w", padx=14, pady=(14, 2))
        tk.Label(left, text="Ready to help", fg="#90a4b4", bg="#111a23", font=("Segoe UI", 9)).pack(anchor="w", padx=14, pady=(0, 14))

        box = tk.Frame(left, bg="#16222d")
        box.pack(fill="x", padx=12, pady=6)
        tk.Label(box, text="Current suggestion", fg="#8bd9ff", bg="#16222d", font=("Segoe UI", 9, "bold")).pack(anchor="w", padx=12, pady=(10, 4))
        self.map_suggestion_label = tk.Label(box, text="Ask PAL-AI where to go next.\nSuggested locations appear as numbered pins.", fg="#e6edf3", bg="#16222d", justify="left", wraplength=205, font=("Segoe UI", 9))
        self.map_suggestion_label.pack(anchor="w", padx=12, pady=(0, 12))

        tk.Label(left, text="Map controls", fg="#c5d0d8", bg="#111a23", font=("Segoe UI", 10, "bold")).pack(anchor="w", padx=14, pady=(18, 8))
        controls = tk.Frame(left, bg="#111a23")
        controls.pack(fill="x", padx=12)
        ttk.Button(controls, text="Zoom +", command=lambda: self.change_map_zoom(0.15)).pack(fill="x", pady=3)
        ttk.Button(controls, text="Zoom -", command=lambda: self.change_map_zoom(-0.15)).pack(fill="x", pady=3)
        ttk.Button(controls, text="Reset zoom", command=self.reset_map_zoom).pack(fill="x", pady=3)
        ttk.Button(controls, text="Refresh", command=self.refresh_map).pack(fill="x", pady=3)
        tk.Label(left, text="Safe overlay", fg="#52d39b", bg="#111a23", font=("Segoe UI", 9, "bold")).pack(anchor="w", padx=14, pady=(22, 2))
        tk.Label(left, text="External PAL-AI map.\nNo game modification.", fg="#8fa0ad", bg="#111a23", justify="left", font=("Segoe UI", 8)).pack(anchor="w", padx=14)

        center = tk.Frame(body, bg="#111a23")
        center.pack(side="left", fill="both", expand=True)
        map_header = tk.Frame(center, bg="#111a23", height=42)
        map_header.pack(fill="x")
        map_header.pack_propagate(False)
        tk.Label(map_header, text="PAL Map", fg="#f1f5f8", bg="#111a23", font=("Segoe UI", 12, "bold")).pack(side="left", padx=14, pady=10)
        tk.Label(map_header, text="PAL-AI suggested locations", fg="#7f96a8", bg="#111a23", font=("Segoe UI", 8)).pack(side="right", padx=14)
        canvas = tk.Canvas(center, bg="#123844", highlightthickness=0)
        canvas.pack(fill="both", expand=True, padx=8, pady=(0, 8))
        win._map_canvas = canvas
        canvas.bind("<Configure>", lambda _event: self.refresh_map())

        right = tk.Frame(body, bg="#111a23", width=250)
        right.pack(side="left", fill="y", padx=(8, 0))
        right.pack_propagate(False)
        tk.Label(right, text="Saved Pins", fg="#f2f5f7", bg="#111a23", font=("Segoe UI", 12, "bold")).pack(anchor="w", padx=14, pady=(14, 8))
        self.map_pin_list_frame = tk.Frame(right, bg="#111a23")
        self.map_pin_list_frame.pack(fill="both", expand=True, padx=10)
        bottom = tk.Frame(right, bg="#111a23")
        bottom.pack(fill="x", padx=10, pady=10)
        ttk.Button(bottom, text="Clear all pins", command=self.clear_map_pins_ui).pack(fill="x")
        self.refresh_map()

    def change_map_zoom(self, delta):
        self.map_zoom = max(0.75, min(1.8, self.map_zoom + delta))
        self.refresh_map()

    def reset_map_zoom(self):
        self.map_zoom = 1.0
        self.refresh_map()

    def draw_world_map(self, canvas, w, h):
        canvas.create_rectangle(0, 0, w, h, fill="#123844", outline="")

        def poly(points, fill, outline="#aeb29c", width=2):
            scaled = []
            for x, y in points:
                scaled.extend((x / 100 * w, y / 100 * h))
            canvas.create_polygon(*scaled, fill=fill, outline=outline, width=width, smooth=True)

        poly([(8,8),(23,5),(33,10),(40,18),(38,28),(30,35),(22,38),(14,33),(8,24)], "#d9e3e4", "#edf6f6", 3)
        poly([(20,31),(31,28),(39,35),(37,45),(29,50),(22,45)], "#56764b")
        poly([(57,7),(71,5),(80,11),(84,23),(79,33),(72,39),(63,35),(58,25)], "#b9a58f", "#d5c6b5", 3)
        poly([(77,28),(90,25),(94,34),(89,45),(80,44),(73,38)], "#5f744b")
        poly([(38,39),(49,34),(58,39),(66,48),(63,61),(54,70),(42,68),(33,59),(31,48)], "#4f7046", "#91a472", 3)
        poly([(45,43),(55,40),(61,48),(57,57),(48,60),(40,54)], "#6b8255")
        poly([(52,58),(62,56),(69,64),(65,74),(55,76),(49,69)], "#6e7548")
        poly([(72,48),(83,43),(90,48),(91,58),(84,64),(75,60)], "#577447")
        poly([(77,65),(87,62),(94,68),(91,78),(82,81),(74,74)], "#58794b")
        poly([(13,49),(22,45),(28,50),(27,59),(20,64),(12,59)], "#687c4d")
        poly([(5,63),(15,58),(23,65),(21,76),(12,82),(5,75)], "#2e3536", "#756b60", 3)
        poly([(34,68),(45,66),(52,74),(50,84),(41,91),(30,85),(27,76)], "#577346")
        poly([(15,78),(28,74),(34,82),(30,92),(19,95),(11,88)], "#4e6544")
        poly([(5,66),(13,64),(20,72),(18,86),(10,91),(4,82)], "#3a3638", "#8a5e50", 3)

        for x, y, rx, ry, fill in [(46,27,5,3,"#5b7749"),(55,31,4,2,"#5a7448"),(67,42,3,5,"#5c744a"),(29,58,4,3,"#62794d"),(59,82,5,3,"#617949"),(72,82,4,3,"#5c7548"),(42,93,4,3,"#6c774b"),(91,18,2,4,"#8c8a88")]:
            canvas.create_oval((x-rx)/100*w,(y-ry)/100*h,(x+rx)/100*w,(y+ry)/100*h,fill=fill,outline="#9da184",width=2)

        for pts in [[(36,44),(43,48),(49,55),(52,66)],[(58,41),(55,49),(62,56),(61,66)],[(21,67),(29,72),(38,75),(46,81)],[(77,50),(82,55),(85,62),(84,72)]]:
            scaled=[]
            for x,y in pts:
                scaled.extend((x/100*w,y/100*h))
            canvas.create_line(*scaled, fill="#7cb7c2", width=3, smooth=True)

        for x,y,text in [(22,20,"FROST REGION"),(69,20,"DESERT REGION"),(48,51,"CENTRAL ISLES"),(84,54,"EASTERN ISLES"),(14,72,"VOLCANIC WEST"),(40,80,"SOUTHERN WILDS")]:
            canvas.create_text(x/100*w,y/100*h,text=text,fill="#eef4ef",font=("Segoe UI",9,"bold"))

    def refresh_map(self):
        if self.map_window is None or not self.map_window.winfo_exists():
            return
        canvas = getattr(self.map_window, "_map_canvas", None)
        if canvas is None:
            return
        canvas.delete("all")
        w = max(100, canvas.winfo_width())
        h = max(100, canvas.winfo_height())
        self.draw_world_map(canvas, w, h)

        if pal_ai.CONFIG.get("map_overlay", {}).get("show_grid", True):
            for i in range(11):
                x = i * w / 10
                y = i * h / 10
                canvas.create_line(x, 0, x, h, fill="#789098", stipple="gray50")
                canvas.create_line(0, y, w, y, fill="#789098", stipple="gray50")

        canvas.create_text(w/2, 16, text="NORTH", fill="white", font=("Segoe UI",9,"bold"))
        canvas.create_text(w/2, h-16, text="SOUTH", fill="white", font=("Segoe UI",9,"bold"))
        canvas.create_text(18, h/2, text="WEST", fill="white", angle=90, font=("Segoe UI",9,"bold"))
        canvas.create_text(w-18, h/2, text="EAST", fill="white", angle=90, font=("Segoe UI",9,"bold"))

        pins = self.db.list_map_pins()
        for number, (_pin_id, name, x, y, note) in enumerate(pins, start=1):
            px = max(0, min(100, float(x))) / 100 * w
            py = max(0, min(100, float(y))) / 100 * h
            canvas.create_oval(px-11, py-11, px+11, py+11, fill="#ffffff", outline="#111111", width=2)
            canvas.create_text(px, py, text=str(number), fill="#111111", font=("Segoe UI", 8, "bold"))
            canvas.create_text(px+14, py-14, text=name, fill="white", anchor="sw", font=("Segoe UI", 9, "bold"))
            if note:
                canvas.create_text(px+14, py+2, text=note[:56], fill="#e5e5e5", anchor="nw", font=("Segoe UI", 8))

        if self.map_zoom != 1.0:
            canvas.scale("all", w/2, h/2, self.map_zoom, self.map_zoom)

        if self.map_pin_list_frame is not None and self.map_pin_list_frame.winfo_exists():
            for child in self.map_pin_list_frame.winfo_children():
                child.destroy()
            if not pins:
                tk.Label(self.map_pin_list_frame, text="No saved pins yet.", fg="#7f96a8", bg="#111a23", font=("Segoe UI", 9)).pack(anchor="w", padx=4, pady=6)
            else:
                for idx, (_pin_id, name, x, y, note) in enumerate(pins, start=1):
                    row = tk.Frame(self.map_pin_list_frame, bg="#16222d")
                    row.pack(fill="x", pady=4)
                    tk.Label(row, text=str(idx), fg="white", bg="#1e78c6", font=("Segoe UI", 9, "bold"), width=2).pack(side="left", padx=(7, 8), pady=8)
                    txt = tk.Frame(row, bg="#16222d")
                    txt.pack(side="left", fill="x", expand=True, pady=6)
                    tk.Label(txt, text=name, fg="#f2f5f7", bg="#16222d", font=("Segoe UI", 9, "bold")).pack(anchor="w")
                    tk.Label(txt, text=f"Map position: {x:.0f}, {y:.0f}", fg="#91a4b3", bg="#16222d", font=("Segoe UI", 8)).pack(anchor="w")
                    if note:
                        tk.Label(txt, text=note[:48], fg="#b9c6cf", bg="#16222d", wraplength=160, justify="left", font=("Segoe UI", 8)).pack(anchor="w", pady=(2,0))

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
            name, x, y, note = pin
            self._say_ui("System", f"Map pin added: {name} ({x:.0f}, {y:.0f})")
            if self.map_suggestion_label is not None and self.map_suggestion_label.winfo_exists():
                self.map_suggestion_label.configure(text=f"Recommended: {name}\nMap position: {x:.0f}, {y:.0f}\n\n{note or 'PAL-AI marked this location for you.'}")
            if pal_ai.CONFIG.get("map_overlay", {}).get("auto_open_on_new_pin", True):
                if self.map_window is None or not self.map_window.winfo_exists():
                    self.open_map()
                else:
                    self.refresh_map()

    pal_ai.App.__init__ = app_init
    pal_ai.App._build = build
    pal_ai.App.toggle_map = toggle_map
    pal_ai.App.open_map = open_map
    pal_ai.App.change_map_zoom = change_map_zoom
    pal_ai.App.reset_map_zoom = reset_map_zoom
    pal_ai.App.draw_world_map = draw_world_map
    pal_ai.App.refresh_map = refresh_map
    pal_ai.App.clear_map_pins_ui = clear_map_pins_ui
    pal_ai.App.parse_map_pin = parse_map_pin
    pal_ai.App._finish_answer = finish_answer
