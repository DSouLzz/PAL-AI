# PAL-AI Troubleshooting

## J Push-to-Talk does not work
Check Windows microphone permissions and make sure `ptt_enabled` is true in `config.json`.

## J also triggers an action in Palworld
PAL-AI listens for J but does not suppress the keypress. Remove or change Palworld's J binding.

## Screen analysis captures the wrong monitor
The current version captures the primary Windows monitor.

## Ollama is disconnected
Start Ollama and click **Test Ollama**.

## Update fails the SHA-256 check
Do not bypass it. The downloaded release does not match the checksum published with the GitHub Release.

## Will updates erase memory?
No. The updater preserves `config.json`, `data/`, `knowledge/`, `screenshots/`, and `.venv/`.
