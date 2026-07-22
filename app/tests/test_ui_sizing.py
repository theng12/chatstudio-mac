from __future__ import annotations

import re
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]


def test_readability_tokens_and_control_guard_match_studio_baseline() -> None:
    css = (ROOT / "app" / "frontend" / "style.css").read_text(encoding="utf-8")

    assert "--font-meta-min: 12px" in css
    assert "--font-control: 15px" in css
    assert "--control-min-height: 40px" in css
    assert "font-size: var(--font-control)" in css
    assert "min-height: var(--control-min-height)" in css


def test_stylesheet_does_not_reintroduce_sub_12px_text() -> None:
    css = (ROOT / "app" / "frontend" / "style.css").read_text(encoding="utf-8")
    undersized = [
        float(match.group(1))
        for match in re.finditer(r"font-size:\s*([0-9.]+)px", css)
        if float(match.group(1)) < 12
    ]

    assert undersized == [], "Use --font-meta-min instead of text smaller than 12px"


def test_templates_do_not_bypass_the_minimum_with_inline_text_sizes() -> None:
    html = (ROOT / "app" / "frontend" / "index.html").read_text(encoding="utf-8")
    undersized = [
        float(match.group(1))
        for match in re.finditer(r"font-size:\s*([0-9.]+)px", html)
        if float(match.group(1)) < 12
    ]

    assert undersized == [], "Use the shared metadata sizing guard instead of undersized inline text"
