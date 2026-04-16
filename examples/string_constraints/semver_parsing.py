"""Semantic versioning parser benchmark target.

Category: Structured string parsing with numeric validation
Intent: Parse and classify semantic version strings (major.minor.patch[-pre][+build])
    including prerelease tags, build metadata, and release type classification.
Challenge: Combines string splitting with numeric conversion, range checks, optional
    prerelease/build-metadata suffixes, and release-type logic (major, patch-only,
    breaking change) creating many branching paths through a simple format.
"""

from __future__ import annotations

MAX_VERSION_COMPONENT = 9999

PRERELEASE_TAGS = frozenset({"alpha", "beta", "rc"})


def _strip_leading_v(version: str) -> str:
    """Strip a leading 'v' or 'V' prefix if present."""
    if version.startswith("v") or version.startswith("V"):
        return version[1:]
    return version


def _extract_build_metadata(patch_part: str) -> tuple[str, str | None]:
    """Separate build metadata from patch segment. Returns (remainder, build_or_none)."""
    if "+" not in patch_part:
        return patch_part, None
    remainder, build = patch_part.split("+", maxsplit=1)
    if len(build) == 0:
        return remainder, ""
    return remainder, build


def _extract_prerelease(patch_part: str) -> tuple[str, str | None]:
    """Separate prerelease tag from patch segment. Returns (patch, prerelease_or_none)."""
    if "-" not in patch_part:
        return patch_part, None
    patch, prerelease = patch_part.split("-", maxsplit=1)
    return patch, prerelease


def _validate_component(value: str, name: str) -> tuple[int, str | None]:
    """Validate and convert a version component. Returns (number, error_or_none)."""
    if not value.isdigit():
        return -1, f"invalid_{name}_not_numeric"
    num = int(value)
    if num > MAX_VERSION_COMPONENT:
        return -1, f"invalid_{name}_too_large"
    return num, None


def _classify_prerelease(tag: str) -> str:
    """Classify a prerelease tag into known or custom category."""
    base = tag.split(".", maxsplit=1)[0]
    if base in PRERELEASE_TAGS:
        return f"prerelease_{base}"
    return "prerelease_custom"


def _classify_release(major: int, minor: int, patch: int) -> str:
    """Classify a stable release by version numbers."""
    if major == 0:
        return "pre_v1_release"
    if minor == 0 and patch == 0:
        return "major_release"
    if major > 0 and minor == 0 and patch > 0:
        return "patch_only"
    return "stable_release"


def semver_parsing(version: str) -> str:
    """Parse a semantic version string and return a classification."""
    if len(version) == 0:
        return "invalid_empty"

    cleaned = _strip_leading_v(version)
    if "." not in cleaned:
        return "invalid_no_dots"

    parts = cleaned.split(".")
    if len(parts) < 3:
        return "invalid_too_few_parts"
    if len(parts) > 3:
        return "invalid_too_many_parts"

    major_str, minor_str, raw_patch = parts

    major, major_err = _validate_component(major_str, "major")
    if major_err is not None:
        return major_err

    minor, minor_err = _validate_component(minor_str, "minor")
    if minor_err is not None:
        return minor_err

    after_build, build = _extract_build_metadata(raw_patch)
    patch_str, prerelease = _extract_prerelease(after_build)

    patch, patch_err = _validate_component(patch_str, "patch")
    if patch_err is not None:
        return patch_err

    if build is not None and len(build) == 0:
        return "invalid_empty_build"

    if prerelease is not None and build is not None:
        return "prerelease_with_build_metadata"
    if build is not None:
        return "release_with_build_metadata"
    if prerelease is not None:
        return _classify_prerelease(prerelease)

    return _classify_release(major, minor, patch)
