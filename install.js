module.exports = {
  requires: {
    bundle: "ai"
  },
  run: [
    {
      method: "shell.run",
      params: {
        path: "app",
        conda: {
          "path": "{{path.resolve(cwd, 'conda_env')}}",
          "python": "python=3.12"
        },
        message: [
          "python -m pip install --upgrade pip",
          // Install from the fully-pinned lock, NOT the floors file — a fresh
          // machine months from now gets the exact package set this app was
          // last verified against, instead of whatever PyPI resolves that day.
          // (requirements.txt keeps the human-edited floors; see the lock's
          // header for the regenerate flow when upgrading deps on purpose.)
          "uv pip install -r requirements.lock.txt"
        ]
      }
    }
  ]
}
