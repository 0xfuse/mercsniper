#!/usr/bin/env bash
# find_problem_mod.sh
#
#   *   Disable all mods.
#   *   Enable each one, run the server once, look for a known crash string.
#   *   If that string appears, print the offending mod and exit.
#   *   If the first run shows missing dependencies, enable those mods,
#       re‑run the server, and see if the crash string appears.
#   *   Keep a single, comprehensive trace file (server_log.txt) that is
#       overwritten before each run.
#
# -------------------------------------------------------------------------

# -------------------------------------------------------------------------
# 1.  General configuration -------------------------------------------------
# -------------------------------------------------------------------------

# Path to the server launcher script (without leading './')
SERVER_SCRIPT="start.sh"          # <-- adjust to your actual script name

# Expected error string that signals a crash caused by a mod
ERROR_STR="Attempted to load class net/minecraft/client/gui/Gui for invalid dist DEDICATED_SERVER" # string that signals *the* crash we care about

# Timeout (in seconds) for a single server run
TIMEOUT=10

# Directory that contains all mod jars
MODS_DIR="mods"

get_modid_from_jar() {
  local jar="$1"

  # locate the metadata file (mods.toml or mod.json)
  local meta
  meta=$(unzip -l "$jar" | grep -E 'META-INF/(mods\.toml|mod\.json)' |
         awk '{print $4}' | head -n1)

  [[ -z $meta ]] && return 1   # nothing found → no output

  # extract the raw content of that file
  local content
  content=$(unzip -p "$jar" "$meta")

  # pull the first modId that appears
  local modid
  modid=$((echo "$content" | \
          grep -Eo 'modId\s*=\s*[^ ]+' || \
          grep -Eo '"modId"\s*:\s*"[^"]+"') | head -n1)

  # clean up the captured value
  modid=$(echo "$modid" | awk -F'=' '{gsub(/^[ \t]+|[ \t]+$/, "", $2); gsub(/["'\'']/, "", $2); print $2}')

  echo "$modid"
}

# 2.3  Disable a single jar
# -------------------------------------------------------------------------
disable_mod() {
    local f="$1"
    mv -- "$f" "${f%.jar}.jar.disabled"
}

# 2.4  Enable a single jar
# -------------------------------------------------------------------------
enable_mod() {
    local f="$1"
    mv -- "$f.disabled" "$f" 
}

# 2.5  Disable all jars (rename *.jar → *.jar.disabled)
# -------------------------------------------------------------------------
disable_all() {
    while read -r f; do
        mv -- "$f" "${f%.jar}.jar.disabled" 2>/dev/null
    done < <(find "$MODS_DIR" -maxdepth 1 -type f -name '*.jar')
}

# 2.5  Enable all jars (rename *.jar.disabled → *.jar)
# -------------------------------------------------------------------------
enable_all() {
    while read -r f; do
        # rename /path/ModName.jar.disabled  →  /path/ModName.jar
        mv -- "$f" "${f%.jar.disabled}.jar" 2>/dev/null
    done < <(
        # find all the disabled jars in the mods directory
        find "$MODS_DIR" -maxdepth 1 -type f -name '*.jar.disabled'
    )
}

# 2.6  Reset the log file (truncate)
# -------------------------------------------------------------------------
reset_log() { : > "$LOG_FILE"; }

# 2.7  Extract missing dependency mod ids from the log
# -------------------------------------------------------------------------
extract_missing_ids() {
    mods_id=$(grep -zPo "Mod ID: '\K[^']+" "$1" | xargs -0 echo -n)
    echo -n $mods_id
}

find_mod_by_id() {
  local target_id="$1"

  while read -r jar; do
    # Grab the first modId from this jar
    local modid
    modid=$(get_modid_from_jar "$jar") || continue   # skip if we can't read it
    
    if [ "$modid" = "$target_id" ]; then
      echo "$jar"          # one match – we can exit early or continue for all
      return 0
    fi

  done < <(find "$MODS_DIR" -maxdepth 1 -type f -name '*.jar*')

  return 1   # no jar matched the id
}

# -------------------------------------------------------------------------
# 3.  Main script
# -------------------------------------------------------------------------

enable_all

MODS=$(find "$MODS_DIR" -maxdepth 1 -type f -name '*.jar')
TOTAL=$(printf '%s\n' "$MODS" | wc -l | tr -d ' ')
echo "Found $TOTAL mod(s)."

# Disable everything first
disable_all
echo "All mods disabled. Starting test loop."

LOG_FILE="server_log.txt"      # comprehensive trace file

i=1
while read -r mod; do
    mod_name=$(basename "$mod")
    echo -e "\n[$i/$TOTAL] Enabling $mod_name..."

    # Enable the candidate mod
    enable_mod "$mod"

    # 3.1  First run – no missing deps yet
    reset_log
    timeout "$TIMEOUT" ./"$SERVER_SCRIPT" >> "$LOG_FILE" 2>&1
    exit_code=$?
    if (( exit_code == 124 )); then
        echo "   [I]  Server timed out - skipping this mod."
        disable_mod "$mod"
        ((i++))
        continue
    fi

    sleep 2   # let the server flush

    # 3.2  Crash string check
    if grep -q "$ERROR_STR" "$LOG_FILE"; then
        echo -e "\n[X]  Crash caused by $(realpath "$mod")"
        exit 0
    fi

    # 3.3  Handle missing deps
    missing=$(extract_missing_ids "$LOG_FILE")
    if [[ -n "$missing" ]]; then
        echo "   [W]  Missing deps: $missing"

        temp=()
        for dep in ${missing}; do
            echo "Searching missing dep '$dep' ..."
            jar=$(find_mod_by_id "$dep")
            enabled_jar=$(basename "$jar" '.disabled')
            if [[ -z "$enabled_jar" ]]; then
                echo "   [W]  Cannot find jar for missing mod '$dep'"
                continue
            fi
            enable_mod "$enabled_jar"
            temp+=("$enabled_jar")
        done <<< "$missing"

        # Re‑run after enabling missing deps
        reset_log
        timeout "$TIMEOUT" ./"$SERVER_SCRIPT" >> "$LOG_FILE" 2>&1
        sleep 2

        if grep -q "$ERROR_STR" "$LOG_FILE"; then
            echo -e "\n[X]  Crash caused by $(realpath "$mod")"
            for j in "${temp[@]}"; do disable_mod "$j"; done
            disable_mod "$mod"
            exit 0
        fi

        # Disable temporarily enabled jars
        for j in "${temp[@]}"; do disable_mod "$j"; done
    fi

    echo "   $mod_name tested"

    echo "   [X]  Crash string not found."
    disable_mod "$mod"
    ((i++))
done <<< "$MODS"

echo "Checked $(($i - 1)) mods."
echo "No offending mod found."

