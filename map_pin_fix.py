import re


PIN_REQUEST_WORDS = (
    "pin it", "put a pin", "add a pin", "mark it", "mark this", "mark that",
    "mark on map", "pin on map", "put it on the map", "show on map",
)


def apply_map_pin_fix(pal_ai):
    """Make map pin commands deterministic and only confirm after a real DB save."""

    pal_ai.SYSTEM_PROMPT += """

STRICT MAP PIN RULE:
If the player explicitly asks you to pin, mark, show, or put a location on the PAL-AI map,
you MUST append exactly one machine-readable token at the very end of your answer:
[[MAP_PIN|short name|x|y|short note]]
Use actual Palworld world coordinates. Do not say that a pin was added unless you also append
this token. Do not put commas between x and y inside separate token fields. If you do not know
reliable coordinates, say that you cannot place the pin yet.
"""

    old_ask = pal_ai.App.ask
    old_finish = pal_ai.App._finish_answer

    def is_pin_request(text):
        q = str(text).lower()
        return any(word in q for word in PIN_REQUEST_WORDS)

    def ask(self, text, *args, **kwargs):
        if is_pin_request(text):
            text = (
                str(text)
                + "\n\nIMPORTANT: If you can identify reliable coordinates for this location, "
                  "append exactly [[MAP_PIN|name|x|y|note]] at the end. "
                  "Example: [[MAP_PIN|Sulfur Field|-23|-341|Good sulfur farm]]. "
                  "Do not claim the pin was added unless you output that token."
            )
        return old_ask(self, text, *args, **kwargs)

    def parse_flexible_pin(self, answer):
        """Accept strict tokens plus common model formatting mistakes."""
        text = str(answer)

        # Preferred format: [[MAP_PIN|Name|-23|-341|Note]]
        strict = re.search(
            r"\[\[\s*MAP_PIN\s*\|\s*([^|\]]{1,80}?)\s*\|\s*(-?\d+(?:\.\d+)?)\s*\|\s*(-?\d+(?:\.\d+)?)\s*\|\s*([^\]]{0,160}?)\s*\]\]",
            text,
            re.I,
        )
        if strict:
            name = strict.group(1).strip()
            x = float(strict.group(2))
            y = float(strict.group(3))
            note = strict.group(4).strip()
            clean = (text[:strict.start()] + text[strict.end():]).strip()
            return clean, (name, x, y, note)

        # Tolerate model mistake seen in practice:
        # [[MAP_PIN|Frozen Tundra| -12, -285 | note]]
        combined = re.search(
            r"\[\[\s*MAP_PIN\s*\|\s*([^|\]]{1,80}?)\s*\|\s*(-?\d+(?:\.\d+)?)\s*,\s*(-?\d+(?:\.\d+)?)\s*\|\s*([^\]]{0,160}?)\s*\]\]",
            text,
            re.I,
        )
        if combined:
            name = combined.group(1).strip()
            x = float(combined.group(2))
            y = float(combined.group(3))
            note = combined.group(4).strip()
            clean = (text[:combined.start()] + text[combined.end():]).strip()
            return clean, (name, x, y, note)

        return text, None

    def validate_and_save(self, pin):
        if pin is None:
            return None
        name, x, y, note = pin
        min_x, max_x, min_y, max_y = self.map_bounds()
        if not (min_x <= x <= max_x and min_y <= y <= max_y):
            return None
        self.db.add_map_pin(name, x, y, note, coord_mode="world")
        return pin

    def extract_fallback_pin(self, answer):
        text = str(answer)
        if not re.search(r"\b(pin|pinned|mark|marked|map)\b", text, re.I):
            return None

        m = re.search(
            r"(?:coordinates?\s*[:=]?\s*|located\s+at\s*|at\s*\()(-?\d+(?:\.\d+)?)\s*[,/]\s*(-?\d+(?:\.\d+)?)(?:\))?",
            text,
            re.I,
        )
        if not m:
            return None

        x, y = float(m.group(1)), float(m.group(2))
        min_x, max_x, min_y, max_y = self.map_bounds()
        if not (min_x <= x <= max_x and min_y <= y <= max_y):
            return None

        name = "PAL-AI suggestion"
        n = re.search(r"(?:recommend|location is|go to|at)\s+(?:the\s+)?([A-Z][A-Za-z0-9 '\-]{2,40})", text)
        if n:
            name = n.group(1).strip().rstrip(".,")
        return name, x, y, "Recovered from PAL-AI coordinate response"

    def finish_answer(self, answer):
        # Parse flexible machine-readable formats first.
        clean, candidate = parse_flexible_pin(self, answer)
        pin = validate_and_save(self, candidate)

        # If no token worked, try prose coordinates.
        if pin is None:
            fallback = extract_fallback_pin(self, answer)
            if fallback is not None:
                pin = validate_and_save(self, fallback)
                clean = re.sub(r"\s*\[\[\s*MAP_PIN[^\]]*\]\]\s*", " ", str(answer), flags=re.I).strip()

        # Never show raw MAP_PIN syntax to the player.
        clean = re.sub(r"\s*\[\[\s*MAP_PIN[^\]]*\]\]\s*", " ", str(clean), flags=re.I).strip()

        # Avoid double-saving by passing token-free text to the prior finisher.
        old_finish(self, clean)

        if pin:
            name, x, y, note = pin
            self._say_ui("System", f"✓ Pin actually saved: {name} ({x:.0f}, {y:.0f})")
            if getattr(self, "map_suggestion_label", None) is not None and self.map_suggestion_label.winfo_exists():
                self.map_suggestion_label.configure(
                    text=f"{name}\nCoordinates: {x:.0f}, {y:.0f}\n\n{note or 'Saved PAL-AI map pin.'}"
                )

            if pal_ai.CONFIG.get("map_overlay", {}).get("auto_open_on_new_pin", True):
                if getattr(self, "map_window", None) is None or not self.map_window.winfo_exists():
                    self.open_map()
                self.root.after(120, self.refresh_map)
                self.root.after(500, self.refresh_map)
        else:
            if re.search(r"\b(i(?:'ve| have)?\s+(?:pinned|marked|added a pin)|pin(?:ned)?\s+(?:it|this)|marked\s+(?:it|this))\b", str(answer), re.I):
                self._say_ui("System", "⚠ PAL-AI mentioned a pin, but no valid coordinates were saved. Ask it for exact coordinates and try again.")

    pal_ai.App.ask = ask
    pal_ai.App._finish_answer = finish_answer
