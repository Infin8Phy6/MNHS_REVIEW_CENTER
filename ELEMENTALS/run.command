#!/bin/sh
# Open ELEMENTALS on this computer. Double-click to start; Ctrl+C in the terminal to stop.
cd "$(dirname "$0")"
python3 app.py "$@"
