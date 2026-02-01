#!/usr/bin/env python3
"""
Python replacement for the original Bash script that scans a set of mod JARs
until the first one that reproduces a crash is found.

Author:  <your‑name>
Date:    2024‑09‑13
"""

import pathlib
import subprocess
import re
import time
import zipfile
from typing import Iterable, List, Optional

# --------------------------------------------------------------------------- #
#  CONFIGURATION  ----------------------------------------------------------- #
# --------------------------------------------------------------------------- #
SERVER_ROOT = "~/forge_server/"
SERVER_SCRIPT = "start.sh"  # the script that starts the server
ERROR_STR = (
    "Attempted to load class net/minecraft/client/gui/Gui for invalid dist DEDICATED_SERVER"
)
TIMEOUT = 10          # seconds – the same value that was used in Bash
MODS_DIR = "mods"     # directory that contains the JARs
LOG_FILE = "server_log.txt"  # log file that is overwritten before each run
# --------------------------------------------------------------------------- #

# --------------------------------------------------------------------------- #
#  HELPERS  --------------------------------------------------------------- #
# --------------------------------------------------------------------------- #
def get_modid_from_jar(jar_path: pathlib.Path) -> Optional[str]:
    """
    Return the `modId` string that is stored in either
    META‑INF/mods.toml or META‑INF/mod.json.
    If nothing can be found the function returns None.
    """
    jar_path = pathlib.Path(jar_path)
    try:
        with zipfile.ZipFile(jar_path, "r") as z:
            # find the first file that looks like a metadata file
            meta_files = [
                f
                for f in z.namelist()
                if f.startswith("META-INF/")
                and (f.endswith("mods.toml") or f.endswith("mod.json"))
            ]
            if not meta_files:
                return None

            meta = meta_files[0]
            content = z.read(meta).decode("utf-8", errors="ignore")

            # `mods.toml`  →  modId = "foo"
            m = re.search(r"modId\s*=\s*([^\s]+)", content)
            if m:
                modid = m.group(1).strip().strip('"').strip("'")
                return modid

            # `mod.json`  →  "modId":"foo"
            m = re.search(r'"modId"\s*:\s*"([^"]+)"', content)
            if m:
                return m.group(1).strip()
    except Exception:
        # Any error while reading the jar is ignored – the original
        # script silently skipped JARs that didn't contain a metadata file
        pass
    return None


def disable_mod(mod_path: pathlib.Path) -> None:
    """Rename `something.jar` → `something.jar.disabled`."""
    p = pathlib.Path(mod_path)
    if p.suffix == ".jar":
        new = p.with_name(p.name + ".disabled")
        p.rename(new)


def enable_mod(mod_path: pathlib.Path) -> None:
    """Rename `something.jar.disabled` → `something.jar`."""
    p = pathlib.Path(mod_path)
    if p.name.endswith(".jar.disabled"):
        new = p.with_name(p.name.replace(".jar.disabled", ".jar"))
        p.rename(new)


def disable_all() -> None:
    """Disable every *.jar in MODS_DIR."""
    for p in pathlib.Path(MODS_DIR).glob("*.jar"):
        disable_mod(p)


def enable_all() -> None:
    """Enable every *.jar.disabled in MODS_DIR."""
    for p in pathlib.Path(MODS_DIR).glob("*.jar.disabled"):
        enable_mod(p)


def reset_log() -> None:
    """Truncate the log file – it will be written to again."""
    pathlib.Path(LOG_FILE).write_text("")


def extract_missing_ids(log_path: pathlib.Path) -> List[str]:
    """
    Return a list of *mod IDs* that appear in the log in the
    form:  Mod ID: 'foo'
    """
    missing: List[str] = []
    content = log_path.read_text(errors="ignore")
    for match in re.finditer(r"Mod ID: '([^']+)'", content):
        missing.append(match.group(1))
    return missing


def find_mod_by_id(target_id: str) -> Optional[pathlib.Path]:
    """Return the first JAR that contains the requested modId."""
    for p in pathlib.Path(MODS_DIR).glob("*.jar*"):
        modid = get_modid_from_jar(p)
        if modid == target_id:
            return p
    return None


def run_server() -> int:
    """
    Execute the server start script, write stdout+stderr to LOG_FILE
    and honour the timeout value.  Return 124 if the process timed
    out – that mirrors the exit code the Bash script used.
    """
    try:
        with pathlib.Path(LOG_FILE).open("w") as log_f:
            result = subprocess.run(
                [f"./{SERVER_SCRIPT}"],
                cwd=".",
                stdout=log_f,
                stderr=log_f,
                timeout=TIMEOUT,
                text=True,
            )
        return result.returncode
    except subprocess.TimeoutExpired:
        return 124


# --------------------------------------------------------------------------- #
#  MAIN  ------------------------------------------------------------------- #
# --------------------------------------------------------------------------- #
def main() -> None:
    enable_all()                         # restore the original state
    mods: List[pathlib.Path] = list(
        pathlib.Path(MODS_DIR).glob("*.jar")
    )
    total = len(mods)

    print(f"Found {total} mod(s).")
    disable_all()
    print("All mods disabled. Starting test loop.")

    for idx, mod in enumerate(mods, start=1):
        mod_name = mod.name
        print(f"\n[{idx}/{total}] Enabling {mod_name}...")

        enable_mod(mod)                 # enable this mod
        reset_log()

        exit_code = run_server()
        if exit_code == 124:            # timed out
            print("   [I] Server timed out – skipping this mod.")
            disable_mod(mod)
            continue

        time.sleep(2)                   # give the server a moment to finish

        log_content = pathlib.Path(LOG_FILE).read_text(errors="ignore")
        if ERROR_STR in log_content:
            print(f"\n[X] Crash caused by {mod.resolve()}")
            return

        missing = extract_missing_ids(LOG_FILE)
        if missing:
            print(f"   [W] Missing deps: {' '.join(missing)}")
            temp_jars: List[pathlib.Path] = []

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

            log_content = pathlib.Path(LOG_FILE).read_text(errors="ignore")
            if ERROR_STR in log_content:
                print(f"\n[X] Crash caused by {mod.resolve()}")
                # clean‑up the temporarily enabled deps
                for j in temp_jars:
                    disable_mod(j)
                disable_mod(mod)
                return

            # if we still haven't crashed, undo the temporary changes
            for j in temp_jars:
                disable_mod(j)

        print(f"   {mod_name} tested")
        print("   [X] Crash string not found.")
        disable_mod(mod)

    print(f"Checked {total} mods.")
    print("No offending mod found.")


if __name__ == "__main__":
    main()

    