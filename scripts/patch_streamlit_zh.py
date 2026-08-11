#!/usr/bin/env python3
"""
把 Streamlit 前端右上角菜单/设置对话框等英文文案替换为中文。
在本地 venv 的 static JS 上打补丁（重装 streamlit 后需再跑一次）。
"""

from __future__ import annotations

import sys
from pathlib import Path

# 精确字符串替换（按出现上下文，避免误伤）
REPLACEMENTS = [
    # 主菜单
    ('label:"Rerun"', 'label:"重新运行"'),
    ('label:"Print"', 'label:"打印"'),
    ('label:"Clear cache"', 'label:"清除缓存"'),
    ('label:"Settings"', 'label:"设置"'),
    ('label:"About"', 'label:"关于"'),
    ('label:"Get help"', 'label:"获取帮助"'),
    ('label:"Report a bug"', 'label:"报告问题"'),
    ('||"Record a screencast"', '||"录制屏幕"'),
    ('COUNTDOWN:"Cancel screencast"', 'COUNTDOWN:"取消录制"'),
    ('RECORDING:"Stop recording"', 'RECORDING:"停止录制"'),
    # 设置对话框（注意 minified 里有空格：]," ","Wide mode"]）
    ('," ","Wide mode"]', '," ","宽屏模式"]'),
    ('," ","Run on save"]', '," ","保存时运行"]'),
    ('AUTO_THEME_NAME="Use system setting"', 'AUTO_THEME_NAME="跟随系统"'),
    ('CUSTOM_THEME_NAME="Custom Theme"', 'CUSTOM_THEME_NAME="自定义主题"'),
    ('title:"Primary color"', 'title:"主色"'),
    ('title:"Background color"', 'title:"背景色"'),
    ('title:"Text color"', 'title:"文字颜色"'),
    ('title:"Secondary background color"', 'title:"次级背景色"'),
    # 页脚
    ("source:`Made with Streamlit ${", "source:`基于 Streamlit ${"),
    # 状态
    ('"Running..."', '"运行中…"'),
    ('"Connecting..."', '"连接中…"'),
    ('"Stop"', '"停止"'),  # 可能较宽，见下方校验
]


def find_streamlit_js_roots() -> list[Path]:
    roots: list[Path] = []
    # 优先当前 venv
    here = Path(__file__).resolve().parent.parent / ".venv"
    candidates = [
        here / "lib",
        Path(sys.prefix) / "lib",
    ]
    for base in candidates:
        if not base.exists():
            continue
        for p in base.glob("python*/site-packages/streamlit/static/static/js"):
            if p.is_dir():
                roots.append(p)
    # 去重
    uniq = []
    seen = set()
    for r in roots:
        s = str(r)
        if s not in seen:
            seen.add(s)
            uniq.append(r)
    return uniq


def patch_file(path: Path) -> int:
    text = path.read_text(encoding="utf-8", errors="ignore")
    original = text

    count = 0
    for old, new in REPLACEMENTS:
        if old == '"Stop"':
            # 仅替换状态栏附近的 Stop 按钮文案，避免误伤
            # Streamlit 里常见: children:"Stop" 或 label:"Stop"
            for frag in ('label:"Stop"', 'children:"Stop"', '>"Stop"<', ',"Stop",'):
                if frag in text:
                    repl = frag.replace("Stop", "停止")
                    n = text.count(frag)
                    text = text.replace(frag, repl)
                    count += n
            continue
        if old in text:
            n = text.count(old)
            text = text.replace(old, new)
            count += n

    if text != original:
        path.write_text(text, encoding="utf-8")
    return count


def main() -> int:
    roots = find_streamlit_js_roots()
    if not roots:
        print("⚠️  未找到 streamlit static/js，跳过中文补丁")
        return 0

    total = 0
    files = 0
    for root in roots:
        for js in root.glob("*.js"):
            # 主包体积大，优先改含 MainMenu 字样的
            try:
                head = js.read_text(encoding="utf-8", errors="ignore")
            except Exception:
                continue
            if 'label:"Rerun"' not in head and 'label:"Clear cache"' not in head and "SCREENCAST_LABEL" not in head:
                # 仍尝试小文件设置相关
                if "Wide mode" not in head and "Run on save" not in head and "Use system setting" not in head:
                    continue
            n = patch_file(js)
            if n:
                files += 1
                total += n
                print(f"  ✅ {js.name}: {n} 处")

    if total:
        print(f"🌐 Streamlit 界面中文补丁完成：{files} 个文件，{total} 处替换")
    else:
        print("🌐 Streamlit 界面中文补丁：无需更新（可能已打过）")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
