from __future__ import annotations

import json
from pathlib import Path
import subprocess


ROOT = Path(__file__).parents[2]


def _launcher_menus() -> dict[str, list[dict]]:
    script = r"""
const launcher = require('./pinokio.js');
const generationFiles = [
  'generation/.installed',
  'conda_env/lib/python3.12/site-packages/mlx_lm',
  'conda_env/lib/python3.12/site-packages/mlx_vlm',
];
function info({ installed = true, generation = true, service = false,
                running = [], local = {} }) {
  return {
    exists(path) {
      if (path === 'conda_env') return installed;
      if (path === 'service/.installed') return service;
      if (generationFiles.includes(path)) return generation;
      return false;
    },
    running(path) { return running.includes(path); },
    local(path) { return path === 'start.js' ? local : {}; },
  };
}
(async () => {
  const scenarios = {
    service: { service: true },
    running_ready: { running: ['start.js'], local: { url: 'http://0.0.0.0:47871' } },
    running_starting: { running: ['start.js'] },
    stopped_missing_generation: { generation: false },
    installing: { running: ['install.js'] },
    installing_generation: { running: ['install_generation.js'] },
    updating: { running: ['update.js'] },
    updating_restart: { running: ['update_and_restart.js'] },
    resetting: { running: ['reset.js'] },
    uninstalled: { installed: false, generation: false },
  };
  const result = {};
  for (const [name, state] of Object.entries(scenarios)) {
    result[name] = await launcher.menu({}, info(state));
  }
  console.log(JSON.stringify(result));
})().catch(error => { console.error(error); process.exit(1); });
"""
    result = subprocess.run(
        ["node", "-e", script], cwd=ROOT, check=True, capture_output=True, text=True
    )
    return json.loads(result.stdout)


def _hrefs(menu: list[dict]) -> list[str]:
    return [str(item.get("href", "")) for item in menu]


def test_whats_new_is_visible_in_every_launcher_state() -> None:
    for state, menu in _launcher_menus().items():
        assert any(
            item.get("href") == "whats_new.js" and item.get("text") == "What's New"
            for item in menu
        ), state


def test_chat_entries_and_common_sidebar_order_are_preserved() -> None:
    menus = _launcher_menus()
    for state in ("service", "running_ready"):
        hrefs = _hrefs(menus[state])
        for route in ("#/chat", "#/models", "#/downloads"):
            assert any(route in href for href in hrefs), (state, route)
        assert next(i for i, href in enumerate(hrefs) if "#/chat" in href) < next(
            i for i, href in enumerate(hrefs) if "open_external.js" in href
        )
        assert hrefs.index("update.js") < hrefs.index("whats_new.js")

    stopped = _hrefs(menus["stopped_missing_generation"])
    assert stopped[-2:] == ["install.js", "reset.js"]
    assert stopped.index("update.js") < stopped.index("whats_new.js")

    service = _hrefs(menus["service"])
    assert service[-1] == "unservice.js"
    assert service.index("update.js") < service.index("whats_new.js")


def test_generation_action_remains_available_in_regular_and_service_modes() -> None:
    menus = _launcher_menus()
    for state in ("service", "running_ready", "running_starting"):
        actions = {item.get("href"): item.get("text") for item in menus[state]}
        assert actions["install_generation.js"] == "Reinstall Generation"
    missing = {item.get("href"): item.get("text") for item in menus["stopped_missing_generation"]}
    assert missing["install_generation.js"] == "Install Generation"


def test_whats_new_displays_the_local_changelog() -> None:
    source = (ROOT / "whats_new.js").read_text(encoding="utf-8")
    assert 'method: "fs.cat"' in source
    assert 'path: "CHANGELOG.md"' in source
