#!/bin/sh
set -eu

start_engine() {
    if [ -x /footy/start-engine ]; then
        /footy/start-engine --client-console
        return
    fi

    if [ -x /opt/acestream/start-engine ]; then
        /opt/acestream/start-engine --client-console
        return
    fi

    if command -v start-engine >/dev/null 2>&1; then
        start-engine --client-console
        return
    fi

    if command -v acestreamengine >/dev/null 2>&1; then
        acestreamengine --client-console
        return
    fi

    echo "Ace Stream engine start command not found" >&2
    exit 1
}

start_engine >/tmp/acestream-engine.log 2>&1 &
ENGINE_PID=$!

python3 - <<'PY'
import socket
import time

deadline = time.time() + 60
while time.time() < deadline:
    try:
        with socket.create_connection(("127.0.0.1", 6878), timeout=1):
            raise SystemExit(0)
    except OSError:
        time.sleep(1)

raise SystemExit("Ace Stream engine did not start on 127.0.0.1:6878 within 60 seconds")
PY

exec "$@"