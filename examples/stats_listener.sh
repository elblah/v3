#!/bin/bash
# Central stats listener - runs stats_server (Unix socket)
# Compiles if needed, then runs the server

[ "${FLOCKER}" != "$0" ] && exec env FLOCKER="$0" flock -en "$0" "$0" "$@" || :

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
SERVER_DIR="$SCRIPT_DIR/stats_server"
SERVER_BIN="$SERVER_DIR/stats_server"

# Compile if needed
if [ ! -x "$SERVER_BIN" ] || [ "$SERVER_DIR/stats_server.c" -nt "$SERVER_BIN" ]; then
    echo "[stats_listener] Compiling stats_server..." >&2
    make -C "$SERVER_DIR"
    if [ $? -ne 0 ]; then
        echo "[stats_listener] Compilation failed" >&2
        exit 1
    fi
fi

# Kill existing server if running
if [ -f /tmp/stats_server.pid ]; then
    OLD_PID=$(cat /tmp/stats_server.pid)
    kill "$OLD_PID" 2>/dev/null
    sleep 0.2
fi

# Run server
echo "[stats_listener] Starting stats_server..." >&2
"$SERVER_BIN" &
echo $! > /tmp/stats_server.pid
echo "[stats_listener] PID: $(cat /tmp/stats_server.pid)" >&2
