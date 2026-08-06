#!/bin/bash
# 一键启动工作日志（推荐方式）
# 用法：
#   ./run.sh          # 前台启动（会尝试自动打开浏览器）
#   ./run.sh bg       # 后台启动（推荐用于长期运行）
set -e

cd "$(dirname "$0")"

# 解析参数：是否后台启动
BACKGROUND=false
if [[ "$1" == "bg" || "$1" == "--background" || "$1" == "-b" ]]; then
    BACKGROUND=true
fi

if [ ! -d ".venv" ]; then
    echo "🔧 首次运行：创建虚拟环境..."
    python3 -m venv .venv
    source .venv/bin/activate
    pip install -q -r requirements.txt
else
    source .venv/bin/activate
fi

# 确保数据库存在
if [ ! -f "data/worklog.db" ]; then
    echo "📦 初始化数据库 + 示例数据..."
    python3 scripts/init_db.py
fi

if [ "$BACKGROUND" = true ]; then
    echo "🚀 后台启动 Streamlit..."
    # 使用 venv 内的 Python + 模块方式（最可靠），headless 模式不自动打开浏览器
    nohup .venv/bin/python -m streamlit run app.py \
        --server.headless true \
        --server.port 8501 \
        > streamlit.log 2>&1 &

    echo $! > streamlit.pid
    echo "✅ 已后台启动"
    echo "   PID文件 : streamlit.pid"
    echo "   日志文件: streamlit.log"
    echo "   访问地址: http://localhost:8501"
    echo ""
    echo "停止命令: kill \$(cat streamlit.pid)"
else
    echo "🚀 启动 Streamlit..."
    # 使用 venv 内的 Python 直接以模块方式启动（比依赖 PATH 里的 streamlit 命令更可靠）
    .venv/bin/python -m streamlit run app.py --server.headless false
fi
