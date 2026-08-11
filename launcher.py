#!/usr/bin/env python3
"""
Windows 双击启动入口（也可开发态：python launcher.py）。

打包后：
  - 可执行文件旁会生成 data/、reports/
  - 自动打开浏览器访问本地 Streamlit
  - 关闭本控制台窗口即停止服务
"""

from __future__ import annotations

import os
import socket
import sys
import threading
import time
import webbrowser
from pathlib import Path


def _base_dir() -> Path:
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parent


def _bundle_dir() -> Path:
    if getattr(sys, "frozen", False) and hasattr(sys, "_MEIPASS"):
        return Path(sys._MEIPASS)
    return Path(__file__).resolve().parent


def _find_free_port(start: int = 8501, end: int = 8599) -> int:
    for port in range(start, end + 1):
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            try:
                s.bind(("127.0.0.1", port))
                return port
            except OSError:
                continue
    return start


def _open_browser(url: str, delay: float = 1.5) -> None:
    def _run():
        time.sleep(delay)
        try:
            webbrowser.open(url)
        except Exception:
            pass

    threading.Thread(target=_run, daemon=True).start()


def main() -> int:
    base = _base_dir()
    bundle = _bundle_dir()
    os.chdir(base)

    # 可写目录
    (base / "data").mkdir(exist_ok=True)
    (base / "reports").mkdir(exist_ok=True)
    (base / ".streamlit").mkdir(exist_ok=True)

    # 首次从包内复制 streamlit 配置
    cfg_src = bundle / ".streamlit" / "config.toml"
    cfg_dst = base / ".streamlit" / "config.toml"
    if cfg_src.is_file() and not cfg_dst.is_file():
        try:
            cfg_dst.write_bytes(cfg_src.read_bytes())
        except OSError:
            pass

    sys.path.insert(0, str(bundle))
    sys.path.insert(0, str(base))

    app_py = bundle / "app.py"
    if not app_py.is_file():
        app_py = base / "app.py"
    if not app_py.is_file():
        print("错误：找不到 app.py")
        input("按回车退出…")
        return 1

    port = int(os.environ.get("WORKLOG_PORT", "0")) or _find_free_port()
    url = f"http://127.0.0.1:{port}"

    print("=" * 50)
    print("  工作日志 Worklog")
    print(f"  访问地址: {url}")
    print("  关闭本窗口即可停止程序")
    print("=" * 50)

    # 延迟打开浏览器
    _open_browser(url)

    # 以编程方式启动 Streamlit（兼容打包）
    from streamlit.web import bootstrap
    from streamlit import config as st_config

    flag_options = {
        "server.port": port,
        "server.address": "127.0.0.1",
        "server.headless": True,
        "browser.gatherUsageStats": False,
        "global.developmentMode": False,
    }
    # 写入配置
    for key, val in flag_options.items():
        try:
            st_config.set_option(key, val)
        except Exception:
            pass

    # Streamlit 1.50: run(main_script_path, is_hello, args, flag_options)
    bootstrap.run(str(app_py), False, [], flag_options)
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except KeyboardInterrupt:
        print("\n已停止。")
        raise SystemExit(0)
    except Exception as e:
        print(f"\n启动失败: {e}")
        import traceback
        traceback.print_exc()
        try:
            input("\n按回车退出…")
        except Exception:
            pass
        raise SystemExit(1)
