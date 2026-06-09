#!/bin/sh
set -e

# Railway 通过 $PORT 路由流量，nginx 需要监听此端口
NGINX_PORT="${PORT:-80}"

# 替换 nginx 配置中的 listen 端口
sed -i "s/listen 80;/listen ${NGINX_PORT};/" /etc/nginx/conf.d/default.conf

# 启动 nginx（守护进程模式）
nginx

# 以非 root 用户运行 uvicorn（安全最佳实践）
# 单 worker：避免多进程 OOM（Railway 内存有限），SQLite WAL 也不需要多进程
# timeout-keep-alive 120s：支持 SSE 长连接
# timeout-graceful-shutdown 30s：优雅关闭
exec gosu appuser uvicorn app.main:app \
  --host 127.0.0.1 --port 8000 \
  --workers 1 \
  --timeout-keep-alive 120 \
  --timeout-graceful-shutdown 30
