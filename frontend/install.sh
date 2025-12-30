#!/bin/bash

# HoraceQuant Frontend 安装脚本
# 使用方法：bash install.sh

set -e

echo "================================================"
echo "  HoraceQuant Frontend 安装脚本"
echo "================================================"
echo ""

# 检查 Node.js
echo "📦 检查 Node.js..."
if ! command -v node &> /dev/null; then
    echo "❌ 未找到 Node.js，请先安装 Node.js 18+"
    echo "   下载地址：https://nodejs.org/"
    exit 1
fi

NODE_VERSION=$(node -v | cut -d'v' -f2 | cut -d'.' -f1)
if [ "$NODE_VERSION" -lt 18 ]; then
    echo "⚠️  Node.js 版本过低（当前：$(node -v)），建议使用 18+"
fi

echo "✅ Node.js 版本：$(node -v)"
echo ""

# 检查 npm
echo "📦 检查 npm..."
if ! command -v npm &> /dev/null; then
    echo "❌ 未找到 npm"
    exit 1
fi
echo "✅ npm 版本：$(npm -v)"
echo ""

# 安装依赖
echo "📦 安装依赖..."
npm install

echo ""
echo "================================================"
echo "  ✅ 安装完成！"
echo "================================================"
echo ""
echo "🚀 启动开发服务器："
echo "   npm run dev"
echo ""
echo "🏗️  构建生产版本："
echo "   npm run build"
echo ""
echo "📚 查看文档："
echo "   README.md - 项目文档"
echo "   QUICKSTART.md - 快速启动"
echo "   DEMO.md - 演示指南"
echo ""
echo "🌐 访问地址（启动后）："
echo "   http://localhost:5173"
echo ""

