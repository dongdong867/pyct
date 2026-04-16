"""Library benchmark suite — auto-discover entry points from installed packages.

Walks bs4 and PyYAML public APIs to find testable functions (callable,
<=5 primitive-typed parameters). Generates BenchmarkTarget for each.
"""

from __future__ import annotations

import importlib
import inspect
import logging
import os
import pkgutil
from dataclasses import dataclass
from types import ModuleType
from typing import Any

from tools.benchmark.targets import BenchmarkTarget

log = logging.getLogger("benchmark.discovery")

_MAX_PARAMS = 5
_PRIMITIVE_TYPES = {int, float, str, bool, bytes}
_DEFAULT_VALUES: dict[type, Any] = {
    int: 1,
    float: 1.0,
    str: "test",
    bool: True,
    bytes: b"test",
}


@dataclass(frozen=True)
class LibraryConfig:
    """Configuration for one library benchmark target."""

    package_name: str
    pip_name: str
    category: str
    description: str


LIBRARY_CONFIGS: list[LibraryConfig] = [
    LibraryConfig(
        package_name="bs4",
        pip_name="beautifulsoup4",
        category="bs4",
        description="BeautifulSoup4 — fully typed HTML/XML parser",
    ),
    LibraryConfig(
        package_name="yaml",
        pip_name="PyYAML",
        category="pyyaml",
        description="PyYAML — zero-type-hint YAML parser",
    ),
]


def discover_library_entry_points(
    package_name: str,
    category: str,
) -> list[BenchmarkTarget]:
    """Discover testable entry points from an installed package."""
    package = _import_package(package_name)
    if package is None:
        return []

    source_path = _resolve_source_path(package)
    modules = _collect_public_modules(package, package_name)
    callables = _collect_public_callables(modules, package_name)
    targets = _build_targets(callables, category, source_path)

    log.info("Discovered %d entry points from %s", len(targets), package_name)
    return targets


def _import_package(name: str) -> ModuleType | None:
    try:
        return importlib.import_module(name)
    except ImportError:
        log.warning("Cannot import package: %s", name)
        return None


def _resolve_source_path(package: ModuleType) -> str | None:
    """Find the installed package's source directory."""
    init_file = getattr(package, "__file__", None)
    if init_file is None:
        return None
    return os.path.dirname(os.path.abspath(init_file))


def _collect_public_modules(
    package: ModuleType,
    package_name: str,
) -> list[ModuleType]:
    """Walk the package tree and collect importable public modules."""
    modules = [package]
    package_path = getattr(package, "__path__", None)
    if package_path is None:
        return modules

    for _importer, name, _is_pkg in pkgutil.walk_packages(
        package_path, prefix=f"{package_name}."
    ):
        if any(part.startswith("_") for part in name.split(".")):
            continue
        try:
            modules.append(importlib.import_module(name))
        except Exception:
            continue
    return modules


def _collect_public_callables(
    modules: list[ModuleType],
    package_name: str,
) -> list[tuple[str, str, Any]]:
    """Find public callables with primitive-typed parameters.

    Returns (module_name, func_name, callable) triples.
    """
    seen: set[int] = set()
    results: list[tuple[str, str, Any]] = []

    for module in modules:
        module_name = module.__name__
        names = getattr(module, "__all__", None)
        if names is None:
            names = [n for n in dir(module) if not n.startswith("_")]

        for name in names:
            obj = getattr(module, name, None)
            if obj is None or not callable(obj):
                continue
            if inspect.isclass(obj):
                continue  # engine's rewrite_target needs a function, not a class
            if id(obj) in seen:
                continue
            seen.add(id(obj))

            # Check it belongs to this package
            obj_module = getattr(obj, "__module__", "")
            if not obj_module.startswith(package_name):
                continue

            if _has_testable_signature(obj):
                results.append((module_name, name, obj))

    return results


def _has_testable_signature(obj: Any) -> bool:
    """Check if callable has <=MAX_PARAMS and inspectable source.

    Accepts params without annotations — those will default to str in
    the arg inference step. This is intentionally lenient to catch
    library functions like yaml.safe_load(stream) that have no hints.
    """
    try:
        sig = inspect.signature(obj)
    except (ValueError, TypeError):
        return False

    # Must have inspectable source for the engine
    try:
        inspect.getfile(obj)
    except (TypeError, OSError):
        return False

    params = [
        p for p in sig.parameters.values()
        if p.kind not in (
            inspect.Parameter.VAR_POSITIONAL,
            inspect.Parameter.VAR_KEYWORD,
        )
        and p.name != "self"
    ]

    return bool(params) and len(params) <= _MAX_PARAMS


def _build_targets(
    callables: list[tuple[str, str, Any]],
    category: str,
    source_path: str | None = None,
) -> list[BenchmarkTarget]:
    """Build BenchmarkTarget for each discovered callable.

    Each candidate is smoke-tested with inferred args. Functions that
    crash on ImportError or FeatureNotFound (missing optional deps like
    lxml) are silently skipped.
    """
    targets: list[BenchmarkTarget] = []
    for module_name, func_name, obj in callables:
        args = _infer_initial_args(obj)
        if args is None:
            continue
        if not _smoke_check(obj, args, f"{module_name}.{func_name}"):
            continue
        targets.append(BenchmarkTarget(
            name=f"{module_name}.{func_name}",
            module=module_name,
            function=func_name,
            initial_args=args,
            category=category,
            description=f"Auto-discovered from {module_name}",
            source_path=source_path,
        ))
    return targets


def _smoke_check(obj: Any, args: dict[str, Any], label: str) -> bool:
    """Try calling the function once; skip if it crashes on missing deps."""
    try:
        obj(**args)
        return True
    except (ImportError, ModuleNotFoundError) as e:
        log.info("Skipping %s: missing dep: %s", label, e)
        return False
    except Exception:
        return True  # other exceptions are fine — the function is callable


def _infer_initial_args(obj: Any) -> dict[str, Any] | None:
    """Infer initial arguments from type annotations and defaults.

    Parameters without annotations or defaults get ``"test"`` (str) as a
    fallback — most library entry points accept string input.
    """
    try:
        sig = inspect.signature(obj)
    except (ValueError, TypeError):
        return None

    args: dict[str, Any] = {}
    for name, param in sig.parameters.items():
        if name == "self":
            continue
        if param.kind in (
            inspect.Parameter.VAR_POSITIONAL,
            inspect.Parameter.VAR_KEYWORD,
        ):
            continue

        if param.default is not inspect.Parameter.empty:
            args[name] = param.default
        elif param.annotation is not inspect.Parameter.empty:
            default = _DEFAULT_VALUES.get(param.annotation)
            if default is not None:
                args[name] = default
            else:
                args[name] = "test"  # fallback for non-primitive annotations
        else:
            args[name] = "test"  # fallback for untyped params
    return args
