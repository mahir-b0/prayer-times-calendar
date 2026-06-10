#!/bin/bash

SCRIPT_DIR="$HOME/prayer-times-calendar"
VENV_DIR="$SCRIPT_DIR/.venv"

echo "Creating venv..."
python3 -m venv "$VENV_DIR"

echo "Installing dependencies..."
"$VENV_DIR/bin/pip" install -q requests beautifulsoup4 icalendar pytz playwright

echo "Installing Playwright browsers..."
"$VENV_DIR/bin/playwright" install chromium

echo "Running script..."
"$VENV_DIR/bin/python" "$SCRIPT_DIR/prayer_times.py"

echo "Destroying venv..."
rm -rf "$VENV_DIR"

echo "Done!"
