function studio() {
  return {
    // ── nav / meta ──
    tab: "chat",
    apiBase: window.location.origin,
    appVersion: "__APP_VERSION__",

    health: { ok: false },
    system: {},
    conn: { addresses: [] },

    // ── catalog / downloads ──
    families: {},
    models: [],
    modelsByFamily: {},
    jobs: [],
    activeDownloadCount: 0,

    // ── model filter / sort ──
    modelSearch: "",
    fitFilter: "all",
    capFilter: "all",
    sortBy: "default",

    // ── chat ──
    diag: { available: false, error: null, packages: [] },
    depInstall: { running: false, result: null },
    chatModels: [],
    currentRepo: null,
    selectedRepo: "",
    loadingModel: null,
    messages: [],
    draft: "",
    streaming: false,
    streamingText: "",
    showParams: false,
    _abort: null,

    // ── generation defaults (persisted in localStorage) ──
    gen: { system: "", temperature: 0.7, maxTokens: 1024, topP: 1.0, defaultModel: "" },

    // ── settings ──
    settings: { hf_token_set: false, hf_token_masked: "" },
    hfTokenInput: "",
    tokenTest: { ok: false, msg: "" },

    // ── api tab ──
    lang: "curl",
    copied: null,

    // ════════════ lifecycle ════════════
    async init() {
      this.loadGen();
      await this.refreshHealth();
      await this.refreshSystem();
      await this.refreshCatalog();
      await this.refreshDiagnostics();
      await this.refreshChatModels();
      await this.refreshConnectivity();
      this.pickDefaultModel();
      this.pollDownloads();
      setInterval(() => this.refreshHealth(), 15000);
      // Auto-load the default model on startup if it's cached
      if (this.gen.defaultModel && this.diag.available) {
        const cached = this.models.find(m => m.repo === this.gen.defaultModel && m.cache?.state === "cached");
        if (cached && cached.repo !== this.currentRepo) {
          this.selectedRepo = cached.repo;
          await this.loadModel(cached.repo);
        }
      }
    },

    go(tab) {
      this.tab = tab;
      if (tab === "chat") { this.refreshDiagnostics(); this.refreshChatModels(); }
      if (tab === "models") this.refreshCatalog();
      if (tab === "api") this.refreshConnectivity();
      if (tab === "settings") { this.refreshSettings(); this.refreshConnectivity(); this.refreshDiagnostics(); }
    },

    async refreshAll() {
      await this.refreshHealth();
      await this.refreshDiagnostics();
      await this.refreshConnectivity();
      await this.refreshChatModels();
    },

    // ════════════ fetchers ════════════
    async refreshHealth() {
      try { this.health = await (await fetch(`${this.apiBase}/api/health`)).json(); }
      catch (e) { this.health = { ok: false }; }
    },
    async refreshSystem() {
      try { this.system = await (await fetch(`${this.apiBase}/api/system`)).json(); } catch (e) {}
    },
    async refreshConnectivity() {
      try { this.conn = await (await fetch(`${this.apiBase}/api/connectivity`)).json(); } catch (e) {}
    },
    async refreshCatalog() {
      try {
        const data = await (await fetch(`${this.apiBase}/api/catalog`)).json();
        this.families = data.families || {};
        this.models = data.models || [];
        const grouped = {};
        for (const m of this.models) (grouped[m.family] = grouped[m.family] || []).push(m);
        this.modelsByFamily = grouped;
      } catch (e) {}
    },
    async refreshDiagnostics() {
      try { this.diag = await (await fetch(`${this.apiBase}/api/chat/diagnostics`)).json(); }
      catch (e) { this.diag = { available: false, error: String(e), packages: [] }; }
    },
    async installDeps() {
      this.depInstall.running = true;
      this.depInstall.result = null;
      try {
        const r = await fetch(`${this.apiBase}/api/deps/install`, { method: "POST" });
        this.depInstall.result = await r.json();
      } catch (e) {
        this.depInstall.result = { ok: false, stdout: "", stderr: String(e) };
      } finally {
        this.depInstall.running = false;
        await this.refreshDiagnostics();
      }
    },
    async refreshChatModels() {
      try {
        const data = await (await fetch(`${this.apiBase}/api/chat/models`)).json();
        this.chatModels = data.models || [];
        const loaded = this.chatModels.find(m => m.loaded);
        if (loaded) this.currentRepo = loaded.repo;
      } catch (e) {}
    },
    async refreshSettings() {
      try { this.settings = await (await fetch(`${this.apiBase}/api/settings`)).json(); } catch (e) {}
    },

    // family display order: Llama, Qwen, Gemma 4/3/2, then the rest
    orderedFamilies() {
      const order = ["llama", "qwen", "gemma4", "gemma3", "gemma2", "mistral", "phi", "deepseek"];
      const fams = Object.values(this.families).filter(f => (this.modelsByFamily[f.id] || []).length > 0);
      return fams.sort((a, b) => {
        const ia = order.indexOf(a.id), ib = order.indexOf(b.id);
        return (ia < 0 ? 99 : ia) - (ib < 0 ? 99 : ib);
      });
    },

    // ── model filter / sort logic ──
    filteredFamilies() {
      const order = ["llama", "qwen", "gemma4", "gemma3", "gemma2", "mistral", "phi", "deepseek"];
      const fams = Object.values(this.families).filter(f => {
        const ms = this.modelsByFamily[f.id] || [];
        return ms.some(m => this._passesFilter(m));
      });
      return fams.sort((a, b) => {
        const ia = order.indexOf(a.id), ib = order.indexOf(b.id);
        return (ia < 0 ? 99 : ia) - (ib < 0 ? 99 : ib);
      });
    },
    filteredModels(familyId) {
      const ms = (this.modelsByFamily[familyId] || []).filter(m => this._passesFilter(m));
      return this._sorted(ms);
    },
    visibleModelCount() {
      return this.models.filter(m => this._passesFilter(m)).length;
    },
    visibleFamilyCount() {
      return Object.values(this.families).filter(f => {
        const ms = this.modelsByFamily[f.id] || [];
        return ms.some(m => this._passesFilter(m));
      }).length;
    },
    _passesFilter(m) {
      if (this.modelSearch) {
        const q = this.modelSearch.toLowerCase();
        const label = (m.label || "").toLowerCase();
        const repo = (m.repo || "").toLowerCase();
        if (!label.includes(q) && !repo.includes(q)) return false;
      }
      if (this.fitFilter !== "all") {
        if ((m.fit?.state || "") !== this.fitFilter) return false;
      }
      if (this.capFilter !== "all") {
        if (this.capFilter === "starter" && !m.is_starter) return false;
        if (this.capFilter === "coder" && !m.is_coder) return false;
        if (this.capFilter === "reasoning" && !m.is_reasoning) return false;
      }
      return true;
    },
    _sorted(ms) {
      const arr = [...ms];
      if (this.sortBy === "size") arr.sort((a, b) => a.size_gb - b.size_gb);
      else if (this.sortBy === "ram") arr.sort((a, b) => a.min_unified_memory_gb - b.min_unified_memory_gb);
      else if (this.sortBy === "name") arr.sort((a, b) => (a.label || "").localeCompare(b.label || ""));
      return arr;
    },

    // ════════════ model loading ════════════
    pickDefaultModel() {
      if (!this.selectedRepo) {
        this.selectedRepo = this.currentRepo || (this.chatModels[0] && this.chatModels[0].repo) || "";
      }
    },
    onPickModel() {
      // changing the dropdown loads the chosen model
      if (this.selectedRepo && this.selectedRepo !== this.currentRepo) this.loadModel(this.selectedRepo);
    },
    async loadModel(repo) {
      this.loadingModel = repo;
      try {
        const r = await fetch(`${this.apiBase}/api/chat/load`, {
          method: "POST", headers: { "content-type": "application/json" },
          body: JSON.stringify({ repo }),
        });
        if (!r.ok) {
          const err = await r.json().catch(() => ({}));
          alert(err.detail || "Failed to load model");
          return;
        }
        this.currentRepo = repo;
        this.selectedRepo = repo;
        await this.refreshChatModels();
      } finally { this.loadingModel = null; }
    },
    loadFromModels(repo) {
      // "Chat with this" button on the Models tab
      this.go("chat");
      this.selectedRepo = repo;
      if (repo !== this.currentRepo) this.loadModel(repo);
    },
    newChat() { this.stopGen(); this.messages = []; this.streamingText = ""; },

    // ════════════ chat send / stream ════════════
    onEnter(e) {
      if (e.shiftKey) return;            // Shift+Enter = newline
      e.preventDefault();
      this.sendMessage();
    },
    autogrow() {
      const el = this.$refs.composer;
      if (!el) return;
      el.style.height = "auto";
      el.style.height = Math.min(el.scrollHeight, 180) + "px";
    },
    async sendMessage() {
      const text = this.draft.trim();
      if (!text || !this.currentRepo || this.streaming) return;
      this.messages.push({ role: "user", content: text });
      this.draft = "";
      this.autogrow();
      this.streaming = true;
      this.streamingText = "";
      this.scrollThread();

      // assemble messages (+ optional system prompt)
      const payloadMsgs = [];
      if (this.gen.system && this.gen.system.trim()) payloadMsgs.push({ role: "system", content: this.gen.system.trim() });
      for (const m of this.messages) payloadMsgs.push({ role: m.role, content: m.content });

      this._abort = new AbortController();
      const t0 = performance.now();
      try {
        const r = await fetch(`${this.apiBase}/api/chat/completions`, {
          method: "POST", headers: { "content-type": "application/json" },
          signal: this._abort.signal,
          body: JSON.stringify({
            repo: this.currentRepo,
            messages: payloadMsgs,
            temperature: this.gen.temperature,
            max_tokens: this.gen.maxTokens,
            top_p: this.gen.topP,
            stream: true,
          }),
        });
        if (!r.ok || !r.body) {
          const err = await r.json().catch(() => ({}));
          this.messages.push({ role: "assistant", content: "⚠️ " + (err.detail || r.statusText) });
          return;
        }
        const reader = r.body.getReader();
        const decoder = new TextDecoder();
        while (true) {
          const { value, done } = await reader.read();
          if (done) break;
          this.streamingText += decoder.decode(value, { stream: true });
          this.scrollThread();
        }
        this.finishAssistant(this.streamingText, t0);
      } catch (e) {
        if (e && e.name === "AbortError") {
          this.finishAssistant(this.streamingText + " ⏹", t0, true);
        } else {
          this.messages.push({ role: "assistant", content: "⚠️ " + String(e) });
        }
      } finally {
        this.streaming = false;
        this.streamingText = "";
        this._abort = null;
        this.scrollThread();
        this.$nextTick(() => { const el = this.$refs.composer; if (el) el.focus(); });
      }
    },
    finishAssistant(content, t0, stopped) {
      const secs = (performance.now() - t0) / 1000;
      const approxTok = Math.max(1, Math.round((content || "").length / 4));
      const tps = secs > 0 ? (approxTok / secs).toFixed(1) : "—";
      const meta = `~${approxTok} tok · ${secs.toFixed(1)}s · ~${tps} tok/s` + (stopped ? " · stopped" : "");
      if ((content || "").trim()) this.messages.push({ role: "assistant", content, meta });
    },
    stopGen() { if (this._abort) try { this._abort.abort(); } catch (e) {} },
    scrollThread() {
      this.$nextTick(() => { const el = this.$refs.thread; if (el) el.scrollTop = el.scrollHeight; });
    },
    shortName(repo) {
      const m = this.chatModels.find(x => x.repo === repo);
      if (m) return m.label.replace(/\s*\(.*\)\s*$/, "");
      return (repo || "").split("/").pop();
    },

    // ════════════ markdown (tiny, XSS-safe: escape first) ════════════
    escapeHtml(s) { return (s || "").replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;"); },
    renderMarkdown(src) {
      if (!src) return "";
      const parts = String(src).split("```");
      let out = "";
      for (let i = 0; i < parts.length; i++) {
        if (i % 2 === 1) {
          // fenced code block (also handles an unterminated final block while streaming)
          let code = parts[i];
          const nl = code.indexOf("\n");
          if (nl > 0) {
            const first = code.slice(0, nl).trim();
            if (/^[a-z0-9+#._-]{1,16}$/i.test(first)) code = code.slice(nl + 1);
          }
          out += '<pre class="code"><code>' + this.escapeHtml(code.replace(/\n$/, "")) + "</code></pre>";
        } else {
          out += this.renderInline(parts[i]);
        }
      }
      return out;
    },
    renderInline(text) {
      let t = this.escapeHtml(text);
      t = t.replace(/^(\s*)[-*]\s+/gm, "$1• ");                       // bullets
      t = t.replace(/`([^`]+)`/g, '<code class="inline">$1</code>');   // inline code
      t = t.replace(/\*\*([^*]+)\*\*/g, "<strong>$1</strong>");        // bold
      t = t.replace(/(^|[^*])\*([^*\n]+)\*(?!\*)/g, "$1<em>$2</em>");   // italic
      t = t.replace(/\[([^\]]+)\]\((https?:[^)\s]+)\)/g, '<a href="$2" target="_blank" rel="noopener">$1</a>');
      t = t.replace(/\n/g, "<br>");
      return t;
    },

    // ════════════ downloads ════════════
    async startDownload(repo) {
      await fetch(`${this.apiBase}/api/downloads`, {
        method: "POST", headers: { "content-type": "application/json" },
        body: JSON.stringify({ repo }),
      });
      await this.refreshCatalog();
      await this.refreshDownloads();
    },
    async cancelDownload(jobId) {
      await fetch(`${this.apiBase}/api/downloads/${jobId}`, { method: "DELETE" });
      await this.refreshDownloads();
      await this.refreshCatalog();
    },
    async refreshDownloads() {
      try {
        const data = await (await fetch(`${this.apiBase}/api/downloads`)).json();
        this.jobs = data.jobs || [];
        this.activeDownloadCount = this.jobs.filter(j => ["queued", "running", "cancelling"].includes(j.state)).length;
      } catch (e) {}
    },
    pollDownloads() {
      this.refreshDownloads();
      setInterval(async () => {
        await this.refreshDownloads();
        if (this.activeDownloadCount > 0) {
          await this.refreshCatalog();
        } else if (this._hadDownloads) {
          // a download just finished — refresh chat model list so it appears
          await this.refreshCatalog();
          await this.refreshChatModels();
          this.pickDefaultModel();
        }
        this._hadDownloads = this.activeDownloadCount > 0;
      }, 2000);
    },

    // ════════════ settings ════════════
    async saveSettings() {
      await fetch(`${this.apiBase}/api/settings`, {
        method: "POST", headers: { "content-type": "application/json" },
        body: JSON.stringify({ hf_token: this.hfTokenInput }),
      });
      this.hfTokenInput = "";
      this.tokenTest = { ok: false, msg: "" };
      await this.refreshSettings();
    },
    async testToken() {
      this.tokenTest = { ok: false, msg: "Testing…" };
      try {
        const r = await fetch(`${this.apiBase}/api/settings/test-hf-token`, {
          method: "POST", headers: { "content-type": "application/json" },
          body: JSON.stringify({ hf_token: this.hfTokenInput || null }),
        });
        const d = await r.json();
        if (r.ok) this.tokenTest = { ok: true, msg: `✓ Valid — signed in as ${d.name || "user"}` };
        else this.tokenTest = { ok: false, msg: "✗ " + (d.detail || "Invalid token") };
      } catch (e) { this.tokenTest = { ok: false, msg: "✗ " + String(e) }; }
    },

    // generation settings persistence
    loadGen() {
      try {
        const raw = localStorage.getItem("chatstudio.gen");
        if (raw) this.gen = Object.assign(this.gen, JSON.parse(raw));
      } catch (e) {}
    },
    saveGen() {
      try { localStorage.setItem("chatstudio.gen", JSON.stringify(this.gen)); } catch (e) {}
    },
    resetGen() {
      const oldDefault = this.gen.defaultModel;
      this.gen = { system: "", temperature: 0.7, maxTokens: 1024, topP: 1.0, defaultModel: oldDefault };
      this.saveGen();
    },
    cachedModelRepos() {
      return this.models.filter(m => m.cache?.state === "cached").map(m => ({ repo: m.repo, label: m.label }));
    },
    setDefaultModel(repo) {
      this.gen.defaultModel = repo || "";
      this.saveGen();
    },

    // ════════════ API tab helpers ════════════
    cachedRepos() { return this.models.filter(m => m.cache && m.cache.state === "cached").map(m => m.repo); },
    snippetModel() {
      return this.currentRepo || this.cachedRepos()[0] || "mlx-community/Llama-3.2-3B-Instruct-4bit";
    },
    snippet() {
      const base = this.apiBase + "/v1";
      const model = this.snippetModel();
      if (this.lang === "curl") {
        return `curl ${base}/chat/completions \\
  -H "Content-Type: application/json" \\
  -H "Authorization: Bearer sk-local" \\
  -d '{
    "model": "${model}",
    "messages": [{"role": "user", "content": "Hello!"}],
    "stream": false
  }'`;
      }
      if (this.lang === "python") {
        return `from openai import OpenAI

client = OpenAI(base_url="${base}", api_key="sk-local")

resp = client.chat.completions.create(
    model="${model}",
    messages=[{"role": "user", "content": "Hello!"}],
)
print(resp.choices[0].message.content)`;
      }
      return `const res = await fetch("${base}/chat/completions", {
  method: "POST",
  headers: { "Content-Type": "application/json", "Authorization": "Bearer sk-local" },
  body: JSON.stringify({
    model: "${model}",
    messages: [{ role: "user", content: "Hello!" }],
  }),
});
const data = await res.json();
console.log(data.choices[0].message.content);`;
    },

    // ════════════ formatting helpers ════════════
    formatBytes(b) {
      if (!b || b <= 0) return "—";
      const units = ["B", "KB", "MB", "GB", "TB"];
      let i = 0;
      let v = b;
      while (v >= 1024 && i < units.length - 1) { v /= 1024; i++; }
      return v.toFixed(i === 0 ? 0 : 1) + " " + units[i];
    },
    formatDuration(s) {
      if (!s || s <= 0 || !isFinite(s)) return "—";
      if (s < 60) return Math.round(s) + "s";
      if (s < 3600) return Math.floor(s / 60) + "m " + Math.round(s % 60) + "s";
      const h = Math.floor(s / 3600);
      return h + "h " + Math.floor((s % 3600) / 60) + "m";
    },

    // ════════════ clipboard ════════════
    async copy(text, key) {
      try { await navigator.clipboard.writeText(text); }
      catch (e) {
        const ta = document.createElement("textarea");
        ta.value = text; document.body.appendChild(ta); ta.select();
        try { document.execCommand("copy"); } catch (_) {}
        document.body.removeChild(ta);
      }
      this.copied = key;
      setTimeout(() => { if (this.copied === key) this.copied = null; }, 1500);
    },
  };
}
