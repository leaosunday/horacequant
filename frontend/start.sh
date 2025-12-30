#!/bin/bash

# HoraceQuant Frontend 启动脚本
# 使用方法：bash start.sh

echo "================================================"
echo "  HoraceQuant Frontend 启动中..."
echo "================================================"
echo ""

# 检查 node_modules
if [ ! -d "node_modules" ]; then
    echo "⚠️  未找到 node_modules，正在安装依赖..."
    npm install
    echo ""
fi

echo "🚀 启动开发服务器..."
echo ""
echo "📍 访问地址："
echo "   http://localhost:5173"
echo ""
echo "💡 提示："
echo "   - 按 Ctrl+C 停止服务器"
echo "   - 修改代码会自动热重载"
echo "   - 确保后端运行在 http://127.0.0.1:8000"
echo ""

npm run dev

