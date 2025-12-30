# 快速启动指南

## 第一次运行

### 1. 安装依赖

```bash
cd frontend
npm install
```

### 2. 启动开发服务器

```bash
npm run dev
```

### 3. 访问应用

打开浏览器访问：`http://localhost:5173`

默认路由会重定向到：`/stocks/b1/20251229`

## 修改默认日期

编辑 `src/router/index.ts`：

```typescript
{
  path: '/',
  redirect: '/stocks/b1/20251229'  // 修改这里的日期
}
```

## 后端连接配置

### 开发环境

Vite 已配置代理，自动转发 `/api` 请求到后端：

```typescript
// vite.config.ts
server: {
  proxy: {
    '/api': {
      target: 'http://127.0.0.1:8000',  // 后端地址
      changeOrigin: true
    }
  }
}
```

### 生产环境

构建后需要配置 Nginx 反向代理：

```nginx
location /api {
    proxy_pass http://127.0.0.1:8000;
    proxy_set_header Host $host;
    proxy_set_header X-Real-IP $remote_addr;
}
```

## 构建生产版本

```bash
npm run build
```

构建产物在 `dist/` 目录，可直接部署到任何静态服务器。

## 常见问题

### Q: 页面显示"暂无选股结果"

**A:** 检查以下几点：
1. 后端是否正常运行（`http://127.0.0.1:8000`）
2. 该日期是否已执行选股脚本
3. 浏览器控制台是否有 API 错误

### Q: K线图不显示

**A:** 
1. 检查浏览器控制台是否有 ECharts 错误
2. 确认数据已正确加载（Network 标签查看 API 响应）
3. 尝试切换日K/周K

### Q: 移动端布局异常

**A:** 
1. 确认视口 meta 标签正确（已在 `index.html` 配置）
2. 清除浏览器缓存
3. 使用 Chrome DevTools 的移动设备模拟器测试

## 开发技巧

### 1. 热重载

修改代码后，Vite 会自动热重载，无需手动刷新。

### 2. 查看 API 响应

打开浏览器开发者工具 → Network 标签 → 筛选 XHR/Fetch

### 3. 调试 ECharts

在 `KlineChart.vue` 中添加：

```typescript
console.log('Chart data:', currentData.value)
```

### 4. 修改主题颜色

编辑 `src/assets/theme.css`，修改 CSS 变量。

## 性能优化建议

1. **使用流式接口**：大量数据时使用 `/stream` 接口
2. **分页加载**：避免一次性加载所有股票
3. **图表懒加载**：进入视口时再渲染图表（可选）

## 下一步

- 查看 [README.md](./README.md) 了解完整文档
- 查看 [../README.md](../README.md) 了解后端配置
- 自定义主题和样式
- 添加更多技术指标

