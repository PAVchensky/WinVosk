"""Windows startup registration through the per-user Run key."""

from __future__ import annotations

import logging
import sys
import winreg
from pathlib import Path

from . import config

log = logging.getLogger(__name__)


def _command() -> str:
    """The Windows startup command: the exe in a bundle, pythonw otherwise."""
    if config.FROZEN:
        return f'"{Path(sys.executable).resolve()}"'
    executable = config.PYTHONW if config.PYTHONW.exists() else Path(sys.executable)
    return f'"{executable}" "{config.RUN_SCRIPT}"'


def is_enabled() -> bool:
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, config.RUN_KEY) as key:
            value, _ = winreg.QueryValueEx(key, config.RUN_VALUE)
    except OSError:
        return False
    return bool(value)


def enable() -> bool:
    command = _command()
    with winreg.CreateKeyEx(
        winreg.HKEY_CURRENT_USER, config.RUN_KEY, 0, winreg.KEY_SET_VALUE
    ) as key:
        winreg.SetValueEx(key, config.RUN_VALUE, 0, winreg.REG_SZ, command)
    log.info("autostart enabled: %s", command)
    return True


def disable() -> bool:
    try:
        with winreg.OpenKey(
            winreg.HKEY_CURRENT_USER, config.RUN_KEY, 0, winreg.KEY_SET_VALUE
        ) as key:
            winreg.DeleteValue(key, config.RUN_VALUE)
    except FileNotFoundError:
        return False
    log.info("autostart disabled")
    return True


def apply(enabled: bool) -> bool:
    return enable() if enabled else disable()
