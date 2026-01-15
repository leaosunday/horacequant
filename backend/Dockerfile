FROM python:3.12-slim

# 安装 tzdata 以支持时区设置
RUN apt-get update && apt-get install -y --no-install-recommends \
    tzdata \
    gcc \
    python3-dev \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# 复制依赖文件并安装
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# 将当前目录（即 backend/）复制到容器的 /app/backend
COPY . /app/backend/

# 设置 PYTHONPATH 使得 backend 作为一个 package 可被导入
ENV PYTHONPATH=/app

# 暴露端口
EXPOSE 8000

# 启动命令
CMD ["python", "backend/run.py"]
