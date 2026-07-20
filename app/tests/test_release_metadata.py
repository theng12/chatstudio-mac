"""Release metadata stays aligned with the in-app What's New contract."""

from __future__ import annotations

import re
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
VERSION_RE = re.compile(r"^\d+\.\d+\.\d+$")
RELEASE_RE = re.compile(r"(?m)^##\s+\[(\d+\.\d+\.\d+)\].*$")


def test_version_is_numeric_semver_and_matches_latest_changelog_release():
    version = (ROOT / "VERSION").read_text(encoding="utf-8").strip()
    changelog = (ROOT / "CHANGELOG.md").read_text(encoding="utf-8")
    latest = RELEASE_RE.search(changelog)

    assert VERSION_RE.fullmatch(version), "VERSION must contain numeric semver only"
    assert latest, "CHANGELOG.md must contain at least one versioned release"
    assert latest.group(1) == version, (
        "VERSION must match the newest CHANGELOG.md release so What's New "
        "describes the installed version"
    )


def test_latest_release_contains_user_facing_whats_new_details():
    changelog = (ROOT / "CHANGELOG.md").read_text(encoding="utf-8")
    latest = RELEASE_RE.search(changelog)
    assert latest

    body = changelog[latest.end():]
    next_release = RELEASE_RE.search(body)
    if next_release:
        body = body[:next_release.start()]

    assert re.search(r"(?m)^[-*]\s+\S", body), (
        "The newest release must include bullet details for the in-app What's New panel"
    )
