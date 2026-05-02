#!/bin/bash
# Central stats listener - runs persistently, appends to central log

[ "${FLOCKER}" != "$0" ] && exec env FLOCKER="$0" flock -en "$0" "$0" "$@" || :

FIFO="$TMP/stats_logger.fifo"
LOG="$HOME/.aicoder/central_stats.log"

mkdir -p "$(dirname "$LOG")"
echo "[stats_listener] Listening on $FIFO" >&2
echo "[stats_listener] Writing to $LOG" >&2

while true; do
    if [ -p "$FIFO" ]; then
        cat "$FIFO" >> "$LOG"
    else
        sleep 0.5
    fi
done
