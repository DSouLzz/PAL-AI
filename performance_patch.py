"""PAL-AI gaming performance patch.

Designed for gaming on limited VRAM (for example RTX 3070 8 GB).
The patch keeps the local AI available on demand but releases Ollama memory
between questions so Palworld gets the GPU back while the player is moving.
"""

import threading

import requests


DEFAULTS = {
    "enabled": True,
    "unload_model_after_response": True,
    "context_size": 2048,
    "disable_auto_memory_while_gaming": True,
    "max_history_messages": 8,
}


def apply_performance_patch(pal_ai):
    perf = pal_ai.CONFIG.setdefault("gaming_performance", {})
    for key, value in DEFAULTS.items():
        perf.setdefault(key, value)

    # These are runtime-only reductions. The user's config is not destructively
    # rewritten, so Gaming Mode can later be made configurable in the UI.
    if perf.get("enabled", True):
        pal_ai.CONFIG["max_history_messages"] = int(perf.get("max_history_messages", 8))
        if perf.get("disable_auto_memory_while_gaming", True):
            pal_ai.CONFIG["auto_memory_every_turns"] = 0

    original_chat = pal_ai.OllamaClient.chat

    def gaming_chat(self, model, messages, images=None, timeout=180):
        if not perf.get("enabled", True):
            return original_chat(self, model, messages, images=images, timeout=timeout)

        msgs = list(messages)
        if images:
            msgs[-1] = dict(msgs[-1])
            msgs[-1]["images"] = images

        payload = {
            "model": model,
            "messages": msgs,
            "stream": False,
            "options": {
                "num_ctx": int(perf.get("context_size", 2048)),
            },
        }

        # Ollama normally keeps a model resident after a response. With 8 GB
        # VRAM that can make Palworld stutter when turning the camera. Setting
        # keep_alive to zero tells Ollama to unload it immediately afterwards.
        if perf.get("unload_model_after_response", True):
            payload["keep_alive"] = 0

        response = requests.post(
            self.base + "/api/chat",
            json=payload,
            timeout=timeout,
        )
        response.raise_for_status()
        return response.json()["message"]["content"]

    pal_ai.OllamaClient.chat = gaming_chat

    def unload_existing_model(base_url, model):
        try:
            requests.post(
                base_url.rstrip("/") + "/api/generate",
                json={"model": model, "keep_alive": 0},
                timeout=20,
            )
        except Exception:
            pass

    # On upgrade from an older release Ollama may still have the previous model
    # loaded. Ask it to release those models once, in the background.
    if perf.get("enabled", True) and perf.get("unload_model_after_response", True):
        base = pal_ai.CONFIG.get("ollama_url", "http://localhost:11434")
        models = {
            pal_ai.CONFIG.get("model", "gemma3:4b"),
            pal_ai.CONFIG.get("vision_model", "gemma3:4b"),
        }
        for model in models:
            threading.Thread(
                target=unload_existing_model,
                args=(base, model),
                daemon=True,
            ).start()

    # Add a small visible indicator to the title without adding GPU-heavy UI.
    original_init = pal_ai.App.__init__

    def performance_init(self, root):
        original_init(self, root)
        if perf.get("enabled", True):
            try:
                root.title(root.title() + "  |  Gaming Mode")
            except Exception:
                pass

    pal_ai.App.__init__ = performance_init
