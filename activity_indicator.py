from tkinter import ttk


STAGES = (
    ("listening", 10, "🎙 Listening…"),
    ("recording", 15, "🎙 Recording…"),
    ("transcribing", 30, "🎙 Transcribing your voice…"),
    ("capturing", 35, "📸 Capturing screen…"),
    ("screenshot", 35, "📸 Capturing screen…"),
    ("scanning", 50, "👁 Scanning…"),
    ("analyzing", 65, "👁 Analyzing screen…"),
    ("analysing", 65, "👁 Analyzing screen…"),
    ("researching", 55, "🌐 Researching current Palworld information…"),
    ("checking", 25, "🔎 Checking…"),
    ("loading", 70, "🧠 Loading AI model…"),
    ("thinking", 80, "🧠 PAL-AI is thinking…"),
    ("downloading", 60, "⬇ Downloading update…"),
)

IDLE_WORDS = (
    "ready",
    "connected",
    "up to date",
    "voice output",
)


def apply_activity_indicator(pal_ai):
    """Add a determinate 0-100% activity bar to the main PAL-AI window."""

    old_build = pal_ai.App._build
    old_set_status = pal_ai.App.set_status
    old_finish_answer = pal_ai.App._finish_answer
    old_finish_error = pal_ai.App._finish_error

    def build(self):
        old_build(self)

        self.activity_frame = ttk.Frame(self.root, padding=(8, 2, 8, 4))
        self.activity_label = ttk.Label(self.activity_frame, text="✓ Ready")
        self.activity_label.pack(side="left", padx=(0, 8))

        self.activity_bar = ttk.Progressbar(
            self.activity_frame,
            mode="determinate",
            length=260,
            maximum=100,
            value=0,
        )
        self.activity_bar.pack(side="left", fill="x", expand=True)

        self.activity_percent = ttk.Label(self.activity_frame, text="0%", width=5)
        self.activity_percent.pack(side="left", padx=(8, 0))

        try:
            self.activity_frame.pack(
                fill="x",
                padx=0,
                pady=0,
                before=self.chatbox,
            )
        except Exception:
            self.activity_frame.pack(fill="x")

        self._activity_target = 0
        self._activity_value = 0
        self._activity_job = None

    def _draw_progress(self, value, text=None):
        value = max(0, min(100, int(value)))
        self._activity_value = value
        try:
            self.activity_bar["value"] = value
            self.activity_percent.configure(text=f"{value}%")
            if text:
                self.activity_label.configure(text=text)
        except Exception:
            pass

    def _animate_toward_target(self):
        self._activity_job = None
        current = int(getattr(self, "_activity_value", 0))
        target = int(getattr(self, "_activity_target", current))
        if current < target:
            # Smooth forward-only movement. It never bounces backwards while working.
            step = 1 if target - current < 15 else 2
            _draw_progress(self, min(target, current + step))
            self._activity_job = self.root.after(35, self._animate_toward_target)

    def set_progress(self, percent, text=None):
        percent = max(0, min(100, int(percent)))
        current = int(getattr(self, "_activity_value", 0))

        # During one task, progress is monotonic. Starting a fresh low stage resets first.
        if percent <= 15 and current >= 95:
            _draw_progress(self, 0)
            current = 0

        if percent < current and percent != 0:
            percent = current

        self._activity_target = percent
        if text:
            try:
                self.activity_label.configure(text=text)
            except Exception:
                pass

        if self._activity_job is None:
            self._activity_job = self.root.after(1, self._animate_toward_target)

    def complete_progress(self, text="✓ Ready"):
        self._activity_target = 100
        _draw_progress(self, 100, text)

        # Leave 100% visible briefly so completion is obvious, then reset for next task.
        def reset():
            self._activity_target = 0
            _draw_progress(self, 0, "✓ Ready")
        self.root.after(900, reset)

    def set_status(self, text):
        old_set_status(self, text)
        value = str(text or "")
        low = value.lower()

        for keyword, percent, label in STAGES:
            if keyword in low:
                set_progress(self, percent, label)
                return

        if any(word in low for word in IDLE_WORDS):
            # Only show completion if a task actually progressed.
            if int(getattr(self, "_activity_value", 0)) > 0:
                complete_progress(self)
            else:
                _draw_progress(self, 0, "✓ Ready")
        else:
            if value:
                try:
                    self.activity_label.configure(text=value)
                except Exception:
                    pass

    def finish_answer(self, answer):
        # Ollama has finished generating before this callback runs.
        set_progress(self, 95, "💬 Preparing answer…")
        result = old_finish_answer(self, answer)
        complete_progress(self, "✓ Answer ready")
        return result

    def finish_error(self, msg):
        result = old_finish_error(self, msg)
        complete_progress(self, "⚠ Finished with an error")
        return result

    pal_ai.App._build = build
    pal_ai.App.set_status = set_status
    pal_ai.App.set_progress = set_progress
    pal_ai.App.complete_progress = complete_progress
    pal_ai.App._animate_toward_target = _animate_toward_target
    pal_ai.App._finish_answer = finish_answer
    pal_ai.App._finish_error = finish_error
