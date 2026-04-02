#!/bin/bash

python -m pytest tests/ -v --tb=short --ignore=tests/integration

echo ""
read -t 15 -p "Run integration tests? [y/N]: "
if [[ "$REPLY" =~ [yY] ]]; then
    python -m pytest tests/integration
fi
