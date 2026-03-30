#!/usr/bin/env bash
# Build the MCPB bundle for Claude Desktop 1-click install.
# Requires: npm install -g @anthropic-ai/mcpb
set -euo pipefail

VERSION=$(python -c "import tomllib; print(tomllib.load(open('pyproject.toml','rb'))['project']['version'])")
OUTPUT="fantastical-mcp-${VERSION}.mcpb"

mcpb pack mcpb "$OUTPUT"
echo "Built: $OUTPUT"
