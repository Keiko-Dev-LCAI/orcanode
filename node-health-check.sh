#!/bin/bash
echo "========== LIGHTCHAIN NODE HEALTH CHECK =========="
echo "Time: $(date)"
echo ""

echo "=== SERVICE STATUS ==="
for svc in lightchain-worker ollama redis-server contract-explainer cloudflared-tunnel; do
  status=$(systemctl is-active $svc 2>/dev/null)
  echo "  $svc: $status"
done

echo ""
echo "=== DOCKER CONTAINER ==="
docker ps --filter name=lightchain-worker --format "  Name: {{.Names}}  Status: {{.Status}}  Running: {{.RunningFor}}" 2>/dev/null
docker ps -a --filter name=lightchain-worker --format "  (all) {{.Names}} - {{.Status}}" 2>/dev/null

echo ""
echo "=== OLLAMA MODELS ==="
curl -s http://127.0.0.1:11434/api/tags 2>/dev/null | python3 -c "
import sys, json
data = json.load(sys.stdin)
for m in data.get('models', []):
    print(f\"  {m['name']}\")
" 2>/dev/null || echo "  Could not reach Ollama"

echo ""
echo "=== WORKER METRICS ==="
docker exec lightchain-worker wget -qO- http://127.0.0.1:9101/metrics 2>/dev/null | grep -E "worker_jobs|worker_heartbeat|worker_ollama|worker_redis|worker_release_reconcile" | head -20

echo ""
echo "=== RECENT WORKER LOGS (last 30 lines) ==="
journalctl -u lightchain-worker.service --no-pager -n 30 2>/dev/null

echo ""
echo "=================================================="
