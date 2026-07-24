from __future__ import annotations

import importlib.util
from pathlib import Path
import re

import pytest


ROOT = Path(__file__).resolve().parents[2]
SPEC = importlib.util.spec_from_file_location("release_metadata_check", ROOT / "release_metadata_check.py")
assert SPEC and SPEC.loader
release_metadata_check = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(release_metadata_check)


def test_installed_version_has_a_truthful_whats_new_entry() -> None:
    release_metadata_check.validate_current_release()


def test_worktree_product_changes_require_release_metadata() -> None:
    release_metadata_check.validate_change_set(release_metadata_check.changed_paths())


def test_release_guard_distinguishes_product_changes_from_tests_and_docs() -> None:
    assert release_metadata_check.is_shipped_path("app/backend/main.py") is True
    assert release_metadata_check.is_shipped_path("pinokio.js") is True
    assert release_metadata_check.is_shipped_path("chatstudio-watchdog.sh") is True
    assert release_metadata_check.is_shipped_path("app/tests/test_launcher_menu.py") is False
    assert release_metadata_check.is_shipped_path("chatstudio_genstudio_integration.md") is False


def test_release_guard_requires_a_numeric_version_increase() -> None:
    paths = {"app/backend/main.py", "VERSION", "CHANGELOG.md"}
    release_metadata_check.validate_change_set(
        paths, baseline_version="1.24.0", release_version="1.24.1"
    )
    with pytest.raises(release_metadata_check.ReleaseMetadataError, match="VERSION to increase"):
        release_metadata_check.validate_change_set(
            paths, baseline_version="1.24.1", release_version="1.24.1"
        )


def test_all_launcher_stops_use_canonical_app_local_uris() -> None:
    for name in ("update.js", "install_generation.js"):
        source = (ROOT / name).read_text(encoding="utf-8")
        assert 'uri: "{{path.resolve(cwd, \'start.js\')}}"' in source
        assert not re.search(
            r'method:\s*"script\.stop",\s*params:\s*\{\s*uri:\s*"start\.js"',
            source,
        )
