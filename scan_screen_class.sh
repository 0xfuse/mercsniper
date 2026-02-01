#!/usr/bin/env bash
# 1. Set this to the folder that holds your mods
MODS_DIR="mods"

# 2. Scan every jar in that folder
for jar in "$MODS_DIR"/*.jar; do
    # Grab every class name inside the jar
    if jar tf "$jar" | grep -q 'net/minecraft/client/gui/screens/Screen'; then
        echo "❗️ Class found inside $jar"
        # If you want to see the *exact* path inside the jar, uncomment the next line
        # jar tf "$jar" | grep 'net/minecraft/client/gui/screens/Screen'
    fi

    # ──────────────────────────────────────────────────────────────────────────────
    # Optional: scan nested JARs (mod‑in‑mod) – use unzip -l or zipinfo
    # The following prints any nested jar that contains the class
    if unzip -l "$jar" | grep -q 'net/minecraft/client/gui/screens/Screen'; then
        echo "⚠️  Class also inside a nested jar of $jar"
    fi
done
