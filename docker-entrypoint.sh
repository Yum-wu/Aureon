#!/bin/sh
# 注意：不使用 set -e，手动处理错误以确保日志输出

# Railway 通过 $PORT 路由流量，nginx 需要监听此端口
NGINX_PORT="${PORT:-80}"

echo "[entrypoint] Starting Aureon application..."
echo "[entrypoint] PORT=${NGINX_PORT}"

# 替换 nginx 配置中的 listen 端口
sed -i "s/listen 80;/listen ${NGINX_PORT};/" /etc/nginx/conf.d/default.conf

# 测试 nginx 配置
echo "[entrypoint] Testing nginx config..."
if ! nginx -t 2>&1; then
    echo "[entrypoint] FATAL: nginx config test failed"
    exit 1
fi
echo "[entrypoint] nginx config OK"

# 启动 nginx（守护进程模式）
echo "[entrypoint] Starting nginx on port ${NGINX_PORT}..."
nginx
echo "[entrypoint] nginx started"

# 预检：验证 app.main 可导入
echo "[entrypoint] Pre-checking app.main import..."
if ! python -c "from app.main import app; print('[entrypoint] App loaded successfully')"; then
    echo "[entrypoint] FATAL: app.main import failed"
    exit 1
fi

# 以非 root 用户运行 gunicorn + uvicorn workers（安全最佳实践 + 生产级进程管理）
# 注意：bind 127.0.0.1:8000，由同容器 nginx 反代对外暴露
echo "[entrypoint] Starting gunicorn (uvicorn workers)..."
exec gosu appuser gunicorn app.main:app \
  --worker-class uvicorn.workers.UvicornWorker \
  --workers 2 \
  --bind 127.0.0.1:8000 \
  --timeout 120 \
  --graceful-timeout 30 \
  --max-requests 1000 \
  --max-requests-jitter 100 \
  --access-logfile - \
  --error-logfile -
