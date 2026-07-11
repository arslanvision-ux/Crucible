#!/bin/bash

echo "==================================================="
echo "Crucible VFX Toolkit - Nuke Automatic Installer"
echo "==================================================="
echo ""

NUKE_DIR="$HOME/.nuke"
DEST_DIR="$NUKE_DIR/Crucible"
SRC_DIR="$(dirname "$0")/Crucible"

if [ ! -d "$SRC_DIR" ]; then
    echo "[ERROR] Could not find the Crucible folder next to this installer."
    echo "Please make sure this script is running from the extracted folder."
    exit 1
fi

echo "[INFO] Target .nuke directory: $NUKE_DIR"

# Create .nuke if it doesn't exist
if [ ! -d "$NUKE_DIR" ]; then
    echo "[INFO] Creating .nuke directory..."
    mkdir -p "$NUKE_DIR"
fi

# Copy Crucible folder
echo "[INFO] Copying Crucible files to $DEST_DIR..."
if [ -d "$DEST_DIR" ]; then
    echo "[INFO] Removing old Crucible installation..."
    rm -rf "$DEST_DIR"
fi
cp -R "$SRC_DIR" "$DEST_DIR"

# Update init.py
INIT_FILE="$NUKE_DIR/init.py"
PLUGIN_LINE="nuke.pluginAddPath('./Crucible')"

echo "[INFO] Updating init.py..."
if [ ! -f "$INIT_FILE" ]; then
    echo "$PLUGIN_LINE" > "$INIT_FILE"
    echo "[SUCCESS] Created new init.py and added Crucible path."
else
    if ! grep -qF "$PLUGIN_LINE" "$INIT_FILE"; then
        echo "" >> "$INIT_FILE"
        echo "$PLUGIN_LINE" >> "$INIT_FILE"
        echo "[SUCCESS] Added Crucible path to existing init.py."
    else
        echo "[INFO] Crucible path already exists in init.py."
    fi
fi

echo ""
echo "==================================================="
echo "INSTALLATION COMPLETE!"
echo "You can now launch Nuke. Crucible will be available"
echo "in the Pane menu."
echo "==================================================="
