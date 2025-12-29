#!/bin/bash

# Council plugin installation script

set -e

# Council directory is project-specific: .aicoder/council
COUNCIL_DIR=".aicoder/council"
EXAMPLE_DIR="$(dirname "$0")/members"

echo "Installing Council plugin members..."
echo "Target directory: $COUNCIL_DIR"

# Create council directory
mkdir -p "$COUNCIL_DIR"

# Copy member files
if [ -d "$EXAMPLE_DIR" ]; then
    cp "$EXAMPLE_DIR"/*.txt "$COUNCIL_DIR/"
    echo "✓ Member files installed to $COUNCIL_DIR"
else
    echo "✗ Example members directory not found: $EXAMPLE_DIR"
    exit 1
fi

# List installed members
echo ""
echo "Installed council members:"
for file in "$COUNCIL_DIR"/*.txt; do
    if [ -f "$file" ]; then
        basename "$file"
    fi
done

echo ""
echo "Council plugin members installed successfully!"
echo "Use /council list to see available members."
