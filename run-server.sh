#!/bin/bash

# Exit on error
set -e

if [ "$#" -lt 1 ]; then
    echo "Usage: ./run-server.sh <window_title_substring> [--codec h264|h265]"
    echo "Example: ./run-server.sh brave --codec h265"
    exit 1
fi

echo "Setting up Python environment with uv..."

# Ensure a virtual environment exists with system site packages (for PyGObject/GStreamer bindings)
if [ ! -d ".venv" ]; then
    uv venv --python /usr/bin/python3 --system-site-packages .venv
fi

# Install dependencies from requirements.txt
uv pip install -r server/requirements.txt

# Run the server
uv run python server/server.py "$@"
