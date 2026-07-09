// Update = pull the latest code from GitHub (when this copy is a git clone,
// e.g. installed via Pinokio's "Download from URL"), converge deps onto the
// committed lockfile, and restart the startup service if one is installed so
// the running server picks up the new code.
module.exports = {
  run: [
    {
      // No-op for a non-git copy; on git clones this brings launcher scripts,
      // backend code, AND the dep lockfile up to date in one step.
      when: "{{exists('.git')}}",
      method: "shell.run",
      params: {
        message: [ "git pull" ]
      }
    },
    {
      when: "{{exists('conda_env')}}",
      method: "shell.run",
      params: {
        path: "app",
        conda: {
          "path": "{{path.resolve(cwd, 'conda_env')}}"
        },
        message: [
          "python -m pip install --upgrade pip",
          // Same lockfile as install.js — Update converges the env onto the
          // exact pinned set (upgrades happen by regenerating the lock, not
          // by letting PyPI drift underneath us).
          "uv pip install -r requirements.lock.txt"
        ]
      }
    },
    {
      // If this Mac runs the app as a launchd startup service, restart it after
      // updating so it picks up the new backend code (the running service keeps
      // the OLD code in memory until restarted). No-op when not installed.
      when: "{{exists('service/.installed')}}",
      method: "shell.run",
      params: {
        message: [ "bash restart_service.sh" ]
      }
    }
  ]
}
