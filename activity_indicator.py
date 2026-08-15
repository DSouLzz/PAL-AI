from tkinter import ttk


BUSY_WORDS = (
    "thinking",
    "researching",
    "scanning",
    "analyzing",
    "analysing",
    "transcribing",
    "listening",
    "recording",
    "capturing",
    "screenshot",
    "downloading",
    "loading",
    "checking",
)

IDLE_WORDS = (
    "ready",
    "connected",
    "up to date",
    "voice output",
)


def apply_activity_indicator(pal_ai):
    """Add a lightweight indeterminate activity bar to the main PAL-AI window."""

    old_build = pal_ai.App._build
    old_set_status = pal_ai.App.set_status

    def build(self):
        old_build(self)

        self.activity_frame = ttk.Frame(self.root, padding=(8, 2, 8, 4))
        self.activity_label = ttk.Label(self.activity_frame, text="PAL-AI ready")
        self.activity_label.pack(side="left", padx=(0, 8))

        self.activity_bar = ttk.Progressbar(
            self.activity_frame,
            mode="indeterminate",
            length=260,
            maximum=100,
        )
        self.activity_bar.pack(side="left", fill="x", expand=True)

        # Put the activity indicator immediately above the chat area.
        try:
            self.activity_frame.pack(
                fill="x",
                padx=0,
                pady=0,
                before=self.chatbox,
            )
        except Exception:
            self.activity_frame.pack(fill="x")

        self._activity_running = False
        self._activity_phase = 0

    def set_activity(self, active, text=None):
        if not hasattr(self, "activity_bar"):
            return

        if text:
            try:
                self.activity_label.configure(text=text)
            except Exception:
                pass

        if active and not getattr(self, "_activity_running", False):
            self._activity_running = True
            try:
                self.activity_bar.start(12)
            except Exception:
                pass
        elif not active and getattr(self, "_activity_running", False):
            self._activity_running = False
            try:
                self.activity_bar.stop()
                self.activity_bar["value"] = 0
            except Exception:
                pass

    def set_status(self, text):
        old_set_status(self, text)
        value = str(text or "")
        low = value.lower()

        if any(word in low for word in BUSY_WORDS):
            label = value
            if "research" in low:
                label = "🌐 Researching current Palworld information…"
            elif "transcrib" in low:
                label = "🎙 Transcribing your voice…"
            elif "listen" in low or "record" in low:
                label = "🎙 Listening…"
            elif "screen" in low or "captur" in low or "analy" in low:
                label = "👁 Scanning and analyzing…"
            elif "download" in low:
                label = "⬇ Downloading update…"
            elif "think" in low:
                label = "🧠 PAL-AI is thinking…"
            set_activity(self, True, label)
            return

        if any(word in low for word in IDLE_WORDS):
            set_activity(self, False, "✓ Ready")
        else:
            # Unknown statuses remain visible but do not burn CPU with animation.
            set_activity(self, False, value or "✓ Ready")

    pal_ai.App._build = build
    pal_ai.App.set_status = set_status
    pal_ai.App.set_activity = set_activity
