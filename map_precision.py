import re
import sqlite3
import tkinter as tk


def apply_map_precision(pal_ai):
    """Upgrade PAL-AI map pins to real Palworld-style coordinates."""

    # Replace the old normalized-coordinate instructions.
    if "x and y must be normalized positions" in pal_ai.SYSTEM_PROMPT:
        pal_ai.SYSTEM_PROMPT = pal_ai.SYSTEM_PROMPT.replace(
            "x and y must be normalized positions from 0 to 100, where x=0 is west/left,\n"
            "x=100 is east/right, y=0 is north/top, and y=100 is south/bottom.\n",
            "x and y must be actual Palworld in-game map coordinates, for example -23, -341.\n"
            "Do not convert them into percentages.\n",
        )

    old_db_init = pal_ai.MemoryDB.__init__

    def db_init(self, path):
        old_db_init(self, path)
        try:
            self.conn.execute("ALTER TABLE map_pins ADD COLUMN coord_mode TEXT DEFAULT 'legacy'")
            self.conn.execute("UPDATE map_pins SET coord_mode='legacy' WHERE coord_mode IS NULL")
            self.conn.commit()
        except sqlite3.OperationalError:
            pass

    def add_map_pin(self, name, x, y, note="", coord_mode="world"):
        self.conn.execute(
            "INSERT INTO map_pins(ts,name,x,y,note,coord_mode) VALUES(datetime('now'),?,?,?,?,?)",
            (name, float(x), float(y), note, coord_mode),
        )
        self.conn.commit()

    def list_map_pins(self):
        return self.conn.execute(
            "SELECT id,name,x,y,note,COALESCE(coord_mode,'legacy') FROM map_pins ORDER BY id ASC"
        ).fetchall()

    def delete_map_pin(self, pin_id):
        self.conn.execute("DELETE FROM map_pins WHERE id=?", (int(pin_id),))
        self.conn.commit()

    pal_ai.MemoryDB.__init__ = db_init
    pal_ai.MemoryDB.add_map_pin = add_map_pin
    pal_ai.MemoryDB.list_map_pins = list_map_pins
    pal_ai.MemoryDB.delete_map_pin = delete_map_pin

    def map_bounds(self):
        cfg = pal_ai.CONFIG.get("map_overlay", {}).get("world_bounds", {})
        return (
            float(cfg.get("min_x", -1954.1)),
            float(cfg.get("max_x", 1200.3)),
            float(cfg.get("min_y", -1908.7)),
            float(cfg.get("max_y", 1245.8)),
        )

    def world_to_canvas(self, x, y, w, h):
        min_x, max_x, min_y, max_y = self.map_bounds()
        px = (float(x) - min_x) / (max_x - min_x) * w
        py = (max_y - float(y)) / (max_y - min_y) * h
        return px, py

    def legacy_to_canvas(self, x, y, w, h):
        return (
            max(0, min(100, float(x))) / 100 * w,
            max(0, min(100, float(y))) / 100 * h,
        )

    def draw_world_map(self, canvas, w, h):
        # Ocean / deep-water frame.
        canvas.create_rectangle(0, 0, w, h, fill="#0d3340", outline="")

        def poly(points, fill, outline="#a9b28f", width=2):
            pts = []
            for x, y in points:
                pts.extend((x / 100 * w, y / 100 * h))
            canvas.create_polygon(*pts, fill=fill, outline=outline, width=width, smooth=True)

        # Larger, more detailed stylized land masses.
        poly([(5,8),(17,3),(29,5),(39,11),(44,20),(41,31),(34,39),(24,42),(14,36),(7,27)], "#dce7e8", "#edf5f4", 3)
        poly([(18,31),(30,27),(40,34),(39,46),(31,52),(22,47)], "#53764c", "#88a377", 2)
        poly([(56,6),(69,4),(81,9),(87,19),(86,30),(78,40),(67,41),(58,33),(54,22)], "#b8a38e", "#d8c7b4", 3)
        poly([(74,31),(89,27),(96,35),(93,46),(82,48),(72,41)], "#58764a", "#8da477", 2)
        poly([(35,40),(47,33),(59,37),(68,47),(67,58),(59,69),(47,73),(36,67),(29,57),(29,47)], "#507349", "#91a878", 3)
        poly([(41,45),(52,40),(62,46),(60,57),(51,62),(41,57)], "#718a59", "#a4b487", 2)
        poly([(50,61),(62,57),(72,64),(69,77),(57,80),(47,71)], "#687c4e", "#9da579", 2)
        poly([(71,47),(84,42),(94,48),(94,60),(86,67),(75,62)], "#53754b", "#92a77a", 2)
        poly([(76,65),(89,62),(97,69),(93,82),(82,84),(72,75)], "#597a4d", "#94a77b", 2)
        poly([(10,48),(21,44),(30,50),(28,61),(19,67),(9,60)], "#657e50", "#9aa97c", 2)
        poly([(3,62),(13,58),(24,65),(23,78),(13,85),(4,78)], "#333638", "#7e6a5d", 3)
        poly([(29,69),(42,65),(53,74),(52,87),(41,94),(27,87),(23,77)], "#55754a", "#98a87e", 2)
        poly([(4,69),(12,65),(20,73),(19,88),(10,94),(3,84)], "#3a3438", "#945f50", 3)

        # Small islands and reefs.
        for x, y, rx, ry, fill in [
            (47,27,5,3,"#58784b"),(55,31,4,2,"#607a4c"),(66,43,3,5,"#5c774c"),
            (29,58,4,3,"#627b4e"),(60,84,5,3,"#627c4c"),(73,83,4,3,"#5c7849"),
            (43,95,4,3,"#6f794d"),(92,18,2,4,"#888a89"),(88,90,3,2,"#65764a")
        ]:
            canvas.create_oval((x-rx)/100*w,(y-ry)/100*h,(x+rx)/100*w,(y+ry)/100*h,
                               fill=fill, outline="#a1a68c", width=2)

        # Rivers / route-like visual structure.
        for pts in [
            [(34,43),(41,48),(48,55),(53,67)],[(58,39),(54,49),(62,57),(61,70)],
            [(19,68),(28,72),(39,76),(48,83)],[(76,49),(82,55),(86,64),(84,76)],
            [(17,33),(23,38),(28,45)],[(64,17),(70,25),(76,34)]
        ]:
            data = []
            for x, y in pts:
                data.extend((x/100*w, y/100*h))
            canvas.create_line(*data, fill="#78b5c0", width=3, smooth=True)

        # Major region captions.
        for x, y, text in [
            (23,19,"FROST REGION"),(70,19,"DESERT REGION"),(48,52,"CENTRAL ISLES"),
            (85,54,"EASTERN ISLES"),(13,73,"VOLCANIC WEST"),(41,83,"SOUTHERN WILDS")
        ]:
            canvas.create_text(x/100*w, y/100*h, text=text, fill="#eef5ef",
                               font=("Segoe UI", 9, "bold"))

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

        cfg = pal_ai.CONFIG.get("map_overlay", {})
        min_x, max_x, min_y, max_y = self.map_bounds()
        step = int(cfg.get("grid_step", 250))

        if cfg.get("show_grid", True):
            gx = int(min_x // step) * step
            while gx <= max_x:
                px, _ = self.world_to_canvas(gx, 0, w, h)
                canvas.create_line(px, 0, px, h, fill="#718991", stipple="gray50")
                canvas.create_text(px+3, 5, text=str(gx), fill="#dbe8ec", anchor="nw",
                                   font=("Segoe UI", 7, "bold"))
                gx += step

            gy = int(min_y // step) * step
            while gy <= max_y:
                _, py = self.world_to_canvas(0, gy, w, h)
                canvas.create_line(0, py, w, py, fill="#718991", stipple="gray50")
                canvas.create_text(4, py+2, text=str(gy), fill="#dbe8ec", anchor="nw",
                                   font=("Segoe UI", 7, "bold"))
                gy += step

            if min_x <= 0 <= max_x:
                px0, _ = self.world_to_canvas(0, 0, w, h)
                canvas.create_line(px0, 0, px0, h, fill="#e3edf0", width=2)
            if min_y <= 0 <= max_y:
                _, py0 = self.world_to_canvas(0, 0, w, h)
                canvas.create_line(0, py0, w, py0, fill="#e3edf0", width=2)

        canvas.create_text(w/2, 16, text="NORTH", fill="white", font=("Segoe UI", 9, "bold"))
        canvas.create_text(w/2, h-16, text="SOUTH", fill="white", font=("Segoe UI", 9, "bold"))
        canvas.create_text(18, h/2, text="WEST", fill="white", angle=90, font=("Segoe UI", 9, "bold"))
        canvas.create_text(w-18, h/2, text="EAST", fill="white", angle=90, font=("Segoe UI", 9, "bold"))

        pins = self.db.list_map_pins()
        radius = int(cfg.get("pin_radius", 12))
        for number, (pin_id, name, x, y, note, mode) in enumerate(pins, start=1):
            if mode == "world":
                px, py = self.world_to_canvas(x, y, w, h)
                coord_text = f"{x:.0f}, {y:.0f}"
            else:
                px, py = self.legacy_to_canvas(x, y, w, h)
                coord_text = "legacy pin"

            tag = f"pin_{pin_id}"
            canvas.create_oval(px-radius, py-radius, px+radius, py+radius,
                               fill="#e53935", outline="white", width=2,
                               tags=(tag, "map_pin"))
            canvas.create_text(px, py, text=str(number), fill="white",
                               font=("Segoe UI", 8, "bold"), tags=(tag, "map_pin"))
            canvas.create_text(px+radius+5, py-14, text=name, fill="white", anchor="sw",
                               font=("Segoe UI", 9, "bold"), tags=(tag, "map_pin"))
            canvas.create_text(px+radius+5, py+1, text=coord_text, fill="#d7e4e9", anchor="nw",
                               font=("Segoe UI", 8), tags=(tag, "map_pin"))
            canvas.tag_bind(tag, "<Button-1>", lambda _e, pid=pin_id: self.select_map_pin(pid))

        panel = getattr(self, "map_pin_list_frame", None)
        if panel is not None and panel.winfo_exists():
            for child in panel.winfo_children():
                child.destroy()
            if not pins:
                tk.Label(panel, text="No saved pins yet.", fg="#7f96a8", bg="#111a23",
                         font=("Segoe UI", 9)).pack(anchor="w", padx=4, pady=6)
            else:
                for number, (pin_id, name, x, y, note, mode) in enumerate(pins, start=1):
                    row = tk.Frame(panel, bg="#16222d")
                    row.pack(fill="x", pady=4)
                    tk.Button(row, text=str(number), fg="white", bg="#d93636", relief="flat", width=2,
                              command=lambda pid=pin_id: self.select_map_pin(pid)).pack(side="left", padx=(7,8), pady=8)
                    text = tk.Frame(row, bg="#16222d")
                    text.pack(side="left", fill="x", expand=True, pady=6)
                    tk.Label(text, text=name, fg="#f2f5f7", bg="#16222d",
                             font=("Segoe UI", 9, "bold")).pack(anchor="w")
                    coords = f"{x:.0f}, {y:.0f}" if mode == "world" else "Legacy pin"
                    tk.Label(text, text=coords, fg="#91a4b3", bg="#16222d",
                             font=("Segoe UI", 8)).pack(anchor="w")

    def select_map_pin(self, pin_id):
        lookup = {row[0]: row for row in self.db.list_map_pins()}
        pin = lookup.get(int(pin_id))
        if not pin:
            return
        _, name, x, y, note, mode = pin
        coords = f"Coordinates: {x:.0f}, {y:.0f}" if mode == "world" else "Legacy percentage pin"
        label = getattr(self, "map_suggestion_label", None)
        if label is not None and label.winfo_exists():
            label.configure(text=f"{name}\n{coords}\n\n{note or 'Saved PAL-AI map pin.'}")

    def parse_map_pin(self, answer):
        pattern = r"\[\[MAP_PIN\|([^|\]]{1,60})\|(-?[0-9]+(?:\.[0-9]+)?)\|(-?[0-9]+(?:\.[0-9]+)?)\|([^\]]{0,120})\]\]"
        match = re.search(pattern, answer)
        if not match:
            return answer, None

        name = match.group(1).strip()
        x = float(match.group(2))
        y = float(match.group(3))
        note = match.group(4).strip()
        clean = re.sub(pattern, "", answer).strip()
        min_x, max_x, min_y, max_y = self.map_bounds()
        if not (min_x <= x <= max_x and min_y <= y <= max_y):
            return clean, None

        self.db.add_map_pin(name, x, y, note, coord_mode="world")
        return clean, (name, x, y, note)

    pal_ai.App.map_bounds = map_bounds
    pal_ai.App.world_to_canvas = world_to_canvas
    pal_ai.App.legacy_to_canvas = legacy_to_canvas
    pal_ai.App.draw_world_map = draw_world_map
    pal_ai.App.refresh_map = refresh_map
    pal_ai.App.select_map_pin = select_map_pin
    pal_ai.App.parse_map_pin = parse_map_pin
