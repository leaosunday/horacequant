# 部署指南

## 生产环境部署

### 方案一：Nginx + 静态文件

#### 1. 构建前端

```bash
cd frontend
npm install
npm run build
```

构建产物在 `dist/` 目录。

#### 2. 配置 Nginx

```nginx
server {
    listen 80;
    server_name your-domain.com;

    # 前端静态文件
    root /path/to/horacequant/frontend/dist;
    index index.html;

    # SPA 路由支持
    location / {
        try_files $uri $uri/ /index.html;
    }

    # API 反向代理
    location /api {
        proxy_pass http://127.0.0.1:8000;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
        
        # 流式接口需要禁用缓冲
        proxy_buffering off;
        proxy_cache off;
    }

    # Gzip 压缩
    gzip on;
    gzip_types text/plain text/css application/json application/javascript text/xml application/xml application/xml+rss text/javascript;
    gzip_vary on;

    # 静态资源缓存
    location ~* \.(js|css|png|jpg|jpeg|gif|ico|svg|woff|woff2|ttf|eot)$ {
        expires 1y;
        add_header Cache-Control "public, immutable";
    }
}
```

#### 3. 重启 Nginx

```bash
sudo nginx -t
sudo systemctl reload nginx
```

### 方案二：Docker 部署

#### 1. 创建 Dockerfile

```dockerfile
# frontend/Dockerfile
FROM node:18-alpine as builder

WORKDIR /app
COPY package*.json ./
RUN npm install
COPY . .
RUN npm run build

FROM nginx:alpine
COPY --from=builder /app/dist /usr/share/nginx/html
COPY nginx.conf /etc/nginx/conf.d/default.conf
EXPOSE 80
CMD ["nginx", "-g", "daemon off;"]
```

#### 2. 创建 nginx.conf

```nginx
# frontend/nginx.conf
server {
    listen 80;
    server_name localhost;
    root /usr/share/nginx/html;
    index index.html;

    location / {
        try_files $uri $uri/ /index.html;
    }

    location /api {
        proxy_pass http://backend:8000;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_buffering off;
    }

    gzip on;
    gzip_types text/plain text/css application/json application/javascript text/xml application/xml;
}
```

#### 3. 构建镜像

```bash
cd frontend
docker build -t horacequant-frontend .
```

#### 4. 运行容器

```bash
docker run -d -p 80:80 --name frontend horacequant-frontend
```

### 方案三：Docker Compose（推荐）

#### docker-compose.yml

```yaml
version: '3.8'

services:
  postgres:
    image: postgres:14
    environment:
      POSTGRES_DB: horace_quant
      POSTGRES_USER: postgres
      POSTGRES_PASSWORD: your_password
    volumes:
      - postgres_data:/var/lib/postgresql/data
    ports:
      - "5432:5432"

  backend:
    build: ./backend
    environment:
      HQ_PG_HOST: postgres
      HQ_PG_PORT: 5432
      HQ_PG_USER: postgres
      HQ_PG_PASSWORD: your_password
      HQ_PG_DB: horace_quant
      HQ_CORS_ENABLED: "true"
    depends_on:
      - postgres
    ports:
      - "8000:8000"

  frontend:
    build: ./frontend
    depends_on:
      - backend
    ports:
      - "80:80"

volumes:
  postgres_data:
```

#### 启动所有服务

```bash
docker-compose up -d
```

## CDN 加速（可选）

### 使用 CDN 托管静态资源

修改 `vite.config.ts`：

```typescript
export default defineConfig({
  build: {
    rollupOptions: {
      output: {
        manualChunks: {
          'echarts': ['echarts'],
          'vue-vendor': ['vue', 'vue-router']
        }
      }
    }
  },
  // 如果使用 CDN
  base: 'https://cdn.your-domain.com/'
})
```

## HTTPS 配置

### 使用 Let's Encrypt

```bash
# 安装 certbot
sudo apt install certbot python3-certbot-nginx

# 获取证书
sudo certbot --nginx -d your-domain.com

# 自动续期
sudo certbot renew --dry-run
```

Nginx 配置会自动更新为 HTTPS。

## 性能优化

### 1. 启用 Brotli 压缩

```nginx
# 安装 nginx-module-brotli
location / {
    brotli on;
    brotli_types text/plain text/css application/json application/javascript;
}
```

### 2. HTTP/2

```nginx
server {
    listen 443 ssl http2;
    # ... 其他配置
}
```

### 3. 预加载关键资源

在 `index.html` 中添加：

```html
<link rel="preload" href="/assets/echarts.js" as="script">
```

## 监控与日志

### Nginx 访问日志

```nginx
access_log /var/log/nginx/horacequant_access.log;
error_log /var/log/nginx/horacequant_error.log;
```

### 前端错误监控（可选）

集成 Sentry 或其他错误监控服务：

```typescript
// main.ts
import * as Sentry from "@sentry/vue"

Sentry.init({
  app,
  dsn: "your-sentry-dsn",
  environment: import.meta.env.MODE
})
```

## 备份策略

### 定期备份数据库

```bash
# 备份脚本
pg_dump -h localhost -U postgres horace_quant > backup_$(date +%Y%m%d).sql

# 恢复
psql -h localhost -U postgres horace_quant < backup_20251229.sql
```

## 常见问题

### Q: 部署后 API 请求 404

**A:** 检查 Nginx 反向代理配置，确保 `/api` 路径正确转发到后端。

### Q: 刷新页面 404

**A:** 确保 Nginx 配置了 `try_files $uri $uri/ /index.html` 支持 SPA 路由。

### Q: 静态资源加载慢

**A:** 
1. 启用 Gzip/Brotli 压缩
2. 配置静态资源缓存
3. 考虑使用 CDN

## 安全建议

1. **HTTPS**: 生产环境必须使用 HTTPS
2. **CORS**: 后端配置正确的 CORS 策略
3. **CSP**: 配置内容安全策略（Content Security Policy）
4. **限流**: 使用 Nginx 限流防止 DDoS

```nginx
# 限流配置
limit_req_zone $binary_remote_addr zone=api:10m rate=10r/s;

location /api {
    limit_req zone=api burst=20;
    # ... 其他配置
}
```

## 更新部署

```bash
# 1. 拉取最新代码
git pull

# 2. 重新构建前端
cd frontend
npm install
npm run build

# 3. 重启服务（如果使用 Docker）
docker-compose restart frontend

# 4. 或重新加载 Nginx
sudo systemctl reload nginx
```

## 回滚

```bash
# 保留上一次构建
mv dist dist.backup
mv dist.new dist

# 如果需要回滚
mv dist dist.failed
mv dist.backup dist
sudo systemctl reload nginx
```

