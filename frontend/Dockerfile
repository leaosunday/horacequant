# 构建阶段
FROM node:20 as build-stage

WORKDIR /app

# 复制 package.json 和 package-lock.json
COPY package*.json ./

# 安装依赖
# 使用 --include=dev 确保 vite 等构建工具被安装
RUN npm install

# 复制源代码
COPY . .

# 执行构建
RUN npm run build

# 生产阶段
FROM nginx:stable-alpine as production-stage

# 复制构建产物到 nginx 目录
COPY --from=build-stage /app/dist /usr/share/nginx/html

# 复制自定义 nginx 配置（如果有需要，比如处理 history 模式路由和反向代理）
# 这里我们直接用命令生成一个简单的配置，或者你可以手动创建一个 nginx.conf
RUN echo 'server { \
    listen 80; \
    server_name localhost; \
    \
    location / { \
        root /usr/share/nginx/html; \
        index index.html index.htm; \
        try_files $uri $uri/ /index.html; \
    } \
    \
    location /api { \
        proxy_pass http://backend:8000; \
        proxy_set_header Host $host; \
        proxy_set_header X-Real-IP $remote_addr; \
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for; \
    } \
}' > /etc/nginx/conf.d/default.conf

EXPOSE 80

CMD ["nginx", "-g", "daemon off;"]
