# Mod‑Tester

Mod‑Tester is a lightweight utility that automates the process of identifying which Minecraft Forge mod
causes a server crash during startup.  
It iterates through all JAR files in a specified `mods/` folder, temporarily enables one mod at a time,
runs the server, and checks the log for the standard crash signature:

```
Attempted to load class net/minecraft/client/gui/Gui for invalid dist DEDICATED_SERVER
```

If the crash is detected, the offending mod is reported and the process stops.  
The script also attempts to resolve any missing dependencies by enabling the required mods
found in the same `mods/` folder.

> **Why this matters**  
> When building or maintaining a modpack, a single incompatible mod can bring down the entire server.
> Automating the detection saves hours of manual trial‑and‑error.

---

## Table of Contents

1. [Prerequisites](#prerequisites)
2. [Project Layout](#project-layout)
3. [Configuration](#configuration)
4. [Usage](#usage)
5. [Additional Scripts](#additional-scripts)
6. [License](#license)

---

## Prerequisites

| Item | Minimum version |
|------|-----------------|
| Python | 3.8 or newer |
| Java | 17+ (matching the server’s required Java version) |
| Forge | 1.19+ (or whatever your server uses) |

> The script only requires the standard library; no external packages are needed.

---

## Project Layout

```
├── LICENSE
├── README.md          ← this file
├── find_problem_mod.sh   (bash helper)
├── scan_screen_class.sh  (bash helper)
└── main.py              ← core tester
```

* `main.py` – the Python script that performs the mod‑by‑mod test cycle.
* `find_problem_mod.sh` – optional helper to search the server log for missing mod IDs.
* `scan_screen_class.sh` – optional helper to locate the obfuscated class name of the screen class.

---

## Configuration

Edit the top‑level constants in `main.py` before running:

```python
SERVER_ROOT = ""          # Optional: change to the directory that contains the server
SERVER_SCRIPT = "start.sh"  # Name of the script that starts the server
ERROR_STR = (
    "Attempted to load class net/minecraft/client/gui/Gui for invalid dist DEDICATED_SERVER"
)  # Crash marker string
TIMEOUT = 10            # Seconds before the server is force‑killed
MODS_DIR = "mods"       # Directory that holds your mod JARs
LOG_FILE = "server_log.txt"  # Log file that is truncated before each run
```

> **Tip:**  
> If your server is launched from a different directory, set `SERVER_ROOT` to that path and
> adjust `SERVER_SCRIPT` accordingly (e.g. `"./run.sh"`).

---

## Usage

```bash
# 1. Place all your mod JARs into the `mods/` directory
mkdir -p mods
# (copy or move .jar files here)

# 2. Ensure your server start script (start.sh) is in the same folder as main.py
#    or set SERVER_ROOT and SERVER_SCRIPT accordingly.

# 3. Run the tester
python3 main.py