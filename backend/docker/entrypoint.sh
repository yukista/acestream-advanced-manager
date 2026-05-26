#!/bin/bash
set -e

ENGINE_PORT=6878
ENGINE_WAIT=60

echo "[entrypoint] Starting Ace Stream engine..."
if [ -x /footy/start-engine ]; then
    /footy/start-engine --client-console &
elif [ -x /opt/acestream/start-engine ]; then
    /opt/acestream/start-engine --client-console &
elif command -v start-engine &>/dev/null; then
    start-engine --client-console &
elif command -v acestreamengine &>/dev/null; then
    acestreamengine --client-console &
else
    echo "[entrypoint] WARNING: Ace Stream engine binary not found"
fi

echo "[entrypoint] Waiting for Ace Stream engine on port $ENGINE_PORT..."
for i in $(seq 1 $ENGINE_WAIT); do
    if curl -sf "http://127.0.0.1:$ENGINE_PORT/webui/api/service?method=get_version" > /dev/null 2>&1; then
        echo "[entrypoint] Ace Stream engine ready after ${i}s"
        break
    fi
    sleep 1
done

echo "[entrypoint] Starting backend: $@"
exec "$@"
