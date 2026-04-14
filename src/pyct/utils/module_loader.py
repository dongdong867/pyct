from __future__ import annotations

import inspect
import logging
import os
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from types import ModuleType
from typing import Any

log = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Public API — preferred entry points for loading modules and functions
# ---------------------------------------------------------------------------


def get_module_from_rootdir_and_modpath(
    root_dir: str, module_path: str
) -> ModuleType | None:
    """
    Load module from root directory and module path.

    Args:
        root_dir: Root directory containing the module
        module_path: Dot-separated module path

    Returns:
        Loaded module or None if loading fails
    """
    return _load_module(root_dir, module_path)


def get_function_from_module_and_funcname(
    module: ModuleType, function_name: str, enforce: bool = True
) -> Callable | None:
    """
    Get function from module by name.

    Args:
        module: Module to search in
        function_name: Function name (supports dot notation for class methods)
        enforce: If True, skip validation and return the attribute directly

    Returns:
        Function object or None if not found/invalid
    """
    return _get_function(module, function_name, enforce)


# ---------------------------------------------------------------------------
# Internal implementation
# ---------------------------------------------------------------------------


def _load_module(root_dir: str, module_path: str) -> ModuleType | None:
    """Load a module by trying standard import first, then file-based loading."""
    try:
        import importlib
        import importlib.util

        try:
            return importlib.import_module(module_path)
        except ImportError:
            pass

        file_path = _resolve_module_path(root_dir, module_path)
        spec = importlib.util.spec_from_file_location(module_path, file_path)

        if spec is None or spec.loader is None:
            return None

        module = importlib.util.module_from_spec(spec)

        exec_dir = root_dir
        if "/src/" in file_path:
            src_index = file_path.find("/src/")
            if src_index != -1:
                exec_dir = file_path[: src_index + 4]

        with _change_directory(exec_dir):
            spec.loader.exec_module(module)

        return module

    except Exception as e:
        log.error("Failed to load module %s: %s", module_path, e)
        return None


def _resolve_module_path(root_dir: str, module_path: str) -> str:
    """Resolve a dot-separated module path to an absolute file path."""
    relative_path = module_path.replace(".", "/") + ".py"

    direct_path = os.path.abspath(os.path.join(root_dir, relative_path))
    if os.path.exists(direct_path):
        return direct_path

    src_path = os.path.abspath(os.path.join(root_dir, "src", relative_path))
    if os.path.exists(src_path):
        return src_path

    return direct_path


def _get_function(
    module: ModuleType, function_name: str, enforce: bool = True
) -> Callable | None:
    """Get a function from a module, optionally validating parameter types."""
    try:
        func = _navigate_to_attribute(module, function_name)

        if enforce:
            return func

        return func if _is_valid_function(func) else None

    except AttributeError as e:
        log.error("Failed to get function %s: %s", function_name, e)
        return None


def _navigate_to_attribute(obj: Any, dotted_name: str) -> Any:
    """Resolve a dot-separated attribute path on an object."""
    current = obj
    for part in dotted_name.split("."):
        current = getattr(current, part)
    return current


def _is_valid_function(func: Callable) -> bool:
    """Check that all parameters have int or str annotations."""
    try:
        sig = inspect.signature(func)
        params = list(sig.parameters.values())

        if not params:
            return False

        supported_types = {int, str}
        return all(p.annotation in supported_types for p in params)

    except Exception:
        return False


@contextmanager
def _change_directory(path: str) -> Iterator[None]:
    """Context manager for safely changing the working directory."""
    original_dir = os.getcwd()
    try:
        os.chdir(path)
        yield
    finally:
        os.chdir(original_dir)
