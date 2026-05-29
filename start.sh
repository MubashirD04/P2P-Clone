#!/bin/bash

# Detect available terminal emulator
if command -v gnome-terminal &> /dev/null; then
    TERM_CMD="gnome-terminal --"
elif command -v xterm &> /dev/null; then
    TERM_CMD="xterm -e"
elif command -v konsole &> /dev/null; then
    TERM_CMD="konsole -e"
elif command -v xfce4-terminal &> /dev/null; then
    TERM_CMD="xfce4-terminal -e"
else
    echo "No supported terminal emulator found."
    echo "Install one of: gnome-terminal, xterm, konsole, xfce4-terminal"
    exit 1
fi

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

echo "Starting P2P BitTorrent Clone..."
echo "Using terminal: $TERM_CMD"

# Start tracker first
echo "Starting tracker..."
$TERM_CMD bash -c "cd '$SCRIPT_DIR' && python tracker.py; exec bash" &

# Give tracker time to bind its port before seeder connects
sleep 1

# Start seeder
echo "Starting seeder..."
$TERM_CMD bash -c "cd '$SCRIPT_DIR' && python seeder.py; exec bash" &

sleep 1

# Start leecher
echo "Starting leecher..."
$TERM_CMD bash -c "cd '$SCRIPT_DIR' && python leecher.py; exec bash" &

echo "All components started."
