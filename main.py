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

# ---------- CONFIGURATION ---------- #
# Expand the user directory to an absolute path for all file operations.
SERVER_ROOT = "~/forge_server"
SERVER_ROOT_ABS = os.path.expanduser(SERVER_ROOT)  # absolute path to the server directory
SERVER_SCRIPT = "start.sh"              # script name inside SERVER_ROOT
ERROR_STR = "Attempted to load class net/minecraft/client/gui/Gui for invalid dist DEDICATED_SERVER"
TIMEOUT = 20
MODS_DIR = "mods"                       # sub‑dir inside SERVER_ROOT
LOG_FILE = "server_log.txt"             # log file inside SERVER_ROOT
# ----------------------------------- #

# ---------- HELPERS ---------- #
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

def reset_log():
    """Truncate the log file – it will be written to again."""
    log_path = pathlib.Path(os.path.join(SERVER_ROOT_ABS, LOG_FILE))
    try:
        log_path.write_text("")
        # print(f"[DEBUG] Reset log {log_path}")
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

# ---------- MOD CLASS ---------- #
class mod:
    """Container for a single mod JAR and its metadata."""
    def __init__(self, path: pathlib.Path):
        self.path = path
        self.modid: Optional[str] = get_modid_from_jar(str(path))
        self.dependencies: List[str] = []  # can be filled later if needed

    def enable(self):
        """Rename `something.jar.disabled` → `something.jar`."""
        p = self.path
        if p.name.endswith(".jar.disabled"):
            new_path = p.with_name(p.name.replace(".jar.disabled", ".jar"))
            try:
                p.rename(new_path)
                self.path = new_path
                # print(f"[DEBUG] Enabled {p}")
            except Exception as e:
                print(f"[DEBUG] Could not enable {self.modid}: {e}")

    def disable(self):
        """Rename `something.jar` → `something.jar.disabled`."""
        p = self.path
        if p.suffix == ".jar":
            new_path = p.with_name(p.name + ".disabled")
            try:
                p.rename(new_path)
                self.path = new_path
                # print(f"[DEBUG] Disabled {p}")
            except Exception as e:
                print(f"[DEBUG] Could not disable {self.modid}: {e}")

# Global list that will hold all discovered mods
MODS: List[mod] = []

def load_mods() -> List[mod]:
    """Scan MODS_DIR once and build a list of `mod` objects."""
    mods = []
    mods_dir = pathlib.Path(os.path.join(SERVER_ROOT_ABS, MODS_DIR))
    for p in mods_dir.glob("*.jar"):
        mods.append(mod(p))
    return mods

# ---------- HELPERS (modified) ---------- #
def disable_all():
    """Disable every mod in MODS."""
    for m in MODS:
        m.disable()

def enable_all():
    """Enable every mod in MODS."""
    for m in MODS:
        m.enable()

def find_mod_by_id(target_id):
    """Return the `mod` instance that matches target_id."""
    for m in MODS:
        if m.modid == target_id:
            return m
    return None

# ---------- MAIN ---------- #
def main():
    print("[DEBUG] Starting mod‑crash‑finder")
    # Build the mod list once
    global MODS
    MODS = load_mods()
    total = len(MODS)

    print(f"[DEBUG] Found {total} mod(s).")

    if total == 0:
        print('[DEBUG] Nothing to do, exiting...')
        exit(1)

    disable_all()
    print("[DEBUG] All mods disabled. Starting test loop.")

    for idx, m in enumerate(MODS, start=1):
        mod_name = os.path.basename(str(m.path))
        print(f"\n[{idx}/{total}] Enabling '{m.modid}' ({mod_name})...")

        m.enable()                 # enable this mod
        reset_log()

        exit_code = run_server()
        if exit_code == 124:            # timed out
            # print("   [I] Server timed out – skipping this mod.")
            m.disable()
            continue
        
        # time.sleep(2)                   # give the server a moment to finish

        log_path = pathlib.Path(os.path.join(SERVER_ROOT_ABS, LOG_FILE))
        try:
            log_content = log_path.read_text(errors="ignore")
        except Exception as e:
            print(f"[DEBUG] Could not read log {log_path}: {e}")
            log_content = ""

        if ERROR_STR in log_content:
            print(f"\n[X] Crash caused by {m.path}")
            return

        missing = extract_missing_ids(log_path)
        if missing:
            print(f"   [W] Missing deps: {' '.join(missing)}")
            temp_mods = []

            for dep in missing:
                # print(f"Searching missing dep '{dep}' …")
                dep_mod = find_mod_by_id(dep)
                if dep_mod is None:
                    print(f"   [W] Cannot find jar for missing mod '{dep}'")
                    continue
                dep_mod.enable()
                temp_mods.append(dep_mod)

            reset_log()
            exit_code = run_server()
            time.sleep(2)

            try:
                log_content = log_path.read_text(errors="ignore")
            except Exception as e:
                print(f"[DEBUG] Could not read log after enabling deps: {e}")
                log_content = ""

            if ERROR_STR in log_content:
                print(f"\n[X] Crash caused by {m.modid}")
                for tm in temp_mods:
                    tm.disable()
                m.disable()
                return

            for tm in temp_mods:
                tm.disable()

        print(f"   {m.modid} tested")
        print("   [X] Crash string not found.")
        m.disable()

    enable_all()

    print(f"Checked {total} mods.")
    print("No offending mod found.")

if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        enable_all()