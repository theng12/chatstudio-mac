// This is a freshly-created project (not cloned from a git remote), so there
// is no upstream "git pull" step — see VoiceStudio's update.js for the
// git-tracked-project version of this pattern. Update here just means
// reinstalling deps (in case requirements.txt changed) and restarting the
// startup service if one is installed, so it picks up the new backend code.
module.exports = {
  run: [
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
          "uv pip install -r requirements.txt"
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
