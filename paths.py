"""Runtime paths for source and systemd deployments."""

from pathlib import Path


def app_base_dir() -> Path:
    return Path(__file__).resolve().parent


def ensure_runtime_dirs() -> Path:
    base = app_base_dir()
    (base / "data").mkdir(parents=True, exist_ok=True)
    (base / "reports").mkdir(parents=True, exist_ok=True)
    return base
