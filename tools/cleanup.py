"""Kill leftover typing targets and the dictation app, so nothing holds the focus.

Only python processes are considered, and never this one. The name of the
script being launched must not appear in a shell command line, or a caller
running this from a shell that mentions the probe would be matched too.
"""

import os
import subprocess
import sys

SELF = os.getpid()
PATTERNS = ("edit_target.py", "src" + os.sep + "run.py")


def python_processes():
    script = (
        "Get-CimInstance Win32_Process -Filter \"Name='python.exe' OR Name='pythonw.exe'\" "
        "| ForEach-Object { $_.ProcessId.ToString() + '|' + $_.CommandLine }"
    )
    result = subprocess.run(
        ["powershell", "-NoProfile", "-Command", script],
        capture_output=True, text=True,
    )
    for line in result.stdout.splitlines():
        pid, _, command = line.partition("|")
        if pid.strip().isdigit() and command.strip():
            yield int(pid.strip()), command


def main() -> int:
    killed = 0
    for pid, command in python_processes():
        if pid == SELF:
            continue
        if not any(pattern in command for pattern in PATTERNS):
            continue
        subprocess.run(["taskkill", "/F", "/PID", str(pid)], capture_output=True)
        killed += 1
        print(f"killed {pid}: {command.strip()[:90]}", flush=True)
    print(f"total {killed}", flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
