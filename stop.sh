#!/bin/bash
# 停止工作日志（Streamlit）
cd "$(dirname "$0")"

echo "🛑 正在停止工作日志..."

if [ -f streamlit.pid ]; then
    PID=$(cat streamlit.pid)
    if kill "$PID" 2>/dev/null; then
        echo "✅ 已停止 Streamlit (PID: $PID)"
    else
        echo "⚠️  进程 $PID 已不存在，清理 PID 文件"
    fi
    rm -f streamlit.pid
else
    if pkill -f "streamlit run app.py" 2>/dev/null; then
        echo "✅ 已通过进程名停止 Streamlit"
    else
        echo "ℹ️  没有找到正在运行的 Streamlit 进程"
    fi
fi

echo "完成。"
