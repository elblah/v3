#!/bin/bash
# Migrate all .aicoder/stats.log files to central log

CENTRAL="$HOME/.aicoder/central_stats.log"
TMP_MERGE="/tmp/stats_merge_$$.log"
SEARCH_PATHS="$HOME $HOME/storage/"

echo "Scanning for stats.log files..."
for path in $SEARCH_PATHS; do
    if [ -d "$path" ]; then
        find "$path" -name "stats.log" -path "*/.aicoder/*" 2>/dev/null | while read f; do
            echo "  Found: $f"
            project=$(cd "$(dirname "$f")/.." && pwd)
            while IFS= read -r line; do
                echo "$project|$line" >> "$TMP_MERGE"
            done < "$f"
        done
    fi
done

if [ -f "$TMP_MERGE" ]; then
    cat "$TMP_MERGE" >> "$CENTRAL"
    rm "$TMP_MERGE"
    sort -u "$CENTRAL" -o "$CENTRAL"
    echo "Done. Central now has $(wc -l < "$CENTRAL") entries"
else
    echo "No stats.log files found"
fi