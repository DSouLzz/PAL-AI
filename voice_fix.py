import os
import re
import subprocess
import threading

import pyttsx3


def reliable_speak(self, text):
    """Reliable English TTS for PAL-AI on Windows, with pyttsx3 fallback."""
    try:
        from pal_ai import CONFIG
    except Exception:
        CONFIG = {"voice_enabled": True}

    if not CONFIG.get("voice_enabled", True):
        return

    spoken = re.sub(r"[#*_`]", "", str(text)).strip()[:1600]
    if not spoken:
        return

    lock = getattr(self, "lock", None)
    if lock is None:
        lock = threading.Lock()
        self.lock = lock

    with lock:
        if os.name == "nt" and CONFIG.get("tts_engine", "windows_sapi") == "windows_sapi":
            try:
                safe_text = spoken.replace("'", "''")
                rate = max(-10, min(10, int(CONFIG.get("tts_rate", 1))))
                volume = max(0, min(100, int(CONFIG.get("tts_volume", 100))))
                ps = (
                    "Add-Type -AssemblyName System.Speech; "
                    "$s = New-Object System.Speech.Synthesis.SpeechSynthesizer; "
                    f"$s.Rate = {rate}; $s.Volume = {volume}; "
                    "$voices = $s.GetInstalledVoices() | ForEach-Object { $_.VoiceInfo }; "
                    "$en = $voices | Where-Object { $_.Culture.Name -like 'en-*' } | Select-Object -First 1; "
                    "if ($en) { $s.SelectVoice($en.Name) }; "
                    f"$s.Speak('{safe_text}'); "
                    "$s.Dispose();"
                )
                result = subprocess.run(
                    ["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-Command", ps],
                    capture_output=True,
                    text=True,
                    timeout=90,
                    creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
                )
                if result.returncode == 0:
                    return
            except Exception:
                pass

        try:
            engine = pyttsx3.init()
            engine.setProperty("rate", 185)
            engine.setProperty("volume", 1.0)
            try:
                for voice in engine.getProperty("voices"):
                    info = (
                        getattr(voice, "name", "") + " " +
                        getattr(voice, "id", "") + " " +
                        str(getattr(voice, "languages", ""))
                    ).lower()
                    if "english" in info or "en-us" in info or "en-gb" in info:
                        engine.setProperty("voice", voice.id)
                        break
            except Exception:
                pass
            engine.say(spoken)
            engine.runAndWait()
            try:
                engine.stop()
            except Exception:
                pass
        except Exception as e:
            print(f"TTS error: {e}")
