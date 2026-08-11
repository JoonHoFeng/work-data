#!/usr/bin/env python3
"""应用根目录解析：开发环境 vs Windows 打包（PyInstaller）。"""

from __future__ import annotations

import sys
from pathlib import Path


def is_frozen() -> bool:
    return bool(getattr(sys, "frozen", False))


def app_base_dir() -> Path:
    """
    用户数据与可写目录（数据库、reports）所在位置。
    - 开发：项目根目录
    - 打包：exe 所在目录
    """
    if is_frozen():
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parent


def bundle_dir() -> Path:
    """
    打包后只读资源所在目录（app.py 等）。
    - 开发：项目根目录
    - 打包：sys._MEIPASS
    """
    if is_frozen() and hasattr(sys, "_MEIPASS"):
        return Path(sys._MEIPASS)
    return Path(__file__).resolve().parent


def ensure_runtime_dirs() -> Path:
    """创建 data/reports/.streamlit，返回 base dir。"""
    base = app_base_dir()
    (base / "data").mkdir(parents=True, exist_ok=True)
    (base / "reports").mkdir(parents=True, exist_ok=True)
    (base / ".streamlit").mkdir(parents=True, exist_ok=True)
    return base
