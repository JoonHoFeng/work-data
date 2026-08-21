#!/usr/bin/env python3
"""Initialize or migrate the worklog SQLite database."""

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from db import DB_PATH, init_db  # noqa: E402


if __name__ == "__main__":
    init_db()
    print(f"数据库已就绪：{DB_PATH}")
