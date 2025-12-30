# HoraceQuant Frontend

基于 Vue 3 + TypeScript + Vite + ECharts 的 A 股量化选股前端应用。

## 技术栈

- **Vue 3** - 渐进式 JavaScript 框架
- **TypeScript** - 类型安全
- **Vite** - 极速开发服务器与构建工具
- **Vue Router** - 路由管理
- **ECharts 5** - 专业级图表库
- **Axios** - HTTP 客户端
- **Day.js** - 轻量级日期处理库

## 功能特性

### 📊 K线图展示
- 日K线 / 周K线切换
- 成交量柱状图
- MACD、KDJ 技术指标
- ZX Short / ZX Long 趋势线
- 支持缩放、拖动、十字光标

### 📱 响应式设计
- **PC端**: 1x2 网格布局（两列展示）
- **移动端**: 1x1 单列布局
- 自适应不同屏幕尺寸

### 🚀 性能优化
- 流式加载（NDJSON）
- 按需分页（cursor-based）
- 图表懒渲染
- 最小化重绘

### 🎨 UI/UX
- 类富途 App 的深色主题
- 流畅的动画过渡
- 清晰的数据展示
- 直观的操作体验

## 快速开始

### 安装依赖

```bash
npm install
```

### 开发模式

```bash
npm run dev
```

默认运行在 `http://localhost:5173`

### 构建生产版本

```bash
npm run build
```

构建产物输出到 `dist/` 目录。

### 预览生产构建

```bash
npm run preview
```

## 项目结构

```
frontend/
├── src/
│   ├── api/              # API 服务层
│   │   └── index.ts      # 后端接口封装
│   ├── assets/           # 静态资源
│   │   └── theme.css     # 主题样式
│   ├── components/       # 组件
│   │   └── KlineChart.vue  # K线图核心组件
│   ├── router/           # 路由配置
│   │   └── index.ts
│   ├── types/            # TypeScript 类型定义
│   │   └── api.ts        # API 数据结构
│   ├── views/            # 页面
│   │   ├── StockList.vue   # 股票列表页
│   │   └── StockDetail.vue # 股票详情页
│   ├── App.vue           # 根组件
│   ├── main.ts           # 入口文件
│   └── style.css         # 全局样式
├── index.html            # HTML 模板
├── package.json          # 依赖配置
├── tsconfig.json         # TypeScript 配置
└── vite.config.ts        # Vite 配置
```

## 核心组件说明

### KlineChart.vue

K线图核心组件，使用 ECharts 渲染。

**Props:**
- `stockCode`: 股票代码
- `stockName`: 股票名称
- `dailyData`: 日K线数据
- `weeklyData`: 周K线数据
- `marketCap`: 市值（可选）

**特性:**
- 自动计算涨跌幅、换手率等指标
- 支持日K/周K切换
- 响应式布局
- 手势操作支持

### StockList.vue

股票列表页面，展示选股结果。

**特性:**
- 流式加载（NDJSON）
- 分页加载更多
- PC端 1x2 布局，移动端 1x1 布局
- 点击卡片跳转详情页

### StockDetail.vue

股票详情页面，展示单个股票完整信息。

**特性:**
- 全屏K线图展示
- 返回列表功能
- 从列表页传递上下文

## API 配置

API 请求通过 Vite 代理转发到后端：

```typescript
// vite.config.ts
export default defineConfig({
  server: {
    proxy: {
      '/api': {
        target: 'http://127.0.0.1:8000',
        changeOrigin: true
      }
    }
  }
})
```

生产环境需要在 Nginx 或其他 Web 服务器配置反向代理。

## 主题定制

主题变量定义在 `src/assets/theme.css`，支持自定义：

```css
:root {
  --bg-primary: #0a0a0a;      /* 主背景色 */
  --color-up: #ee4b4b;        /* 涨色 */
  --color-down: #3dd598;      /* 跌色 */
  --indicator-yellow: #ffd700; /* 指标颜色 */
  /* ... 更多变量 */
}
```

## 浏览器支持

- Chrome / Edge >= 90
- Firefox >= 88
- Safari >= 14
- iOS Safari >= 14
- Android Chrome >= 90

## 常见问题

### 1. API 请求失败

确保后端服务运行在 `http://127.0.0.1:8000`，或修改 `vite.config.ts` 中的代理配置。

### 2. 图表不显示

检查数据是否正确加载，打开浏览器控制台查看错误信息。

### 3. 移动端布局错乱

确认视口 meta 标签正确配置：

```html
<meta name="viewport" content="width=device-width, initial-scale=1.0, maximum-scale=1.0, user-scalable=no" />
```

## 开发建议

1. **性能优化**: 
   - 使用流式接口避免大量数据一次性加载
   - 图表数据变化时避免完全重绘

2. **类型安全**:
   - 严格遵守 TypeScript 类型定义
   - API 响应使用明确的接口类型

3. **代码风格**:
   - 使用 ESLint + Prettier（可选）
   - 组件单一职责原则
   - 合理拆分组件和逻辑

## License

个人项目，默认不提供商业保证。

