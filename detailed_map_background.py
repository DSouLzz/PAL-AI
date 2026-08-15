from pathlib import Path

from PIL import Image, ImageTk


def apply_detailed_map_background(pal_ai):
    """Use the latest captured in-game Palworld map screenshot as PAL-AI's map background."""

    old_draw_world_map = pal_ai.App.draw_world_map
    old_world_to_canvas = pal_ai.App.world_to_canvas

    def reference_path(self):
        return pal_ai.DATA_DIR / "ingame_map_reference.png"

    def world_to_reference_pixel(self, x, y):
        capture = pal_ai.CONFIG.get("map_overlay", {}).get("ingame_capture", {})
        if not capture.get("transform_known", False):
            return None

        dxw = float(capture.get("x2", 0)) - float(capture.get("x1", 0))
        dyw = float(capture.get("y2", 0)) - float(capture.get("y1", 0))
        if abs(dxw) < 1e-9 or abs(dyw) < 1e-9:
            return None

        sx = (float(capture.get("px2", 0)) - float(capture.get("px1", 0))) / dxw
        sy = (float(capture.get("py2", 0)) - float(capture.get("py1", 0))) / dyw
        px = float(capture.get("px1", 0)) + (float(x) - float(capture.get("x1", 0))) * sx
        py = float(capture.get("py1", 0)) + (float(y) - float(capture.get("y1", 0))) * sy
        return px, py

    def draw_world_map(self, canvas, w, h):
        path = reference_path(self)
        if path.exists():
            try:
                image = Image.open(path).convert("RGB")
                source_w, source_h = image.size
                image = image.resize((w, h), Image.Resampling.LANCZOS)
                photo = ImageTk.PhotoImage(image)
                canvas.create_image(0, 0, image=photo, anchor="nw", tags=("real_map_background",))
                canvas._real_map_photo = photo
                canvas._real_map_source_size = (source_w, source_h)
                return
            except Exception:
                pass
        old_draw_world_map(self, canvas, w, h)

    def world_to_canvas(self, x, y, w, h):
        path = reference_path(self)
        pixel = world_to_reference_pixel(self, x, y)
        if path.exists() and pixel is not None:
            try:
                source_w, source_h = getattr(
                    getattr(self.map_window, "_map_canvas", None),
                    "_real_map_source_size",
                    (0, 0),
                )
                if not source_w or not source_h:
                    with Image.open(path) as img:
                        source_w, source_h = img.size
                px, py = pixel
                return px / source_w * w, py / source_h * h
            except Exception:
                pass
        return old_world_to_canvas(self, x, y, w, h)

    def has_real_map_background(self):
        return reference_path(self).exists()

    pal_ai.App.reference_map_path = reference_path
    pal_ai.App.world_to_reference_pixel = world_to_reference_pixel
    pal_ai.App.draw_world_map = draw_world_map
    pal_ai.App.world_to_canvas = world_to_canvas
    pal_ai.App.has_real_map_background = has_real_map_background
