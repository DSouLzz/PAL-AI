import re


PIN_REQUEST_WORDS = (
    "pin it", "put a pin", "add a pin", "mark it", "mark this", "mark that",
    "mark on map", "pin on map", "put it on the map", "show on map",
)


def apply_map_pin_fix(pal_ai):
    """Make map pin commands deterministic and only confirm after a real DB save."""

    # Stronger model instruction: explicit user pin requests must emit a token.
    pal_ai.SYSTEM_PROMPT += """

STRICT MAP PIN RULE:
If the player explicitly asks you to pin, mark, show, or put a location on the PAL-AI map,
you MUST append exactly one machine-readable token at the very end of your answer:
[[MAP_PIN|short name|x|y|short note]]
Use actual Palworld world coordinates. Do not say that a pin was added unless you also append
this token. If you do not know reliable coordinates, say that you cannot place the pin yet.
"""

    old_ask = pal_ai.App.ask
    old_finish = pal_ai.App._finish_answer

    def is_pin_request(text):
        q = str(text).lower()
        return any(word in q for word in PIN_REQUEST_WORDS)

    def ask(self, text, *args, **kwargs):
        # Add a hard instruction only for explicit map-pin commands.
        if is_pin_request(text):
            text = (
                str(text)
                + "\n\nIMPORTANT: If you can identify reliable coordinates for this location, "
                  "append exactly [[MAP_PIN|name|x|y|note]] at the end. "
                  "Do not claim the pin was added unless you output that token."
            )
        return old_ask(self, text, *args, **kwargs)

    def extract_fallback_pin(self, answer):
        """Recover a pin if model gave coordinates in prose but forgot the token."""
        text = str(answer)
        # Only use fallback when answer itself claims a map/pin action.
        if not re.search(r"\b(pin|pinned|mark|marked|map)\b", text, re.I):
            return None

        # Common coordinate forms: Coordinates: -23, -341  /  (-23, -341)
        m = re.search(
            r"(?:coordinates?\s*[:=]?\s*|\()(-?\d+(?:\.\d+)?)\s*[,/]\s*(-?\d+(?:\.\d+)?)(?:\))?",
            text,
            re.I,
        )
        if not m:
            return None

        x, y = float(m.group(1)), float(m.group(2))
        min_x, max_x, min_y, max_y = self.map_bounds()
        if not (min_x <= x <= max_x and min_y <= y <= max_y):
            return None

        # Try to derive a useful name from nearby prose.
        name = "PAL-AI suggestion"
        n = re.search(r"(?:recommend|location is|go to|at)\s+(?:the\s+)?([A-Z][A-Za-z0-9 '\-]{2,40})", text)
        if n:
            name = n.group(1).strip().rstrip(".,")
        return name, x, y, "Recovered from PAL-AI coordinate response"

    def finish_answer(self, answer):
        # First use the strict token parser installed by map_precision.
        clean, pin = self.parse_map_pin(answer)

        # If the model forgot its token but clearly supplied coordinates, recover it.
        if pin is None:
            fallback = extract_fallback_pin(self, answer)
            if fallback is not None:
                name, x, y, note = fallback
                self.db.add_map_pin(name, x, y, note, coord_mode="world")
                pin = fallback
                # Remove misleading claims only after we actually save the pin.
                clean = str(answer).strip()

        # Call the original base app finisher directly through the map-overlay closure chain
        # by temporarily hiding MAP_PIN tokens from user-visible text.
        token_pattern = r"\s*\[\[MAP_PIN\|[^\]]+\]\]\s*$"
        clean = re.sub(token_pattern, "", str(clean)).strip()

        # The currently installed old_finish may itself parse pins, so prevent double-save by
        # passing clean text with no token.
        old_finish(self, clean)

        if pin:
            name, x, y, note = pin
            self._say_ui("System", f"✓ Pin actually saved: {name} ({x:.0f}, {y:.0f})")
            if getattr(self, "map_suggestion_label", None) is not None and self.map_suggestion_label.winfo_exists():
                self.map_suggestion_label.configure(
                    text=f"{name}\nCoordinates: {x:.0f}, {y:.0f}\n\n{note or 'Saved PAL-AI map pin.'}"
                )

            # Open/refresh only after database commit succeeded.
            if pal_ai.CONFIG.get("map_overlay", {}).get("auto_open_on_new_pin", True):
                if getattr(self, "map_window", None) is None or not self.map_window.winfo_exists():
                    self.open_map()
                self.root.after(120, self.refresh_map)
                self.root.after(500, self.refresh_map)
        else:
            # Correct false model claims so the UI is truthful.
            if re.search(r"\b(i(?:'ve| have)?\s+(?:pinned|marked)|pin(?:ned)?\s+(?:it|this)|marked\s+(?:it|this))\b", str(answer), re.I):
                self._say_ui("System", "⚠ PAL-AI mentioned a pin, but no valid coordinates were saved. Ask it to give exact coordinates and pin again.")

    pal_ai.App.ask = ask
    pal_ai.App._finish_answer = finish_answer
