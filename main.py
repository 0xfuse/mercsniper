#!/usr/bin/env python3

#
# MIT License
#
# Copyright (c) 2026 0xfuse
#
# Permission is hereby granted, free of charge, to any person obtaining a copy
# of this software and associated documentation files (the "Software"), to deal
# in the Software without restriction, including without limitation the rights
# to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
# copies of the Software, and to permit persons to whom the Software is
# furnished to do so, subject to the following conditions:
#
# The above copyright notice and this permission notice shall be included in all
# copies or substantial portions of the Software.
#
# THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
# IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
# FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
# AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
# LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
# OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
# SOFTWARE.
#

import pathlib
import subprocess
import re
import time
import zipfile
import os
from typing import Iterable, List, Optional

# ---------- CONFIGURATION -------------- #
# Expand the user directory to an absolute path for all file operations.
SERVER_ROOT = "~/forge_server"
SERVER_ROOT_ABS = os.path.expanduser(SERVER_ROOT)  # absolute path to the server directory
SERVER_SCRIPT = "start.sh"              # script name inside SERVER_ROOT
ERROR_STR = "Attempted to load class net/minecraft/client/gui/Gui for invalid dist DEDICATED_SERVER"
TIMEOUT = 10
MODS_DIR = "mods"                       # sub‑dir inside SERVER_ROOT
LOG_FILE = "server_log.txt"             # log file inside SERVER_ROOT
# -------------------------------------- #

# ---------- HELPERS -------------- #
def get_modid_from_jar(jar_path):
    """Return the `modId` string that is stored in either
    META‑INF/mods.toml or META‑INF/mod.json.
    """
    jar_path = pathlib.Path(jar_path)
    try:
        with zipfile.ZipFile(jar_path, "r") as z:
            meta_files = [
                f for f in z.namelist()
                if f.startswith("META-INF/") and (f.endswith("mods.toml") or f.endswith("mod.json"))
            ]
            if not meta_files:
                return None
            meta = meta_files[0]
            content = z.read(meta).decode("utf-8", errors="ignore")
            m = re.search(r"modId\s*=\s*([^\s]+)", content)
            if m:
                return m.group(1).strip().strip('"').strip("'")
            m = re.search(r'"modId"\s*:\s*"([^"]+)"', content)
            if m:
                return m.group(1).strip()
    except Exception as e:
        print(f"[DEBUG] Failed to read modId from {jar_path}: {e}")
    return None

def disable_mod(mod_path):
    """Rename `something.jar` → `something.jar.disabled`."""
    p = pathlib.Path(mod_path)
    if p.suffix == ".jar":
        new = p.with_name(p.name + ".disabled")
        try:
            p.rename(new)
            print(f"[DEBUG] Disabled {p}")
        except Exception as e:
            print(f"[DEBUG] Could not disable {p}: {e}")

def enable_mod(mod_path):
    """Rename `something.jar.disabled` → `something.jar`."""
    p = pathlib.Path(mod_path)
    if p.name.endswith(".jar.disabled"):
        new = p.with_name(p.name.replace(".jar.disabled", ".jar"))
        try:
            p.rename(new)
            print(f"[DEBUG] Enabled {p}")
        except Exception as e:
            print(f"[DEBUG] Could not enable {p}: {e}")

def disable_all():
    """Disable every *.jar in MODS_DIR."""
    for p in pathlib.Path(os.path.join(SERVER_ROOT_ABS, MODS_DIR)).glob("*.jar"):
        disable_mod(str(p))

def enable_all():
    """Enable every *.jar.disabled in MODS_DIR."""
    for p in pathlib.Path(os.path.join(SERVER_ROOT_ABS, MODS_DIR)).glob("*.jar.disabled"):
        enable_mod(str(p))

def reset_log():
    """Truncate the log file – it will be written to again."""
    log_path = pathlib.Path(os.path.join(SERVER_ROOT_ABS, LOG_FILE))
    try:
        log_path.write_text("")
        print(f"[DEBUG] Reset log {log_path}")
    except Exception as e:
        print(f"[DEBUG] Could not reset log {log_path}: {e}")

def extract_missing_ids(log_path):
    """Return a list of *mod IDs* that appear in the log."""
    missing = []
    try:
        content = pathlib.Path(log_path).read_text(errors="ignore")
        for match in re.finditer(r"Mod ID: '([^']+)'", content):
            missing.append(match.group(1))
    except Exception as e:
        print(f"[DEBUG] Failed to read log {log_path}: {e}")
    return missing

def find_mod_by_id(target_id):
    """Return the first JAR that contains the requested modId."""
    for p in pathlib.Path(os.path.join(SERVER_ROOT_ABS, MODS_DIR)).glob("*.jar*"):
        modid = get_modid_from_jar(str(p))
        if modid == target_id:
            return str(p)
    return None

def run_server():
    """Execute the server start script, write stdout+stderr to LOG_FILE."""
    log_path = pathlib.Path(os.path.join(SERVER_ROOT_ABS, LOG_FILE))
    try:
        with log_path.open("w") as log_f:
            print(f"[DEBUG] Running server script {SERVER_SCRIPT} in {SERVER_ROOT_ABS}")
            result = subprocess.run(
                [f"./{SERVER_SCRIPT}"],
                cwd=SERVER_ROOT_ABS,
                stdout=log_f,
                stderr=log_f,
                timeout=TIMEOUT,
                text=True,
            )
        print(f"[DEBUG] Server exited with code {result.returncode}")
        return result.returncode
    except subprocess.TimeoutExpired:
        print(f"[DEBUG] Server timed out after {TIMEOUT}s")
        return 124
    except Exception as e:
        print(f"[DEBUG] Failed to run server: {e}")
        return 1

# ---------- MAIN -------------- #
def main():
    print("[DEBUG] Starting mod‑crash‑finder")
    enable_all()  # restore the original state
    mods = [str(p) for p in pathlib.Path(os.path.join(SERVER_ROOT_ABS, MODS_DIR)).glob("*.jar")]
    total = len(mods)

    print(f"[DEBUG] Found {total} mod(s).")
    disable_all()
    print("[DEBUG] All mods disabled. Starting test loop.")

    for idx, mod in enumerate(mods, start=1):
        mod_name = os.path.basename(mod)
        print(f"\n[{idx}/{total}] Enabling {mod_name}...")

        enable_mod(mod)                 # enable this mod
        reset_log()

        exit_code = run_server()
        if exit_code == 124:            # timed out
            print("   [I] Server timed out – skipping this mod.")
            disable_mod(mod)
            continue

        time.sleep(2)                   # give the server a moment to finish

        log_path = pathlib.Path(os.path.join(SERVER_ROOT_ABS, LOG_FILE))
        try:
            log_content = log_path.read_text(errors="ignore")
        except Exception as e:
            print(f"[DEBUG] Could not read log {log_path}: {e}")
            log_content = ""

        if ERROR_STR in log_content:
            print(f"\n[X] Crash caused by {mod}")
            return

        missing = extract_missing_ids(log_path)
        if missing:
            print(f"   [W] Missing deps: {' '.join(missing)}")
            temp_jars = []

            for dep in missing:
                print(f"Searching missing dep '{dep}' …")
                jar = find_mod_by_id(dep)
                if jar is None:
                    print(f"   [W] Cannot find jar for missing mod '{dep}'")
                    continue
                enable_mod(jar)
                temp_jars.append(jar)

            reset_log()
            exit_code = run_server()
            time.sleep(2)

            try:
                log_content = log_path.read_text(errors="ignore")
            except Exception as e:
                print(f"[DEBUG] Could not read log after enabling deps: {e}")
                log_content = ""

            if ERROR_STR in log_content:
                print(f"\n[X] Crash caused by {mod}")
                for j in temp_jars:
                    disable_mod(j)
                disable_mod(mod)
                return

            for j in temp_jars:
                disable_mod(j)

        print(f"   {mod_name} tested")
        print("   [X] Crash string not found.")
        disable_mod(mod)

    print(f"Checked {total} mods.")
    print("No offending mod found.")

if __name__ == "__main__":
    main()

