// Install or repair Chat Studio's MLX generation stack.
// Safe to run while either server mode is active: the install happens first,
// then only the active server mode is restarted so fresh imports are used.
module.exports = {
  requires: {
    bundle: "ai"
  },
  run: [
    {
      when: "{{running('start.js')}}",
      method: "script.stop",
      params: { uri: "start.js" }
    },
    {
      method: "shell.run",
      params: {
        path: "app",
        conda: { "path": "{{path.resolve(cwd, 'conda_env')}}" },
        message: [
          "uv pip install -r requirements-generation.txt"
        ]
      }
    },
    {
      method: "shell.run",
      params: {
        path: "app",
        conda: { "path": "{{path.resolve(cwd, 'conda_env')}}" },
        message: [
          "python -c \"from importlib.metadata import version; import mlx, mlx_lm, mlx_vlm, transformers, tokenizers; assert version('mlx') == '0.31.2'; assert version('mlx-lm') == '0.31.3'; assert version('mlx-vlm') == '0.6.4'; assert version('transformers') == '5.12.1'; assert version('tokenizers') == '0.22.2'; print('GEN_VERIFY_OK')\" 2>&1"
        ],
        on: [{ event: "/GEN_VERIFY_OK/", done: true }]
      }
    },
    {
      method: "shell.run",
      params: {
        message: [
          "mkdir -p generation && touch generation/.installed"
        ]
      }
    },
    {
      when: "{{exists('service/.installed')}}",
      method: "shell.run",
      params: { message: ["bash install_service.sh"] }
    },
    {
      when: "{{!exists('service/.installed')}}",
      method: "script.start",
      params: { uri: "start.js" }
    },
    {
      method: "notify",
      params: { html: "Generation engine installed &amp; verified. The active server mode is ready." }
    }
  ]
}
