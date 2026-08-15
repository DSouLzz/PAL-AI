# PAL-AI

PAL-AI is a local English-speaking Palworld companion for Windows.

## Current features

- Local Ollama model (`gemma3:4b` by default)
- Global **J Push-to-Talk**
- English speech recognition with faster-whisper
- English spoken responses
- Voice-triggered screen analysis
- Local long-term memory with SQLite
- Local Palworld knowledge files
- Optional read-only Palworld dedicated-server status integration
- GitHub Release based self-updater with SHA-256 verification

## Local data

These folders/files are intentionally not meant to be committed from a personal installation:

- `data/`
- `screenshots/`
- `.venv/`
- personal `config.json`

Use `config.example.json` as the repository template.

## Releases

A release is created by pushing a version tag such as:

```text
v0.7
```

GitHub Actions packages the app into a ZIP, calculates a SHA-256 checksum, and publishes both as GitHub Release assets.

PAL-AI checks the latest public GitHub Release, downloads the ZIP, verifies the checksum, installs it in place, preserves local memory/config/knowledge, and restarts.

## Hardware target

The current defaults are tuned for approximately:

- Intel Core i9-10900KF
- 32 GB RAM
- NVIDIA RTX 3070 8 GB
- Windows 11
