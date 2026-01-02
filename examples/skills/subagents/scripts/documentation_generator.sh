#!/bin/bash

# Documentation Generator - Parallel documentation creation from codebase
# Generates API, architecture, and setup documentation simultaneously

set -e

# Export global settings for all subagents
export YOLO_MODE=1
export MINI_SANDBOX=0
export MAX_RETRIES=10

# Create temp directory for documentation outputs
TEMP_DIR="/tmp/subagent_docs_$(date +%s)"
mkdir -p "$TEMP_DIR"

echo "📚 Launching parallel documentation generation..."

# API Documentation Generator
AICODER_SYSTEM_PROMPT="You are an API DOCUMENTATION SPECIALIST. Focus exclusively on extracting and documenting APIs, endpoints, functions, and their parameters. Create clear, developer-friendly API reference." \
echo "Analyze this codebase and extract all APIs, endpoints, functions, and their parameters. Create comprehensive API documentation that developers can easily understand and use." | python main.py > "$TEMP_DIR/api_documentation.txt" &
PID1=$!

# Architecture Documentation Generator
AICODER_SYSTEM_PROMPT="You are an ARCHITECTURE DOCUMENTATION SPECIALIST. Focus exclusively on design patterns, component relationships, data flow, and system structure. Create architectural overview that helps developers understand the big picture." \
echo "Analyze this codebase architecture. Document the main components, their relationships, design patterns used, data flow, and overall system structure." | python main.py > "$TEMP_DIR/architecture_documentation.txt" &
PID2=$!

# Setup/Installation Documentation Generator
AICODER_SYSTEM_PROMPT="You are a SETUP DOCUMENTATION SPECIALIST. Focus exclusively on installation procedures, dependencies, configuration, and getting started guides. Create clear step-by-step setup instructions." \
echo "Analyze this codebase for setup and installation requirements. Document dependencies, installation steps, configuration options, and getting started instructions." | python main.py > "$TEMP_DIR/setup_documentation.txt" &
PID3=$!

# User Guide Documentation Generator
AICODER_SYSTEM_PROMPT="You are a USER GUIDE SPECIALIST. Focus exclusively on creating user-friendly guides, tutorials, and usage examples. Make the project accessible to new users." \
echo "Analyze this codebase and create user documentation. Include getting started guide, common usage patterns, examples, and troubleshooting tips." | python main.py > "$TEMP_DIR/user_guide.txt" &
PID4=$!

echo "📡 Documentation generators launched (PIDs: $PID1, $PID2, $PID3, $PID4)"
echo "⏳ Waiting for all documentation to complete..."

# Wait for all documentation generators to complete
wait $PID1 $PID2 $PID3 $PID4

echo "✅ Documentation generation completed!"
echo ""
echo "📊 Documentation Results:"
echo "  - API Documentation: $TEMP_DIR/api_documentation.txt"
echo "  - Architecture Documentation: $TEMP_DIR/architecture_documentation.txt"
echo "  - Setup Documentation: $TEMP_DIR/setup_documentation.txt"
echo "  - User Guide: $TEMP_DIR/user_guide.txt"
echo ""

# Generate complete documentation package
cat > "$TEMP_DIR/complete_documentation.md" << EOF
# Complete Project Documentation

Generated on: $(date)
Project directory: $(pwd)

## 📚 API Documentation
$(cat "$TEMP_DIR/api_documentation.txt")

## 🏗️ Architecture Documentation
$(cat "$TEMP_DIR/architecture_documentation.txt")

## ⚙️ Setup & Installation
$(cat "$TEMP_DIR/setup_documentation.txt")

## 👥 User Guide
$(cat "$TEMP_DIR/user_guide.txt")

---

*Documentation generated using subagent parallel processing*
EOF

echo "📋 Complete documentation package: $TEMP_DIR/complete_documentation.md"
echo ""
echo "🔍 Documentation summary:"
echo "  - Total pages: 4"
echo "  - Output directory: $TEMP_DIR"
echo "  - Ready for review and publication"

# Return temp directory path for caller
echo "$TEMP_DIR"