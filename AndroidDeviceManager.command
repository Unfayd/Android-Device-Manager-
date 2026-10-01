#!/bin/bash
set -e

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$SCRIPT_DIR"

echo "=========================================="
echo " Android Device Manager V5.3"
echo "=========================================="
echo

PYTHON=""

if command -v python3 >/dev/null 2>&1; then
    PYTHON="python3"
elif command -v python >/dev/null 2>&1; then
    PYTHON="python"
fi

if [ -z "$PYTHON" ]; then
    echo "Python 3 was not found."
    echo "Please install Python 3 and run this file again."
    read -r -p "Press Enter to close..."
    exit 1
fi

echo "Using: $PYTHON"
echo "Starting Android Device Manager..."
echo

exec "$PYTHON" "$SCRIPT_DIR/android_device_manager_v5_3.py"
