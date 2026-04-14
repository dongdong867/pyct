"""Helper utilities for managing virtual environments."""

from __future__ import annotations

import site
import sys
from pathlib import Path
from typing import Optional

_VENV_DIR_NAMES = (".venv", "venv", "env")


def activate_project_venv(project_root: str) -> bool:
    """Activate a project's virtual environment if it exists.

    Modifies ``sys.path`` to include the project's venv site-packages.

    Returns True if a venv was found and activated.
    """
    site_packages = _find_site_packages(project_root)
    if site_packages is None:
        return False

    site_packages_str = str(site_packages)
    if site_packages_str not in sys.path:
        sys.path.insert(1, site_packages_str)

    site.addsitedir(site_packages_str)
    return True


def get_venv_python_executable(project_root: str) -> Optional[str]:
    """Return the path to the venv's Python executable, or None."""
    venv_path = _find_venv_dir(project_root)
    if venv_path is None:
        return None

    if sys.platform == "win32":
        exe = venv_path / "Scripts" / "python.exe"
    else:
        exe = venv_path / "bin" / "python"

    return str(exe) if exe.exists() else None


# ---------------------------------------------------------------------------
# Shared helpers
# ---------------------------------------------------------------------------


def _find_venv_dir(project_root: str) -> Optional[Path]:
    """Locate the venv directory under *project_root*."""
    root = Path(project_root)
    for name in _VENV_DIR_NAMES:
        candidate = root / name
        if candidate.exists():
            return candidate
    return None


def _find_site_packages(project_root: str) -> Optional[Path]:
    """Locate the site-packages directory inside the project's venv."""
    venv_path = _find_venv_dir(project_root)
    if venv_path is None:
        return None

    if sys.platform == "win32":
        candidate = venv_path / "Lib" / "site-packages"
        return candidate if candidate.exists() else None

    return _find_unix_site_packages(venv_path)


def _find_unix_site_packages(venv_path: Path) -> Optional[Path]:
    """Find site-packages under a Unix venv, trying the current Python version first."""
    python_version = f"python{sys.version_info.major}.{sys.version_info.minor}"
    candidate = venv_path / "lib" / python_version / "site-packages"
    if candidate.exists():
        return candidate

    lib_path = venv_path / "lib"
    if not lib_path.exists():
        return None

    for item in lib_path.iterdir():
        if item.is_dir() and item.name.startswith("python"):
            candidate = item / "site-packages"
            if candidate.exists():
                return candidate

    return None
