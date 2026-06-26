function studio() {
  return {
    // ── nav / meta ──
    tab: "chat",
    apiBase: window.location.origin,
    appVersion: "",

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

    // ── RAM slider (Models tab hardware planner) ──
    // Effective unified-memory budget used to score every model's fit chip
    // LIVE on the client. Defaults to detected RAM; the user can drag/type it
    // to preview a different machine (e.g. plan a 512 GB Mac before buying
    // it). Seeded in _initRamPlanner() after /api/system.
    ramGb: null,
    ramIsDetected: true,
    ramTiers: [8, 16, 24, 32, 48, 64, 128, 256, 512],

    // ── chat ──
    diag: { available: false, error: null, packages: [] },
    depInstall: { running: false, result: null },
    continueState: null,   // {messageIndex, excludeIds, provider} when a stream broke mid-answer
    continuing: false,

    // ── cloud providers ──
    providers: [],
    providerKeyInputs: {},
    providerSaving: null,
    providerTests: {},
    liveModels: {},        // { providerKey: [{id, repo}] } fetched on demand
    liveLoading: null,
    modelTab: null,        // 'local' | 'cloud' (null = auto-pick)
    showAllProviders: false, // cloud tab: also show providers with no key (greyed)
    routerProviders: [],   // ordered fallback list {id,name,kind,enabled,key_set}
    providerHealth: {},    // { id: 'online'|'offline'|'rate_limited'|'no_key'|'slow'|'unknown' }
    healthLoading: false,
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
      this.loadLive();
      await this.refreshHealth();
      await this.refreshSystem();
      // Seed the RAM-slider budget from detected RAM (or a saved override).
      this._initRamPlanner();
      await this.refreshCatalog();
      await this.refreshDiagnostics();
      await this.refreshChatModels();
      await this.refreshProviders();
      await this.refreshConnectivity();
      this.pickDefaultModel();
      this.pollDownloads();
      setInterval(() => this.refreshHealth(), 15000);
      // Provider health (Uninterrupted Mode): on launch + every 5 minutes.
      this.refreshRouterProviders();
      this.refreshProviderHealth();
      setInterval(() => this.refreshProviderHealth(), 300000);
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
      if (tab === "settings") { this.refreshSettings(); this.refreshConnectivity(); this.refreshDiagnostics(); this.refreshProviders(); this.refreshRouterProviders(); this.refreshProviderHealth(); }
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
      try {
        this.diag = await (await fetch(`${this.apiBase}/api/chat/diagnostics`)).json();
        if (this.diag.app_version) this.appVersion = this.diag.app_version;
      }
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
        const [local, prov] = await Promise.all([
          fetch(`${this.apiBase}/api/chat/models`).then(r => r.json()).catch(() => ({models: []})),
          fetch(`${this.apiBase}/api/providers`).then(r => r.json()).catch(() => ({providers: []})),
        ]);
        const locals = (local.models || []).map(m => ({...m, source: 'local'}));
        const clouds = [];
        for (const p of (prov.providers || [])) {
          for (const m of p.models) {
            // Paid models stay hidden from the dropdown until the user enables
            // paid for that provider.
            if (!m.free && !p.paid_enabled) continue;
            clouds.push({
              repo: m.repo,
              label: m.label + (m.free ? '' : ' 💲'),
              source: 'cloud',
              provider: p.key,
              provider_name: p.name,
              notes: m.notes,
              key_set: p.key_set,
              free: m.free,
            });
          }
        }
        // Live-fetched models (loaded on demand per provider) — appended and
        // deduped against curated, so the dropdown can reflect a provider's
        // full current catalog instead of only the hardcoded list.
        const provByKey = {};
        for (const p of (prov.providers || [])) provByKey[p.key] = p;
        const have = new Set(clouds.map(c => c.repo));
        for (const [pkey, models] of Object.entries(this.liveModels || {})) {
          const p = provByKey[pkey];
          if (!p) continue;
          for (const m of (models || [])) {
            if (have.has(m.repo)) continue;
            have.add(m.repo);
            clouds.push({
              repo: m.repo, label: m.id, source: 'cloud', provider: pkey,
              provider_name: p.name, notes: 'live', key_set: p.key_set, free: true, live: true,
            });
          }
        }
        this.chatModels = [...locals, ...clouds];
        const loaded = this.chatModels.find(m => m.loaded);
        if (loaded) this.currentRepo = loaded.repo;
      } catch (e) {}
    },
    // Which picker tab is showing — explicit choice, else Local if any local
    // models exist, else Cloud.
    effectiveModelTab() {
      if (this.modelTab) return this.modelTab;
      return this.chatModels.some(m => m.source === 'local') ? 'local' : 'cloud';
    },
    // Optgroups for the model <select>, scoped to the active tab.
    //  · Local tab → one "Local (MLX)" group.
    //  · Cloud tab → one group per provider (so identical model names from
    //    different providers stay distinguishable). Providers with no API key
    //    are hidden unless "show all" is on, and then rendered greyed/disabled.
    groupedModels() {
      const tab = this.effectiveModelTab();
      if (tab === 'local') {
        const locals = this.chatModels.filter(m => m.source === 'local');
        return locals.length ? [{ label: '🖥 Local (MLX)', models: locals, disabled: false }] : [];
      }
      const order = [];
      const byProv = {};
      for (const m of this.chatModels) {
        if (m.source !== 'cloud') continue;
        const k = m.provider || 'cloud';
        if (!byProv[k]) {
          byProv[k] = { label: '☁ ' + (m.provider_name || 'Cloud'), models: [], key_set: !!m.key_set };
          order.push(k);
        }
        byProv[k].models.push(m);
      }
      const groups = [];
      for (const k of order) {
        const g = byProv[k];
        g.disabled = !g.key_set;
        if (g.disabled && !this.showAllProviders) continue;  // keyless hidden by default
        if (g.disabled) g.label += ' — needs key';
        groups.push(g);
      }
      return groups;
    },
    // Switch tab; keep selection valid for what's now shown.
    setModelTab(tab) {
      this.modelTab = tab;
      const selectable = this.groupedModels().flatMap(g => g.disabled ? [] : g.models);
      if (!selectable.find(m => m.repo === this.selectedRepo)) {
        this.selectedRepo = (selectable[0] && selectable[0].repo) || "";
      }
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

    // ── RAM slider + client-side hardware fit ──
    /** Effective RAM budget (GB): slider value, else detected, else 16. */
    get effectiveRam() {
      return this.ramGb || this.system.unified_memory_gb || 16;
    },
    /** Client-side fit verdict vs effectiveRam. Mirrors backend
     *  system_info.fit_for() (1.5× comfortable / 1.0× tight / below = over)
     *  so the RAM slider re-scores every card instantly. Returns a `label`
     *  too, since the model cards render m.fit.label. */
    fitFor(minGb) {
      const actual = this.effectiveRam;
      const floor = Math.max(Number(minGb) || 0, 1);
      const headroom = actual / floor;
      let state, label;
      if (headroom >= 1.5)      { state = "ok";    label = "✓ fits"; }
      else if (headroom >= 1.0) { state = "tight"; label = "⚠ tight"; }
      else                      { state = "risky"; label = "✗ over budget"; }
      const hint = headroom >= 1.5
        ? `${actual} GB is ≥1.5× this model's ${minGb} GB floor — comfortable headroom.`
        : headroom >= 1.0
          ? `${actual} GB just clears the ${minGb} GB floor — close other apps before loading.`
          : `${actual} GB is below the ${minGb} GB floor — it would swap heavily or fail to load.`;
      return { state, label, hint, actual_gb: actual, required_gb: Number(minGb) || 0 };
    },
    setRam(gb) {
      const v = Math.max(1, Math.min(1024, Math.round(Number(gb) || 0)));
      this.ramGb = v;
      this.ramIsDetected = (v === this.system.unified_memory_gb);
      try { localStorage.setItem("chatstudio.ramGb", String(v)); } catch {}
    },
    resetRamToDetected() {
      const d = this.system.unified_memory_gb;
      if (d) this.setRam(d);
    },
    _initRamPlanner() {
      try {
        const saved = localStorage.getItem("chatstudio.ramGb");
        if (saved !== null && !isNaN(+saved)) {
          this.ramGb = +saved;
          this.ramIsDetected = (+saved === this.system.unified_memory_gb);
          return;
        }
      } catch {}
      this.ramGb = this.system.unified_memory_gb || 16;
      this.ramIsDetected = !!this.system.unified_memory_gb;
    },
    /** "✨ Best for your RAM" — highest-quality model in each lane (overall /
     *  starter / coder / reasoning) that still fits the budget. Live. */
    bestPicks() {
      const fits  = (m) => this.fitFor(m.min_unified_memory_gb).state !== "risky";
      const score = (m) => (Number(m.min_unified_memory_gb) || 0) * 1000
                         + (Number(m.size_gb) || 0) * 10
                         + (/recommended/i.test(m.label || "") ? 5 : 0);
      const pick = (predicate) => {
        const c = (this.models || []).filter(m => fits(m) && predicate(m));
        return c.length ? c.slice().sort((a, b) => score(b) - score(a))[0] : null;
      };
      const buckets = [
        { id: "overall",   label: "Best overall",   icon: "🏆", model: pick(() => true) },
        { id: "coder",     label: "Best for code",  icon: "💻", model: pick(m => m.is_coder) },
        { id: "reasoning", label: "Best reasoning", icon: "🧠", model: pick(m => m.is_reasoning) },
        { id: "starter",   label: "Best starter",   icon: "⭐", model: pick(m => m.is_starter) },
      ];
      const seen = new Set();
      return buckets.filter(b => {
        if (!b.model || seen.has(b.model.repo)) return false;
        seen.add(b.model.repo);
        return true;
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
        // Scored live against the RAM slider. The "over" button maps to the
        // "risky" fit state (the segmented control's label is "Over").
        const st = this.fitFor(m.min_unified_memory_gb).state;
        const want = this.fitFilter === "over" ? "risky" : this.fitFilter;
        if (st !== want) return false;
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
      // Cloud models don't need a load step — just set them as current.
      if (repo && repo.startsWith("provider:")) {
        this.currentRepo = repo;
        this.selectedRepo = repo;
        return;
      }
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
    newChat() { this.stopGen(); this.messages = []; this.streamingText = ""; this.continueState = null; },

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
      this.continueState = null;   // a new message supersedes any pending "continue"
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
        // Uninterrupted Mode appends a trailing "__CHATSTUDIO_META__{json}"
        // sentinel saying which provider answered / whether it fell back.
        // Strip it from the displayed text and parse it for the footer.
        const MARK = "\n__CHATSTUDIO_META__";
        let raw = "";
        while (true) {
          const { value, done } = await reader.read();
          if (done) break;
          raw += decoder.decode(value, { stream: true });
          const mi = raw.indexOf(MARK);
          this.streamingText = mi >= 0 ? raw.slice(0, mi) : raw;
          this.scrollThread();
        }
        let providerMeta = null, finalText = raw;
        const mi = raw.indexOf(MARK);
        if (mi >= 0) {
          try { providerMeta = JSON.parse(raw.slice(mi + MARK.length)); } catch (e) {}
          finalText = raw.slice(0, mi);
        }
        this.finishAssistant(finalText, t0, false, providerMeta);
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
    finishAssistant(content, t0, stopped, providerMeta) {
      const secs = (performance.now() - t0) / 1000;
      const approxTok = Math.max(1, Math.round((content || "").length / 4));
      const tps = secs > 0 ? (approxTok / secs).toFixed(1) : "—";
      let prefix = "";
      if (providerMeta && providerMeta.provider) {
        prefix = (providerMeta.interrupted ? "⚠ interrupted on " : "via ") + providerMeta.provider
               + (providerMeta.fallback ? " ⤵ fell back" : "") + " · ";
      }
      const meta = prefix + `~${approxTok} tok · ${secs.toFixed(1)}s · ~${tps} tok/s` + (stopped ? " · stopped" : "");
      if ((content || "").trim()) {
        this.messages.push({ role: "assistant", content, meta });
        if (providerMeta && providerMeta.interrupted) {
          this.continueState = {
            messageIndex: this.messages.length - 1,
            excludeIds: providerMeta.provider_id ? [providerMeta.provider_id] : [],
            provider: providerMeta.provider,
          };
        }
      }
    },
    async continueGeneration() {
      if (!this.continueState || this.streaming || this.continuing) return;
      const st = this.continueState;
      this.continueState = null;
      this.continuing = true;
      const idx = st.messageIndex;
      const base = this.messages[idx].content + "\n";
      // Send conversation up to + including the partial answer, then a hidden
      // "continue" instruction, excluding the provider that just broke.
      const payloadMsgs = [];
      if (this.gen.system && this.gen.system.trim()) payloadMsgs.push({ role: "system", content: this.gen.system.trim() });
      for (let i = 0; i <= idx; i++) payloadMsgs.push({ role: this.messages[i].role, content: this.messages[i].content });
      payloadMsgs.push({ role: "user", content: "Continue your previous response from exactly where it stopped. Do not repeat anything you already wrote." });

      this._abort = new AbortController();
      try {
        const r = await fetch(`${this.apiBase}/api/chat/completions`, {
          method: "POST", headers: { "content-type": "application/json" },
          signal: this._abort.signal,
          body: JSON.stringify({
            repo: this.currentRepo, messages: payloadMsgs,
            temperature: this.gen.temperature, max_tokens: this.gen.maxTokens, top_p: this.gen.topP,
            stream: true, exclude_providers: st.excludeIds,
          }),
        });
        if (!r.ok || !r.body) { const e = await r.json().catch(() => ({})); alert(e.detail || "Continue failed"); return; }
        const reader = r.body.getReader(); const decoder = new TextDecoder();
        const MARK = "\n__CHATSTUDIO_META__";
        let raw = "";
        while (true) {
          const { value, done } = await reader.read(); if (done) break;
          raw += decoder.decode(value, { stream: true });
          const mi = raw.indexOf(MARK);
          this.messages[idx].content = base + (mi >= 0 ? raw.slice(0, mi) : raw);
          this.scrollThread();
        }
        const mi = raw.indexOf(MARK); let meta = null, tail = raw;
        if (mi >= 0) { try { meta = JSON.parse(raw.slice(mi + MARK.length)); } catch (e) {} tail = raw.slice(0, mi); }
        this.messages[idx].content = base + tail;
        if (meta && meta.provider) {
          this.messages[idx].meta = (meta.interrupted ? "⚠ interrupted again on " : "continued via ") + meta.provider + (meta.fallback ? " ⤵" : "");
          if (meta.interrupted) {
            this.continueState = { messageIndex: idx, excludeIds: [...st.excludeIds, meta.provider_id].filter(Boolean), provider: meta.provider };
          }
        }
      } catch (e) {
        if (!(e && e.name === "AbortError")) alert(String(e));
      } finally {
        this.continuing = false; this._abort = null; this.scrollThread();
      }
    },
    stopGen() {
      // Tell the server to stop generating (frees the GPU now), then abort the
      // client stream. Without the server call, generation would run to
      // max_tokens in the background even though we stopped reading.
      fetch(`${this.apiBase}/api/chat/cancel`, { method: "POST" }).catch(() => {});
      if (this._abort) try { this._abort.abort(); } catch (e) {}
    },
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
    async saveUninterrupted() {
      await fetch(`${this.apiBase}/api/settings`, {
        method: "POST", headers: { "content-type": "application/json" },
        body: JSON.stringify({
          uninterrupted_mode: !!this.settings.uninterrupted_mode,
          request_timeout: Number(this.settings.request_timeout) || 60,
        }),
      });
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

    // ── cloud provider handlers ──
    async refreshProviders() {
      try {
        const d = await (await fetch(`${this.apiBase}/api/providers`)).json();
        this.providers = d.providers || [];
      } catch (e) { this.providers = []; }
    },
    async saveProviderKey(name) {
      const key = (this.providerKeyInputs[name] || "").trim();
      this.providerSaving = name;
      try {
        const r = await fetch(`${this.apiBase}/api/providers/${name}/key`, {
          method: "POST", headers: { "content-type": "application/json" },
          body: JSON.stringify({ api_key: key }),
        });
        const d = await r.json();
        if (r.ok) {
          this.providers = d.providers || [];
          this.providerKeyInputs[name] = "";
          this.providerTests[name] = { ok: true, msg: "✓ Saved" };
        } else {
          this.providerTests[name] = { ok: false, msg: "✗ " + (d.detail || "Save failed") };
        }
      } catch (e) { this.providerTests[name] = { ok: false, msg: "✗ " + String(e) }; }
      this.providerSaving = null;
      await this.refreshChatModels();
    },
    async testProvider(name) {
      const key = (this.providerKeyInputs[name] || "").trim();
      this.providerTests[name] = { ok: false, msg: "Testing…" };
      try {
        const r = await fetch(`${this.apiBase}/api/providers/${name}/test`, {
          method: "POST", headers: { "content-type": "application/json" },
          body: JSON.stringify({ api_key: key || null }),
        });
        const d = await r.json();
        if (r.ok && d.ok) {
          this.providerTests[name] = { ok: true, msg: `✓ Valid — ${d.models_available} models available` };
          this.providers = (await (await fetch(`${this.apiBase}/api/providers`)).json()).providers || [];
        } else {
          this.providerTests[name] = { ok: false, msg: "✗ " + (d.detail || `HTTP ${d.status || "?"}`) };
        }
      } catch (e) { this.providerTests[name] = { ok: false, msg: "✗ " + String(e) }; }
    },
    async loadLiveModels(name) {
      this.liveLoading = name;
      try {
        const r = await fetch(`${this.apiBase}/api/providers/${name}/models/live`);
        const d = await r.json();
        if (r.ok) {
          this.liveModels[name] = d.models || [];
          this.saveLive();
          await this.refreshChatModels();
          this.providerTests[name] = { ok: true, msg: `✓ Loaded ${d.count} live models` };
        } else {
          this.providerTests[name] = { ok: false, msg: "✗ " + (d.detail || "Failed to load models") };
        }
      } catch (e) { this.providerTests[name] = { ok: false, msg: "✗ " + String(e) }; }
      this.liveLoading = null;
    },
    clearLiveModels(name) {
      delete this.liveModels[name];
      this.saveLive();
      this.refreshChatModels();
    },
    saveLive() { try { localStorage.setItem("chatstudio.live", JSON.stringify(this.liveModels)); } catch (e) {} },
    loadLive() { try { const r = localStorage.getItem("chatstudio.live"); if (r) this.liveModels = JSON.parse(r) || {}; } catch (e) {} },
    async setProviderPaid(name, enabled) {
      try {
        const r = await fetch(`${this.apiBase}/api/providers/${name}/paid`, {
          method: "POST", headers: { "content-type": "application/json" },
          body: JSON.stringify({ enabled }),
        });
        const d = await r.json();
        if (r.ok) this.providers = d.providers || this.providers;
      } catch (e) {}
      // Refresh the chat dropdown so paid models appear/disappear immediately.
      await this.refreshChatModels();
    },

    // ── fallback priority + health (Uninterrupted Mode) ──
    async refreshRouterProviders() {
      try {
        const d = await (await fetch(`${this.apiBase}/api/router/providers`)).json();
        this.routerProviders = d.providers || [];
      } catch (e) {}
    },
    async refreshProviderHealth() {
      this.healthLoading = true;
      try {
        const d = await (await fetch(`${this.apiBase}/api/router/health`)).json();
        this.providerHealth = d.health || {};
      } catch (e) {} finally { this.healthLoading = false; }
    },
    async moveProvider(id, dir) {
      const ids = this.routerProviders.map(p => p.id);
      const i = ids.indexOf(id), j = i + dir;
      if (i < 0 || j < 0 || j >= ids.length) return;
      [ids[i], ids[j]] = [ids[j], ids[i]];
      try {
        const d = await (await fetch(`${this.apiBase}/api/router/order`, {
          method: "POST", headers: { "content-type": "application/json" },
          body: JSON.stringify({ order: ids }),
        })).json();
        this.routerProviders = d.providers || this.routerProviders;
      } catch (e) {}
    },
    async toggleProviderEnabled(id, enabled) {
      try {
        const d = await (await fetch(`${this.apiBase}/api/router/providers/${id}/enabled`, {
          method: "POST", headers: { "content-type": "application/json" },
          body: JSON.stringify({ enabled }),
        })).json();
        this.routerProviders = d.providers || this.routerProviders;
      } catch (e) {}
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
