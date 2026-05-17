#!/bin/bash

if ! python -m pytest tests/ -v --tb=short --ignore=tests/integration; then
    echo "Integration tests interrupted because previous errors... abort..."
    exit 1
fi

echo ""
read -t 15 -p "Run integration tests? [Y/n]: "
ret=$?
if (( ret == 142 )) || [[ ! "$REPLY" =~ [nN] ]]; then
    python -m pytest tests/integration
fi
