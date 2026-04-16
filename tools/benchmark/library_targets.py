"""Library benchmark suite — auto-discover entry points from installed packages.

Walks sympy.ntheory and PyYAML public APIs to find testable functions
and class constructors. Matches legacy's discovery logic: includes
classes (via __init__), uses 0/""/ None for inferred args, strict
same-module check.
"""

from __future__ import annotations

import importlib
import inspect
import logging
import os
import pkgutil
import typing
from dataclasses import dataclass
from types import ModuleType
from typing import Any

from tools.benchmark.targets import BenchmarkTarget

log = logging.getLogger("benchmark.discovery")

_MAX_PARAMS = 5
_PRIMITIVE_TYPES = {int, float, str, bool, bytes, list, dict, type(None)}
_IMMUTABLE_DEFAULTS: dict[type, Any] = {
    int: 0,
    str: "",
    bool: True,
    float: 0.0,
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
        package_name="sympy.ntheory",
        pip_name="sympy",
        category="sympy_ntheory",
        description="SymPy number theory — pure-Python numeric computation",
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

    for _importer, name, _is_pkg in pkgutil.walk_packages(package_path, prefix=f"{package_name}."):
        if any(part.startswith("_") or part == "tests" for part in name.split(".")):
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
    """Find public callables (functions + class constructors).

    Matches legacy: includes classes (checks __init__ signature),
    strict same-module check (func.__module__ == module.__name__).
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
            if id(obj) in seen:
                continue
            seen.add(id(obj))

            # Strict same-module check (matches legacy)
            obj_module = getattr(obj, "__module__", "")
            if obj_module != module_name:
                continue

            if inspect.isclass(obj):
                if _has_testable_init(obj):
                    results.append((module_name, name, obj))
            elif _has_testable_signature(obj):
                results.append((module_name, name, obj))

    return results


def _has_testable_init(cls: type) -> bool:
    """Check if a class constructor is testable."""
    init = getattr(cls, "__init__", None)
    if init is None or init is object.__init__:
        return False
    return _has_testable_signature(init, skip_self=True)


def _has_testable_signature(obj: Any, *, skip_self: bool = False) -> bool:
    """Check if callable has testable parameters.

    Only required params (no default) must have primitive-compatible
    types. Optional params are accepted regardless — PyCT uses their
    defaults. Matches legacy's _has_primitive_signature.
    """
    try:
        sig = inspect.signature(obj)
        resolved_hints = _resolve_type_hints(obj)
    except (ValueError, TypeError):
        return False

    params = list(sig.parameters.values())
    if skip_self and params and params[0].name == "self":
        params = params[1:]

    regular = [
        p
        for p in params
        if p.kind not in (inspect.Parameter.VAR_POSITIONAL, inspect.Parameter.VAR_KEYWORD)
    ]
    required = [p for p in regular if p.default is inspect.Parameter.empty]

    if not regular:
        return False
    if len(required) > _MAX_PARAMS:
        return False

    return all(_is_primitive_param(p, resolved_hints) for p in required)


def _resolve_type_hints(func: Any) -> dict:
    """Resolve string annotations to actual types."""
    try:
        return typing.get_type_hints(func)
    except Exception:
        return {}


def _is_primitive_param(param: inspect.Parameter, resolved_hints: dict) -> bool:
    """Check if a required parameter is primitive-compatible."""
    ann = resolved_hints.get(param.name, param.annotation)
    if ann is inspect.Parameter.empty:
        return True  # untyped params default to 0
    return _is_primitive_type(ann)


def _is_primitive_type(annotation: Any) -> bool:
    """Check if a type annotation is primitive or simple container."""
    if annotation in _PRIMITIVE_TYPES:
        return True
    origin = getattr(annotation, "__origin__", None)
    if origin is list or origin is dict or origin is type(None):
        return True
    if origin is typing.Union:
        args = getattr(annotation, "__args__", ())
        return any(_is_primitive_type(a) for a in args)
    return False


def _build_targets(
    callables: list[tuple[str, str, Any]],
    category: str,
    source_path: str | None = None,
) -> list[BenchmarkTarget]:
    """Build BenchmarkTarget for each discovered callable."""
    targets: list[BenchmarkTarget] = []
    for module_name, func_name, obj in callables:
        target_func = obj.__init__ if inspect.isclass(obj) else obj
        try:
            args = _infer_args(target_func)
        except (ValueError, TypeError):
            continue
        args.pop("self", None)
        if not args:
            continue
        targets.append(
            BenchmarkTarget(
                name=f"{module_name}.{func_name}",
                module=module_name,
                function=func_name,
                initial_args=args,
                category=category,
                description=f"Auto-discovered from {module_name}",
                source_path=source_path,
            )
        )
    return targets


def _infer_args(func: Any) -> dict[str, Any]:
    """Infer initial args matching legacy's pattern.

    Required params: type-inferred default (0 for untyped, "" for str, etc.)
    Optional params with primitive defaults: use the default.
    Optional params with non-primitive defaults: skip.
    """
    sig = inspect.signature(func)
    args: dict[str, Any] = {}

    for param_name, param in sig.parameters.items():
        if param.kind in (inspect.Parameter.VAR_POSITIONAL, inspect.Parameter.VAR_KEYWORD):
            continue
        if param.default is inspect.Parameter.empty:
            args[param_name] = _default_for_annotation(param.annotation)
        elif isinstance(param.default, (int, float, str, bool, bytes, type(None))):
            args[param_name] = param.default

    return args


def _default_for_annotation(annotation: Any) -> Any:
    """Return a sensible default for a type annotation.

    Matches legacy: 0 for untyped, "" for str, None for Optional.
    """
    if annotation is inspect.Parameter.empty:
        return 0

    if annotation in _IMMUTABLE_DEFAULTS:
        return _IMMUTABLE_DEFAULTS[annotation]

    if annotation is list:
        return []
    if annotation is dict:
        return {}

    origin = getattr(annotation, "__origin__", None)
    if origin is list:
        return []
    if origin is dict:
        return {}

    if origin is typing.Union:
        args = getattr(annotation, "__args__", ())
        if type(None) in args:
            return None

    return None
