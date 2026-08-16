import json
import threading
import time
import tkinter as tk
from tkinter import ttk, simpledialog, messagebox

import requests


def apply_server_sync(pal_ai):
    """Read-only live position/world sync through Palworld's official REST API."""
    cfg = pal_ai.CONFIG.setdefault("server_sync", {})
    cfg.setdefault("enabled", False)
    cfg.setdefault("base_url", "http://127.0.0.1:8212/v1/api")
    cfg.setdefault("username", "")
    cfg.setdefault("password", "")
    cfg.setdefault("player_name", "")
    cfg.setdefault("player_id", "")
    cfg.setdefault("interval_seconds", 5)
    cfg.setdefault("world_guid", "")
    cfg.setdefault("server_name", "")

    old_init = pal_ai.App.__init__
    old_open_map = pal_ai.App.open_map

    def save_config():
        pal_ai.CONFIG_PATH.write_text(json.dumps(pal_ai.CONFIG, indent=2, ensure_ascii=False), encoding="utf-8")

    def app_init(self, root):
        self.server_sync_stop = threading.Event()
        self.server_sync_thread = None
        self.server_sync_status = "Server sync OFF"
        old_init(self, root)
        if pal_ai.CONFIG.get("server_sync", {}).get("enabled", False):
            self.start_server_sync()

    def api_get(self, endpoint):
        scfg = pal_ai.CONFIG.get("server_sync", {})
        base = str(scfg.get("base_url", "")).rstrip("/")
        auth = None
        if scfg.get("username") or scfg.get("password"):
            auth = (str(scfg.get("username", "")), str(scfg.get("password", "")))
        r = requests.get(base + endpoint, auth=auth, headers={"Accept": "application/json"}, timeout=4)
        r.raise_for_status()
        return r.json()

    def choose_player(self, players):
        scfg = pal_ai.CONFIG.get("server_sync", {})
        wanted_id = str(scfg.get("player_id", "")).strip().lower()
        wanted_name = str(scfg.get("player_name", "")).strip().lower()
        if wanted_id:
            for p in players:
                if str(p.get("playerId", "")).lower() == wanted_id or str(p.get("userId", "")).lower() == wanted_id:
                    return p
        if wanted_name:
            for p in players:
                if str(p.get("name", "")).strip().lower() == wanted_name or str(p.get("accountName", "")).strip().lower() == wanted_name:
                    return p
        if len(players) == 1:
            return players[0]
        return None

    def sync_once(self, announce=False):
        info = self.server_api_get("/info")
        pdata = self.server_api_get("/players")
        players = pdata.get("players", []) if isinstance(pdata, dict) else []
        player = choose_player(self, players)
        if player is None:
            names = ", ".join(str(p.get("name", "?")) for p in players[:8])
            raise RuntimeError("Could not identify your player. Set Player Name in Server Sync." + (f" Online: {names}" if names else ""))

        x = float(player.get("location_x"))
        y = float(player.get("location_y"))
        world_guid = str(info.get("worldguid", ""))
        server_name = str(info.get("servername", "Palworld Server"))

        scfg = pal_ai.CONFIG.setdefault("server_sync", {})
        previous_world = str(scfg.get("world_guid", ""))
        scfg["world_guid"] = world_guid
        scfg["server_name"] = server_name
        scfg["player_id"] = str(player.get("playerId", scfg.get("player_id", "")))
        if not scfg.get("player_name"):
            scfg["player_name"] = str(player.get("name", ""))

        pos = pal_ai.CONFIG.setdefault("map_overlay", {}).setdefault("player_position", {})
        pos.update({"known": True, "x": x, "y": y, "source": "server_rest", "world_guid": world_guid})
        save_config()

        self.server_sync_status = f"LIVE • {server_name} • {x:.0f}, {y:.0f}"
        try:
            self.root.after(0, self.refresh_map)
            self.root.after(0, self.refresh_server_sync_label)
        except Exception:
            pass

        if announce:
            self.root.after(0, lambda: self._say_ui("System", f"✓ Server sync connected: {server_name}. Live position ({x:.0f}, {y:.0f})."))
        elif previous_world and world_guid and previous_world != world_guid:
            self.root.after(0, lambda: self._say_ui("System", f"World changed. PAL-AI is now synced to {server_name}."))
        return x, y

    def sync_loop(self):
        first = True
        while not self.server_sync_stop.is_set():
            try:
                self.sync_server_position(announce=first)
                first = False
            except Exception as exc:
                self.server_sync_status = "Server sync waiting"
                try:
                    self.root.after(0, self.refresh_server_sync_label)
                except Exception:
                    pass
            interval = max(2, int(pal_ai.CONFIG.get("server_sync", {}).get("interval_seconds", 5)))
            self.server_sync_stop.wait(interval)

    def start_server_sync(self):
        if self.server_sync_thread is not None and self.server_sync_thread.is_alive():
            return
        self.server_sync_stop.clear()
        pal_ai.CONFIG.setdefault("server_sync", {})["enabled"] = True
        save_config()
        self.server_sync_thread = threading.Thread(target=self.server_sync_loop, daemon=True)
        self.server_sync_thread.start()
        self.server_sync_status = "Server sync connecting..."
        self.refresh_server_sync_label()

    def stop_server_sync(self):
        pal_ai.CONFIG.setdefault("server_sync", {})["enabled"] = False
        save_config()
        self.server_sync_stop.set()
        self.server_sync_status = "Server sync OFF"
        self.refresh_server_sync_label()

    def configure_server_sync(self):
        scfg = pal_ai.CONFIG.setdefault("server_sync", {})
        base = simpledialog.askstring("PAL-AI Server Sync", "Palworld REST API URL:", initialvalue=scfg.get("base_url", "http://127.0.0.1:8212/v1/api"), parent=self.root)
        if not base:
            return
        username = simpledialog.askstring("PAL-AI Server Sync", "REST API username (leave blank if not used):", initialvalue=scfg.get("username", ""), parent=self.root)
        if username is None:
            return
        password = simpledialog.askstring("PAL-AI Server Sync", "REST API password (leave blank if not used):", initialvalue=scfg.get("password", ""), show="*", parent=self.root)
        if password is None:
            return
        player_name = simpledialog.askstring("PAL-AI Server Sync", "Your exact in-game player name:", initialvalue=scfg.get("player_name", ""), parent=self.root)
        if player_name is None:
            return
        scfg.update({"base_url": base.rstrip("/"), "username": username, "password": password, "player_name": player_name})
        save_config()
        try:
            self.sync_server_position(announce=True)
            self.start_server_sync()
        except Exception as exc:
            messagebox.showerror("PAL-AI Server Sync", f"Could not connect:\n{exc}\n\nThe server must have RESTAPIEnabled=True and PAL-AI must be able to reach its REST API port.")

    def refresh_server_sync_label(self):
        label = getattr(self, "server_sync_label", None)
        if label is not None and label.winfo_exists():
            label.configure(text=self.server_sync_status)

    def open_map(self):
        old_open_map(self)
        if self.map_window is None or not self.map_window.winfo_exists():
            return
        bar = tk.Frame(self.map_window, bg="#0b1118")
        bar.pack(fill="x", side="bottom", padx=10, pady=(0, 6))
        self.server_sync_label = tk.Label(bar, text=self.server_sync_status, fg="#48e59b", bg="#0b1118", font=("Segoe UI", 9, "bold"))
        self.server_sync_label.pack(side="left", padx=(0, 12))
        ttk.Button(bar, text="⚙ Server Sync", command=self.configure_server_sync).pack(side="left", padx=4)
        ttk.Button(bar, text="Start Live Sync", command=self.start_server_sync).pack(side="left", padx=4)
        ttk.Button(bar, text="Stop Sync", command=self.stop_server_sync).pack(side="left", padx=4)
        self.refresh_server_sync_label()

    pal_ai.App.__init__ = app_init
    pal_ai.App.server_api_get = api_get
    pal_ai.App.sync_server_position = sync_once
    pal_ai.App.server_sync_loop = sync_loop
    pal_ai.App.start_server_sync = start_server_sync
    pal_ai.App.stop_server_sync = stop_server_sync
    pal_ai.App.configure_server_sync = configure_server_sync
    pal_ai.App.refresh_server_sync_label = refresh_server_sync_label
    pal_ai.App.open_map = open_map
