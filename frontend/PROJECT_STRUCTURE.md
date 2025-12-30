# 项目结构说明

## 目录树

```
frontend/
├── public/                    # 公共静态资源（可选）
├── src/                       # 源代码
│   ├── api/                   # API 服务层
│   │   └── index.ts          # 后端接口封装、流式加载实现
│   ├── assets/               # 静态资源
│   │   └── theme.css         # 主题变量和全局样式
│   ├── components/           # 可复用组件
│   │   └── KlineChart.vue    # K线图核心组件（ECharts）
│   ├── router/               # 路由配置
│   │   └── index.ts          # Vue Router 配置
│   ├── types/                # TypeScript 类型定义
│   │   └── api.ts            # API 数据结构类型
│   ├── views/                # 页面组件
│   │   ├── StockList.vue     # 股票列表页（流式加载）
│   │   └── StockDetail.vue   # 股票详情页（全屏图表）
│   ├── App.vue               # 根组件
│   ├── main.ts               # 应用入口
│   └── style.css             # 全局基础样式
├── index.html                # HTML 模板
├── package.json              # 依赖配置
├── tsconfig.json             # TypeScript 配置
├── tsconfig.node.json        # Node 环境 TS 配置
├── vite.config.ts            # Vite 构建配置
├── README.md                 # 项目文档
├── QUICKSTART.md             # 快速启动指南
├── DEPLOY.md                 # 部署指南
└── PROJECT_STRUCTURE.md      # 本文件
```

## 核心文件详解

### 配置文件

#### `package.json`
- 项目依赖管理
- 核心依赖：Vue 3、Vue Router、ECharts、Axios、Day.js
- 脚本命令：dev（开发）、build（构建）、preview（预览）

#### `vite.config.ts`
- Vite 构建工具配置
- 路径别名：`@` -> `./src`
- 开发服务器代理：`/api` -> `http://127.0.0.1:8000`

#### `tsconfig.json`
- TypeScript 编译配置
- 严格模式、ES2020 目标
- 路径映射支持

### 源码文件

#### `src/main.ts`
应用入口文件：
- 创建 Vue 应用实例
- 注册路由插件
- 挂载到 DOM

#### `src/App.vue`
根组件：
- 简单的路由视图容器
- 全局背景样式

#### `src/router/index.ts`
路由配置：
- `/` - 重定向到默认选股结果
- `/stocks/:ruleName/:tradeDate` - 股票列表页
- `/stock/:code` - 股票详情页

#### `src/api/index.ts`
API 服务层：
- Axios 实例配置（拦截器、超时）
- `fetchPicks()` - 获取选股结果（普通接口）
- `fetchPicksStream()` - 流式获取（NDJSON）
- 支持分页、游标

#### `src/types/api.ts`
TypeScript 类型定义：
- `ApiResponse<T>` - 统一响应格式
- `KlinePoint` - K线数据点
- `PickBundleItem` - 单个股票完整数据
- `PicksBundle` - 选股结果集合
- `StreamMessage` - 流式消息类型

#### `src/components/KlineChart.vue`
K线图核心组件：

**Props:**
- `stockCode` - 股票代码（如 "002456"）
- `stockName` - 股票名称（如 "欧菲光"）
- `dailyData` - 日K线数据数组
- `weeklyData` - 周K线数据数组
- `marketCap` - 总市值（可选）

**功能:**
- 股票信息头部（代码、名称、状态）
- 价格信息区（当前价、涨跌、最高最低、换手率等）
- 日K/周K切换
- ECharts 图表：
  - 主图：K线 + ZX Short + ZX Long
  - 副图1：成交量
  - 副图2：MACD（DIF、DEA、HIST）
  - 副图3：KDJ（K、D、J）
- 缩放、拖动、十字光标
- 响应式布局

**样式特点:**
- 深色主题（类富途）
- 涨红跌绿
- 清晰的数据展示
- 移动端适配

#### `src/views/StockList.vue`
股票列表页：

**功能:**
- 顶部导航（策略名、交易日期）
- 流式加载股票数据（NDJSON）
- 网格布局展示K线卡片
- 加载更多（分页）
- 点击卡片跳转详情页
- 空状态提示

**布局:**
- PC端：2列网格（1x2）
- 移动端：1列（1x1）

**性能优化:**
- 流式加载，边拉边画
- 游标分页，避免重复数据

#### `src/views/StockDetail.vue`
股票详情页：

**功能:**
- 返回列表按钮
- 全屏K线图展示
- 从列表页传递上下文（ruleName、tradeDate）

**用途:**
- 查看单个股票完整图表
- 更大的展示空间

#### `src/style.css`
全局基础样式：
- CSS Reset
- 字体配置
- 滚动条样式
- 基础布局

#### `src/assets/theme.css`
主题变量：
- CSS 变量定义（颜色、圆角、阴影等）
- 工具类（涨跌色、响应式）
- 统一视觉风格

## 数据流

```
用户访问 /stocks/b1/20251229
    ↓
StockList.vue 加载
    ↓
调用 fetchPicksStream()
    ↓
流式接收 NDJSON 数据
    ↓
逐个渲染 KlineChart 组件
    ↓
ECharts 绘制图表
```

## 组件通信

```
StockList.vue
    ├─ props ─→ KlineChart.vue (股票数据)
    └─ router.push() ─→ StockDetail.vue (跳转传参)

StockDetail.vue
    ├─ route.query ─→ 获取上下文（ruleName、tradeDate）
    └─ fetchPicks() ─→ 重新加载数据
```

## 响应式设计

### 断点

- **移动端**: `max-width: 768px`
- **平板**: `769px ~ 1023px`
- **PC端**: `min-width: 1024px`

### 布局策略

- **StockList**: 
  - PC: `grid-template-columns: repeat(2, 1fr)`
  - 移动: `grid-template-columns: 1fr`

- **KlineChart**:
  - PC: 完整信息展示
  - 移动: 精简信息、调整字号

## 性能考虑

### 1. 流式加载
- 使用 NDJSON 流式接口
- 避免一次性加载大量数据
- 提升首屏渲染速度

### 2. 分页策略
- 基于游标的分页（cursor-based）
- 每页 10-20 条（可配置）
- "加载更多"按钮

### 3. 图表优化
- ECharts `animation: false` 禁用动画
- 数据变化时局部更新
- ResizeObserver 响应式调整

### 4. 代码分割
- Vue Router 懒加载（可选）
- ECharts 按需引入（可选）

## 扩展建议

### 1. 添加更多技术指标
在 `KlineChart.vue` 中扩展：
- BOLL（布林带）
- RSI（相对强弱指标）
- MA（移动平均线）

### 2. 实时数据更新
- WebSocket 连接
- 定时轮询
- 服务端推送

### 3. 用户偏好
- 保存图表设置（周期、指标）
- 自选股列表
- 主题切换（深色/浅色）

### 4. 数据导出
- 导出选股结果（CSV、Excel）
- 图表截图
- 分享功能

### 5. 移动端手势
- 双指缩放
- 左右滑动切换股票
- 下拉刷新

## 开发规范

### 命名约定
- 组件：PascalCase（如 `KlineChart.vue`）
- 文件：kebab-case 或 PascalCase
- 变量/函数：camelCase
- 常量：UPPER_SNAKE_CASE

### 代码风格
- 使用 TypeScript 严格模式
- Props 使用 `defineProps<T>()`
- Emits 使用 `defineEmits<T>()`
- 组合式 API（Composition API）

### Git 提交
- feat: 新功能
- fix: 修复
- style: 样式调整
- refactor: 重构
- docs: 文档
- perf: 性能优化

## 故障排查

### 图表不显示
1. 检查数据格式是否正确
2. 查看浏览器控制台错误
3. 确认 ECharts 正确初始化

### API 请求失败
1. 检查后端是否运行
2. 查看 Network 标签
3. 确认代理配置正确

### 样式错乱
1. 清除浏览器缓存
2. 检查 CSS 变量是否加载
3. 确认响应式断点

## 相关文档

- [README.md](./README.md) - 完整项目文档
- [QUICKSTART.md](./QUICKSTART.md) - 快速启动指南
- [DEPLOY.md](./DEPLOY.md) - 部署指南
- [Vue 3 文档](https://cn.vuejs.org/)
- [ECharts 文档](https://echarts.apache.org/zh/index.html)
- [Vite 文档](https://cn.vitejs.dev/)

