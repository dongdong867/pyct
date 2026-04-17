"""Path normalization — make baselines portable across machines.

Baselines are committed to git and must match hits on any developer's
machine regardless of where site-packages lives. The normalizer strips
the leading venv/install prefix so the remaining key (e.g.
``yaml/__init__.py``) is stable.
"""

from __future__ import annotations

from tools.benchmark.baseline import normalize_to_site_packages_relative

# ── Happy paths: common install layouts ───────────────────────────


def test_normalize_uv_venv_macos():
    abs_path = "/Users/dong/dev/pyct/.venv/lib/python3.13/site-packages/yaml/__init__.py"
    assert normalize_to_site_packages_relative(abs_path) == "yaml/__init__.py"


def test_normalize_uv_venv_linux():
    abs_path = "/home/dong/Dev/pyct/.venv/lib/python3.12/site-packages/werkzeug/http.py"
    assert normalize_to_site_packages_relative(abs_path) == "werkzeug/http.py"


def test_normalize_conda_env():
    abs_path = "/opt/conda/envs/x/lib/python3.12/site-packages/sympy/ntheory/factor_.py"
    assert normalize_to_site_packages_relative(abs_path) == "sympy/ntheory/factor_.py"


def test_normalize_nested_package_path():
    abs_path = "/v/lib/python3.12/site-packages/bs4/builder/_html5lib.py"
    assert normalize_to_site_packages_relative(abs_path) == "bs4/builder/_html5lib.py"


# ── Edge ──────────────────────────────────────────────────────────


def test_normalize_uses_last_site_packages_when_nested():
    # Some dev layouts have site-packages inside site-packages (eg bundled tools).
    # The LAST occurrence is the actual install location.
    abs_path = "/a/site-packages/tool/b/site-packages/yaml/__init__.py"
    assert normalize_to_site_packages_relative(abs_path) == "yaml/__init__.py"


def test_normalize_rejects_substring_match():
    # "site-packages" as part of a filename must NOT be treated as the boundary.
    abs_path = "/home/user/site-packages-bundler/yaml/__init__.py"
    assert normalize_to_site_packages_relative(abs_path) is None


# ── Stdlib paths (realworld uses urllib.parse, json, etc) ─────────


def test_normalize_stdlib_urllib_linux():
    abs_path = "/usr/lib/python3.12/urllib/parse.py"
    assert normalize_to_site_packages_relative(abs_path) == "urllib/parse.py"


def test_normalize_stdlib_macos_homebrew():
    abs_path = "/opt/homebrew/lib/python3.13/json/decoder.py"
    assert normalize_to_site_packages_relative(abs_path) == "json/decoder.py"


def test_normalize_prefers_site_packages_over_stdlib_pattern():
    # A venv inside /usr/lib — the site-packages install is canonical.
    abs_path = "/usr/lib/python3.12/site-packages/yaml/__init__.py"
    assert normalize_to_site_packages_relative(abs_path) == "yaml/__init__.py"


# ── Error / non-matching ──────────────────────────────────────────


def test_normalize_returns_none_when_no_site_packages_or_stdlib():
    # Editable install or source file — not under any recognizable root.
    abs_path = "/Users/dong/dev/pyct/src/pyct/engine.py"
    assert normalize_to_site_packages_relative(abs_path) is None


def test_normalize_returns_none_for_empty_string():
    assert normalize_to_site_packages_relative("") is None
