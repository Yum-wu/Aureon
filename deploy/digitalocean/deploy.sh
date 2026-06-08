#!/bin/bash
# One-click DigitalOcean deployment script
# Usage: ./deploy.sh <droplet-ip> <domain>

set -euo pipefail

DROPLET_IP="${1:?Usage: ./deploy.sh <droplet-ip> <domain>}"
DOMAIN="${2:?Usage: ./deploy.sh <droplet-ip> <domain>}"

echo "=== Aureon DigitalOcean Deployment ==="
echo "Target: $DROPLET_IP ($DOMAIN)"

echo "[1/5] Copying project files..."
rsync -avz --exclude node_modules --exclude .git --exclude __pycache__ \
    ./ root@$DROPLET_IP:/opt/aureon/

echo "[2/5] Building Docker images..."
ssh root@$DROPLET_IP "cd /opt/aureon && docker compose -f deploy/digitalocean/docker-compose.prod.yml build"

echo "[3/5] Starting services..."
ssh root@$DROPLET_IP "cd /opt/aureon && docker compose -f deploy/digitalocean/docker-compose.prod.yml up -d"

echo "[4/5] Setting up SSL with Let's Encrypt..."
ssh root@$DROPLET_IP "certbot --nginx -d $DOMAIN --non-interactive --agree-tos --email admin@$DOMAIN || true"

echo "[5/5] Verifying deployment..."
sleep 10
HTTP_CODE=$(ssh root@$DROPLET_IP "curl -s -o /dev/null -w '%{http_code}' http://localhost:8000/api/health" || echo "000")
if [ "$HTTP_CODE" = "200" ]; then
    echo "=== Deployment successful! ==="
    echo "Frontend: https://$DOMAIN"
    echo "API: https://$DOMAIN/api/"
else
    echo "WARNING: Health check returned $HTTP_CODE"
fi
