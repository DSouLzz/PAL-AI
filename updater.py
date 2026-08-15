import hashlib
import json
import subprocess
import sys
import tempfile
import zipfile
from pathlib import Path
from urllib.parse import urlparse

import requests

APP_DIR = Path(__file__).resolve().parent
CONFIG_PATH = APP_DIR / "config.json"
VERSION_PATH = APP_DIR / "VERSION"
DEFAULT_REPO = "DSouLzz/PAL-AI"
GITHUB_API = "https://api.github.com"


def load_config():
    with open(CONFIG_PATH, "r", encoding="utf-8") as f:
        return json.load(f)


def current_version():
    try:
        return VERSION_PATH.read_text(encoding="utf-8").strip()
    except Exception:
        try:
            return str(load_config().get("app_version", "0.0"))
        except Exception:
            return "0.0"


def version_tuple(v):
    v = str(v).strip().lstrip("vV")
    out = []
    for p in v.split("."):
        digits = "".join(ch for ch in p if ch.isdigit())
        out.append(int(digits or 0))
    return tuple(out)


def _validate_https(url, allowed_hosts):
    parsed = urlparse(url)
    if parsed.scheme.lower() != "https":
        raise ValueError("PAL-AI updates must use HTTPS.")
    host = (parsed.hostname or "").lower()
    if host not in allowed_hosts:
        raise ValueError(f"Update host is not allowed: {host}")
    return url


def _sha256_file(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest().lower()


def _github_latest_release(repo):
    api_url = f"{GITHUB_API}/repos/{repo}/releases/latest"
    _validate_https(api_url, {"api.github.com"})
    r = requests.get(
        api_url,
        headers={"Accept": "application/vnd.github+json", "User-Agent": "PAL-AI-Updater"},
        timeout=10,
    )
    if r.status_code == 404:
        return None
    r.raise_for_status()
    return r.json()


def check_for_update():
    cfg = load_config()
    up = cfg.get("updater", {})
    if not up.get("enabled", True):
        return {"status": "disabled"}

    repo = str(up.get("github_repo", DEFAULT_REPO)).strip() or DEFAULT_REPO
    release = _github_latest_release(repo)
    if not release:
        return {"status": "no_release"}

    latest = str(release.get("tag_name", "")).strip().lstrip("vV")
    current = current_version()

    if not latest:
        raise ValueError("Latest GitHub release has no version tag.")

    if version_tuple(latest) <= version_tuple(current):
        return {"status": "up_to_date", "current": current, "latest": latest}

    assets = release.get("assets", [])
    zip_asset = None
    sha_asset = None
    for a in assets:
        name = str(a.get("name", ""))
        if name.lower().endswith(".zip") and name.startswith("PAL-AI-"):
            zip_asset = a
        elif name.lower().endswith(".sha256"):
            sha_asset = a

    if not zip_asset or not sha_asset:
        raise ValueError("GitHub release is missing the PAL-AI ZIP or SHA-256 asset.")

    zip_url = zip_asset["browser_download_url"]
    sha_url = sha_asset["browser_download_url"]
    _validate_https(zip_url, {"github.com"})
    _validate_https(sha_url, {"github.com"})

    sha_resp = requests.get(sha_url, timeout=10, headers={"User-Agent": "PAL-AI-Updater"})
    sha_resp.raise_for_status()
    expected = sha_resp.text.strip().split()[0].lower()

    if len(expected) != 64 or any(c not in "0123456789abcdef" for c in expected):
        raise ValueError("GitHub release has an invalid SHA-256 asset.")

    return {
        "status": "update_available",
        "current": current,
        "latest": latest,
        "download_url": zip_url,
        "sha256": expected,
        "notes": release.get("body", "") or release.get("name", "") or ""
    }


def prepare_update(download_url, latest_version, expected_sha256):
    _validate_https(download_url, {"github.com"})

    tmp_root = Path(tempfile.mkdtemp(prefix="palai_update_"))
    zip_path = tmp_root / "update.zip"
    extract_dir = tmp_root / "payload"
    extract_dir.mkdir()

    with requests.get(download_url, stream=True, timeout=90, headers={"User-Agent": "PAL-AI-Updater"}) as r:
        r.raise_for_status()
        with open(zip_path, "wb") as f:
            for chunk in r.iter_content(chunk_size=1024 * 1024):
                if chunk:
                    f.write(chunk)

    actual = _sha256_file(zip_path)
    expected = expected_sha256.lower().strip()
    if actual != expected:
        try:
            zip_path.unlink()
        except Exception:
            pass
        raise ValueError(
            "SECURITY CHECK FAILED: downloaded update SHA-256 does not match GitHub release checksum.\n\n"
            f"Expected: {expected}\n"
            f"Received: {actual}\n\n"
            "The update was NOT installed."
        )

    with zipfile.ZipFile(zip_path, "r") as z:
        z.extractall(extract_dir)

    children = list(extract_dir.iterdir())
    payload = extract_dir
    if len(children) == 1 and children[0].is_dir():
        payload = children[0]

    script = tmp_root / "apply_update.py"
    apply_script = """
from pathlib import Path
import shutil
import time
import subprocess

src = Path({src!r})
dst = Path({dst!r})
preserve = {{"config.json", "data", "knowledge", "screenshots", ".venv"}}

time.sleep(2.0)

for item in src.iterdir():
    if item.name in preserve:
        continue
    target = dst / item.name
    if target.exists():
        if target.is_dir():
            shutil.rmtree(target)
        else:
            target.unlink()
    if item.is_dir():
        shutil.copytree(item, target)
    else:
        shutil.copy2(item, target)

py = dst / ".venv" / "Scripts" / "python.exe"
req = dst / "requirements.txt"
if py.exists() and req.exists():
    subprocess.run([str(py), "-m", "pip", "install", "-r", str(req)], cwd=str(dst), check=False)

launcher = dst / "launcher.py"
pythonw = dst / ".venv" / "Scripts" / "pythonw.exe"
start = dst / "start.bat"

if pythonw.exists() and launcher.exists():
    subprocess.Popen(
        [str(pythonw), str(launcher)],
        cwd=str(dst),
        creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        close_fds=True,
    )
elif start.exists():
    subprocess.Popen(
        ["cmd", "/c", str(start)],
        cwd=str(dst),
        creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        close_fds=True,
    )
""".format(src=str(payload), dst=str(APP_DIR))

    script.write_text(apply_script, encoding="utf-8")
    subprocess.Popen([sys.executable, str(script)], cwd=str(tmp_root))
