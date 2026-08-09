function studio() {
  return {
    // ── nav / meta ──
    tab: "chat",
    apiBase: window.location.origin,
    appVersion: "",
    showWhatsNew: false,
    releaseNotesCurrent: "",
    releaseNotes: [],

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
    modelAdvancedOpen: false,
    openModelFamilies: new Set(),
    expandedModelRepos: new Set(),

    // Hugging Face discovery stays separate from the curated family library.
    // It uses the existing MLX-only Hub endpoint and the same download queue.
    hubQuery: "",
    hubResults: [],
    hubLoading: false,
    hubError: "",

    // ── RAM slider (Models tab hardware planner) ──
    // Effective unified-memory budget used to score every model's fit chip
    // LIVE on the client. Defaults to detected RAM; the user can drag/type it
    // to preview a different machine (e.g. plan a 512 GB Mac before buying
    // it). Seeded in _initRamPlanner() after /api/system.
    ramGb: null,
    ramIsDetected: true,
    ramTiers: [8, 16, 24, 32, 48, 64, 128, 256, 512],

    // ── chat ──
    diag: { checked: false, available: false, error: null, packages: [] },
    depInstall: { running: false, result: null },
    chatModels: [],
    currentRepo: null,
    selectedRepo: "",
    loadingModel: null,
    messages: [],
    draft: "",
    draftImages: [],   // data URLs attached to the next message (vision models)
    streaming: false,
    streamingText: "",
    showParams: false,
    _abort: null,

    // ── chat sessions (history) ──
    sessions: [],
    sessionSearch: "",
    currentSessionId: null,
    sessionDeleteArmed: null,
    _sessionDeleteTimer: null,
    showSidebar: window.innerWidth > 700,

    // ── transient toast + idle-unload tracking ──
    toast: "",
    _toastT: null,
    _lastAutoUnloadAt: 0,
    _seenAutoUnload: false,

    // ── generation defaults (persisted in localStorage) ──
    gen: { system: "", temperature: 0.7, maxTokens: 1024, topP: 1.0, defaultModel: "" },

    // ── settings ──
    settings: { hf_token_set: false, hf_token_masked: "" },
    autoUpdate: {
      loaded:false, busy:false, message:"", messageKind:"info", state:"idle",
      installed_version:"", latest_version:null, last_checked:null, next_check:null,
      last_update_result:null, defer_reason:null, rollback:null, details:[],
      update_available:false, scheduler:{installed:false}, release_notes_url:"",
      settings:{mode:"off",frequency:"daily",maintenance_hour:3,idle_only:true},
      draft:{mode:"off",frequency:"daily",maintenance_hour:3,idle_only:true},
      dirty:false,
    },
    storagePolicy: { enabled:true, retention_days:30, max_gb:80, used_bytes:0, supported:false, loaded:false, busy:false, message:"" },
    memoryPolicy: {
      mode:"performance", default_mode:"performance", idle_seconds:null,
      loaded_model:null, model_idle_seconds:null, next_release_at:null,
      last_release_at:null, last_release_reason:null, release_count:0,
      process_title:"Chat Studio Mac", process_title_applied:false,
      loaded:false, busy:false, message:"", messageKind:"info",
      draft:{mode:"performance"}, dirty:false,
    },
    hfTokenInput: "",
    tokenTest: { ok: false, msg: "" },

    // ── api tab ──
    lang: "curl",
    copied: null,

    // ════════════ lifecycle ════════════
    async init() {
      this.loadGen();
      await this.refreshReleaseNotes();
      await this.refreshHealth();
      await this.refreshSystem();
      // Seed the RAM-slider budget from detected RAM (or a saved override).
      this._initRamPlanner();
      await this.refreshCatalog();
      await this.refreshDiagnostics();
      await this.refreshChatModels();
      await this.refreshStoragePolicy();
      await this.refreshMemoryPolicy(true, true);
      this.initModelLibrary();
      await this.refreshConnectivity();
      this.pickDefaultModel();
      this.pollDownloads();
      this.refreshSessions();
      setInterval(() => this.refreshHealth(), 15000);
      setInterval(() => {
        if (this.tab === "settings" || ["checking","updating","restarting","deferred"].includes(this.autoUpdate.state)) this.refreshAutoUpdate(true);
        if (this.tab === "settings") this.refreshMemoryPolicy(true);
      }, 5000);
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
      if (tab === "settings") { this.refreshSettings(); this.refreshAutoUpdate(true); this.refreshMemoryPolicy(true); this.refreshStoragePolicy(); this.refreshConnectivity(); this.refreshDiagnostics(); }
    },

    async refreshAll() {
      await this.refreshHealth();
      await this.refreshDiagnostics();
      await this.refreshConnectivity();
      await this.refreshChatModels();
    },

    // ════════════ fetchers ════════════
    async refreshHealth() {
      try {
        this.health = await (await fetch(`${this.apiBase}/api/health`)).json();
        // Notice when the server auto-unloaded an idle local model.
        const au = this.health.auto_unload;
        if (au && au.at && au.at !== this._lastAutoUnloadAt) {
          this._lastAutoUnloadAt = au.at;
          if (this._seenAutoUnload) {  // skip the first poll (pre-existing event)
            this.showToast(`⏏ Freed ${this.sessionModelShort(au.repo)} — memory released automatically`);
          }
          this._seenAutoUnload = true;
        } else if (au) {
          this._seenAutoUnload = true;
        }
      } catch (e) { this.health = { ok: false }; }
    },
    async unloadModel() {
      await this.releaseMemory();
    },
    showToast(msg) {
      this.toast = msg;
      clearTimeout(this._toastT);
      this._toastT = setTimeout(() => { this.toast = ""; }, 5000);
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
        this.diag = { ...(await (await fetch(`${this.apiBase}/api/chat/diagnostics`)).json()), checked: true };
        if (this.diag.app_version) this.appVersion = this.diag.app_version;
      }
      catch (e) { this.diag = { checked: true, available: false, error: String(e), packages: [] }; }
    },
    async refreshReleaseNotes() {
      try {
        const r = await fetch(`${this.apiBase}/api/release-notes`, { cache: "no-store" });
        if (!r.ok) throw new Error(`HTTP ${r.status}`);
        const data = await r.json();
        this.releaseNotesCurrent = data.current_version || this.appVersion || "unknown";
        this.releaseNotes = Array.isArray(data.releases) ? data.releases : [];
      } catch (e) {
        this.releaseNotes = [];
      }
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
        const local = await fetch(`${this.apiBase}/api/chat/models`).then(r => r.json());
        this.chatModels = local.models || [];
        const loaded = this.chatModels.find(m => m.loaded);
        if (loaded) this.currentRepo = loaded.repo;
      } catch (e) {}
    },
    groupedModels() {
      return this.chatModels.length
        ? [{ label: '🖥 Local (MLX)', models: this.chatModels, disabled: false }]
        : [];
    },
    async refreshSettings() {
      try { this.settings = await (await fetch(`${this.apiBase}/api/settings`)).json(); } catch (e) {}
    },
    async refreshStoragePolicy() {
      try {
        const r = await fetch(`${this.apiBase}/api/storage-policy`);
        if (!r.ok) return;
        this.storagePolicy = { ...this.storagePolicy, ...(await r.json()), loaded:true, busy:false };
      } catch (e) { /* keep last */ }
    },
    async saveStoragePolicy() {
      this.storagePolicy.busy=true; this.storagePolicy.message="Saving fleet policy…";
      try {
        const r=await fetch(`${this.apiBase}/api/storage-policy`,{method:"PUT",headers:{"content-type":"application/json"},body:JSON.stringify({enabled:!!this.storagePolicy.enabled,retention_days:Number(this.storagePolicy.retention_days),max_gb:Number(this.storagePolicy.max_gb)})});
        const d=await r.json(); if(!r.ok) throw new Error(d.detail||`HTTP ${r.status}`);
        this.storagePolicy={...this.storagePolicy,...d,loaded:true,busy:false,message:"Saved. Chat history and model caches remain protected."};
      } catch(e) { this.storagePolicy.busy=false; this.storagePolicy.message=String(e.message||e); }
    },
    async cleanStoragePolicyNow() {
      this.storagePolicy.busy=true; this.storagePolicy.message="Checking for disposable media…";
      try {
        const r=await fetch(`${this.apiBase}/api/storage-policy/cleanup`,{method:"POST",headers:{"content-type":"application/json"},body:"{}"});
        const d=await r.json(); if(!r.ok) throw new Error(d.detail||`HTTP ${r.status}`);
        this.storagePolicy={...this.storagePolicy,...d,loaded:true,busy:false,message:"Nothing to remove. Chat Studio has no disposable media outputs."};
      } catch(e) { this.storagePolicy.busy=false; this.storagePolicy.message=String(e.message||e); }
    },

    async refreshMemoryPolicy(silent=false, forceDraft=false) {
      try {
        const r=await fetch(`${this.apiBase}/api/memory-policy`,{cache:"no-store"});
        const d=await r.json(); if(!r.ok) throw new Error(d.detail||`HTTP ${r.status}`);
        const saved=d.mode;
        Object.assign(this.memoryPolicy,d,{loaded:true});
        if(forceDraft || !this.memoryPolicy.dirty){this.memoryPolicy.draft={mode:saved};this.memoryPolicy.dirty=false;}
      } catch(e){if(!silent){this.memoryPolicy.message=String(e.message||e);this.memoryPolicy.messageKind="error";}}
    },
    markMemoryPolicyDirty(){this.memoryPolicy.dirty=true;this.memoryPolicy.message="";this.memoryPolicy.messageKind="info";},
    memoryPolicyTime(value){if(!value)return "Not scheduled";const n=Number(value);const d=new Date(n<1e12?n*1000:n);return Number.isNaN(d.getTime())?"Not scheduled":d.toLocaleString();},
    async saveMemoryPolicy(){
      this.memoryPolicy.busy=true;this.memoryPolicy.message="Saving memory mode…";this.memoryPolicy.messageKind="info";
      try{
        const r=await fetch(`${this.apiBase}/api/memory-policy`,{method:"PUT",headers:{"content-type":"application/json"},body:JSON.stringify(this.memoryPolicy.draft)});
        const d=await r.json();if(!r.ok)throw new Error(d.detail||`HTTP ${r.status}`);
        Object.assign(this.memoryPolicy,d,{loaded:true,draft:{mode:d.mode},dirty:false,message:"Memory mode saved.",messageKind:"success"});
      }catch(e){this.memoryPolicy.message=String(e.message||e);this.memoryPolicy.messageKind="error";}
      finally{this.memoryPolicy.busy=false;}
    },
    async releaseMemory(){
      this.memoryPolicy.busy=true;this.memoryPolicy.message="Releasing model memory…";this.memoryPolicy.messageKind="info";
      try{
        const r=await fetch(`${this.apiBase}/api/memory/release`,{method:"POST"});
        const d=await r.json();if(!r.ok)throw new Error(d.detail||`HTTP ${r.status}`);
        const repo=d.last_release_details?.repo;
        Object.assign(this.memoryPolicy,d,{loaded:true,message:repo?`Released ${this.sessionModelShort(repo)} from memory.`:"Allocator caches cleared; no local model was loaded.",messageKind:"success"});
        this.showToast(repo?`⏏ Unloaded ${this.sessionModelShort(repo)} — memory freed`:"Memory caches cleared");
      }catch(e){this.memoryPolicy.message=String(e.message||e);this.memoryPolicy.messageKind="error";this.showToast(this.memoryPolicy.message);}
      finally{this.memoryPolicy.busy=false;await this.refreshHealth();}
    },

    async refreshAutoUpdate(silent=false) {
      try {
        const r = await fetch(`${this.apiBase}/api/auto-update/status`, {cache:"no-store"});
        const data = await r.json();
        if (!r.ok) throw new Error(data.detail || `HTTP ${r.status}`);
        this.applyAutoUpdateStatus(data);
      } catch (e) {
        if (!silent) { this.autoUpdate.message=String(e.message||e); this.autoUpdate.messageKind="error"; }
      }
    },
    applyAutoUpdateStatus(data, forceDraft=false) {
      const savedSettings = data.settings ? {...data.settings} : null;
      Object.assign(this.autoUpdate, data, {loaded:true});
      if (savedSettings && (forceDraft || !this.autoUpdate.dirty)) {
        this.autoUpdate.draft = savedSettings;
        this.autoUpdate.dirty = false;
      }
    },
    markAutoUpdateDirty() {
      this.autoUpdate.dirty = true;
      this.autoUpdate.message = "";
      this.autoUpdate.messageKind = "info";
    },
    autoUpdateTime(value) {
      if (!value) return "Not yet";
      const date=new Date(value); return Number.isNaN(date.getTime()) ? "Not yet" : date.toLocaleString();
    },
    async saveAutoUpdate() {
      this.autoUpdate.busy=true; this.autoUpdate.message="Saving and validating the schedule…"; this.autoUpdate.messageKind="info";
      try {
        const r=await fetch(`${this.apiBase}/api/auto-update/settings`,{method:"POST",headers:{"content-type":"application/json"},body:JSON.stringify(this.autoUpdate.draft)});
        const data=await r.json(); if(!r.ok) throw new Error(data.detail||`HTTP ${r.status}`);
        this.applyAutoUpdateStatus(data, true);
        this.autoUpdate.message=data.settings.mode==="off"?"Saved. Automatic updates are off and the schedule is unloaded.":"Saved. The updater schedule is installed and verified.";
        this.autoUpdate.messageKind="success";
      } catch(e) { this.autoUpdate.message=String(e.message||e); this.autoUpdate.messageKind="error"; }
      finally { this.autoUpdate.busy=false; }
    },
    async autoUpdateAction(action,body={}) {
      this.autoUpdate.busy=true; this.autoUpdate.message=action==="check"?"Checking safely…":"Starting the update helper…"; this.autoUpdate.messageKind="info";
      try {
        const r=await fetch(`${this.apiBase}/api/auto-update/${action}`,{method:"POST",headers:{"content-type":"application/json"},body:JSON.stringify(body)});
        const data=await r.json(); if(!r.ok) throw new Error(data.detail||`HTTP ${r.status}`);
        this.applyAutoUpdateStatus(data);
        this.autoUpdate.message=body.after_current?"Queued. The updater will retry when Chat Studio is idle.":(action==="check"?"Check started. Status refreshes automatically.":"Update started. This page may reconnect during restart.");
        this.autoUpdate.messageKind="success";
      } catch(e) { this.autoUpdate.message=String(e.message||e); this.autoUpdate.messageKind="error"; }
      finally { this.autoUpdate.busy=false; }
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
    localModelCount() { return this.models.length; },
    initModelLibrary() {
      if (!this.openModelFamilies.size) this.openBestModelFamily();
      // Remove preferences from older experiments that could silently hide
      // most of the catalog. The family library always opens unfiltered.
      try {
        for (const key of Object.keys(localStorage)) {
          if (key.startsWith("chatstudio.modelFilter")) localStorage.removeItem(key);
        }
      } catch {}
    },
    openBestModelFamily() {
      const cached = this.models.find(m => m.cache?.state === "cached");
      const starter = this.models.find(m => m.is_starter && this.fitFor(m.min_unified_memory_gb).state !== "risky");
      const first = cached || starter || this.models[0];
      this.openModelFamilies = new Set(first ? [first.family] : []);
    },
    isModelFamilyOpen(id) {
      return this.openModelFamilies.has(id) || !!this.modelSearch.trim();
    },
    toggleModelFamily(id) {
      const next = new Set(this.openModelFamilies);
      if (next.has(id)) next.delete(id); else next.add(id);
      this.openModelFamilies = next;
    },
    isModelExpanded(repo) { return this.expandedModelRepos.has(repo); },
    toggleModelExpanded(repo) {
      const next = new Set(this.expandedModelRepos);
      if (next.has(repo)) next.delete(repo); else next.add(repo);
      this.expandedModelRepos = next;
    },
    familyMonogram(label) {
      return String(label || "AI").split(/\s+/).map(x => x[0]).join("").slice(0, 2).toUpperCase();
    },
    familyCachedCount(familyId) {
      return (this.modelsByFamily[familyId] || []).filter(m => m.cache?.state === "cached").length;
    },
    familyFitCount(familyId) {
      return (this.modelsByFamily[familyId] || []).filter(m => this.fitFor(m.min_unified_memory_gb).state !== "risky").length;
    },
    modelRole(m) {
      if (m.is_coder) return "Code";
      if (m.is_reasoning) return "Reasoning";
      if (m.is_starter) return "Starter";
      return "General";
    },
    clearModelFilters() {
      this.modelSearch = "";
      this.fitFilter = "all";
      this.capFilter = "all";
      this.sortBy = "default";
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
        const family = this.families[m.family] || {};
        const familyText = `${family.label || ""} ${family.summary || ""}`.toLowerCase();
        if (!label.includes(q) && !repo.includes(q) && !familyText.includes(q)) return false;
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

    async searchHub() {
      this.hubLoading = true;
      this.hubError = "";
      try {
        const q = encodeURIComponent(this.hubQuery.trim());
        const r = await fetch(`${this.apiBase}/api/hub/search?q=${q}&limit=40`);
        const d = await r.json();
        if (!r.ok) throw new Error(d.detail || "Hub search failed");
        this.hubResults = d.models || [];
      } catch (e) {
        this.hubResults = [];
        this.hubError = String(e.message || e);
      } finally { this.hubLoading = false; }
    },
    hubJob(repo) {
      return this.jobs.find(j => j.repo === repo && ["queued", "running", "cancelling"].includes(j.state));
    },
    hubIsCached(result) {
      if (result.cache_state === "cached") return true;
      return this.jobs.some(j => j.repo === result.repo && j.state === "done");
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
    newChat() { this.stopGen(); this.messages = []; this.streamingText = ""; this.currentSessionId = null; },

    // ════════════ chat sessions (history) ════════════
    async refreshSessions() {
      try {
        const q = encodeURIComponent(this.sessionSearch || "");
        const d = await (await fetch(`${this.apiBase}/api/sessions?q=${q}`)).json();
        this.sessions = d.sessions || [];
      } catch (e) {}
    },
    pinnedSessions() { return this.sessions.filter(s => s.pinned); },
    recentSessions() { return this.sessions.filter(s => !s.pinned); },
    async openSession(id) {
      try {
        const s = await (await fetch(`${this.apiBase}/api/sessions/${id}`)).json();
        this.messages = (s.messages || []).map(m => ({ role: m.role, content: m.content, meta: m.meta }));
        this.currentSessionId = s.id;
        if (s.model) {
          const local = this.chatModels.find(m => m.repo === s.model);
          if (local) this.selectedRepo = s.model;
        }
        this.scrollThread();
      } catch (e) {}
    },
    async saveCurrentSession() {
      if (!this.messages.length) return;
      try {
        const m = await (await fetch(`${this.apiBase}/api/sessions`, {
          method: "POST", headers: { "content-type": "application/json" },
          body: JSON.stringify({
            id: this.currentSessionId,
            model: this.currentRepo,
            messages: this.messages.map(x => ({ role: x.role, content: x.content, meta: x.meta })),
          }),
        })).json();
        if (m && m.id) this.currentSessionId = m.id;
        await this.refreshSessions();
      } catch (e) {}
    },
    async togglePin(s) {
      await fetch(`${this.apiBase}/api/sessions/${s.id}/pin`, {
        method: "POST", headers: { "content-type": "application/json" },
        body: JSON.stringify({ pinned: !s.pinned }),
      }).catch(() => {});
      await this.refreshSessions();
    },
    async renameSession(s) {
      const t = prompt("Rename chat:", s.title || "");
      if (t === null) return;
      const r = await fetch(`${this.apiBase}/api/sessions/${s.id}/rename`, {
        method: "POST", headers: { "content-type": "application/json" },
        body: JSON.stringify({ title: t }),
      }).catch(() => {});
      if (!r || !r.ok) { this.showToast("Could not rename chat"); return; }
      this.showToast("Chat renamed");
      await this.refreshSessions();
    },
    async deleteSession(s) {
      if (this.sessionDeleteArmed !== s.id) {
        this.sessionDeleteArmed = s.id;
        clearTimeout(this._sessionDeleteTimer);
        this._sessionDeleteTimer = setTimeout(() => {
          if (this.sessionDeleteArmed === s.id) this.sessionDeleteArmed = null;
        }, 4000);
        this.showToast("Click delete again to confirm");
        return;
      }
      clearTimeout(this._sessionDeleteTimer);
      this.sessionDeleteArmed = null;
      const r = await fetch(`${this.apiBase}/api/sessions/${s.id}`, { method: "DELETE" }).catch(() => {});
      if (!r || !r.ok) { this.showToast("Could not delete chat"); return; }
      if (s.id === this.currentSessionId) { this.currentSessionId = null; this.messages = []; }
      this.showToast("Chat deleted");
      await this.refreshSessions();
    },
    sessionModelShort(repo) {
      if (!repo) return "";
      if (repo.startsWith("provider:")) return repo.split(":")[1];
      return repo.split("/").pop();
    },
    relTime(ts) {
      if (!ts) return "";
      const d = Date.now() - ts * 1000, m = 60000, h = 3600000, day = 86400000;
      if (d < m) return "just now";
      if (d < h) return Math.floor(d / m) + "m ago";
      if (d < day) return Math.floor(d / h) + "h ago";
      if (d < 7 * day) return Math.floor(d / day) + "d ago";
      return new Date(ts * 1000).toLocaleDateString();
    },

    // ════════════ chat send / stream ════════════
    /** Is the currently-selected model a vision-language model? Drives the
     *  📎 attach button + image preview. Looks the repo up in the catalog
     *  (this.models); non-catalog models are treated as text-only here. */
    get currentIsVision() {
      if (!this.currentRepo) return false;
      const m = (this.models || []).find(x => x.repo === this.currentRepo);
      return !!(m && m.is_vision);
    },
    onImagePick(event) {
      const files = Array.from(event.target.files || []);
      for (const f of files) {
        if (this.draftImages.length >= 4) {
          this.showToast("Attach at most 4 images per message");
          break;
        }
        if (!f.type.startsWith("image/")) {
          this.showToast(`${f.name} is not an image`);
          continue;
        }
        if (f.size > 10 * 1024 * 1024) {
          this.showToast(`${f.name} is larger than 10 MB`);
          continue;
        }
        const reader = new FileReader();
        reader.onload = () => { this.draftImages.push(reader.result); };
        reader.readAsDataURL(f);   // data:image/...;base64,... — what the backend expects
      }
      event.target.value = "";     // allow re-picking the same file
    },
    removeDraftImage(i) { this.draftImages.splice(i, 1); },
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
      const images = this.draftImages.slice();   // images for this turn only
      if ((!text && !images.length) || !this.currentRepo || this.streaming) return;
      this.messages.push({ role: "user", content: text, images: images.length ? images : undefined });
      this.draft = "";
      this.draftImages = [];
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
            images,   // applied to the current (last user) turn by the backend
          }),
        });
        if (!r.ok || !r.body) {
          const err = await r.json().catch(() => ({}));
          this.messages.push({ role: "assistant", content: "⚠️ " + (err.detail || r.statusText) });
          return;
        }
        const reader = r.body.getReader();
        const decoder = new TextDecoder();
        let raw = "";
        while (true) {
          const { value, done } = await reader.read();
          if (done) break;
          raw += decoder.decode(value, { stream: true });
          this.streamingText = raw;
          this.scrollThread();
        }
        this.finishAssistant(raw, t0, false);
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
        this.saveCurrentSession();   // persist this exchange to history
        this.$nextTick(() => { const el = this.$refs.composer; if (el) el.focus(); });
      }
    },
    finishAssistant(content, t0, stopped) {
      const secs = (performance.now() - t0) / 1000;
      const approxTok = Math.max(1, Math.round((content || "").length / 4));
      const tps = secs > 0 ? (approxTok / secs).toFixed(1) : "—";
      const meta = `~${approxTok} tok · ${secs.toFixed(1)}s · ~${tps} tok/s` + (stopped ? " · stopped" : "");
      if ((content || "").trim()) {
        this.messages.push({ role: "assistant", content, meta });
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
      this.$nextTick(() => {
        const el = this.$refs.thread;
        if (!el) return;
        const nearBottom = el.scrollHeight - el.scrollTop - el.clientHeight < 140;
        if (nearBottom) el.scrollTop = el.scrollHeight;
      });
    },
    shortName(repo) {
      const m = this.chatModels.find(x => x.repo === repo);
      if (m) return m.label.replace(/\s*\(.*\)\s*$/, "");
      return (repo || "").split("/").pop();
    },

    // ════════════ markdown (tiny, XSS-safe: escape first) ════════════
    escapeHtml(s) {
      return (s || "").replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;")
        .replace(/"/g, "&quot;").replace(/'/g, "&#39;");
    },
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
      // Decimal (SI, ÷1000) — NOT binary ÷1024. Must match the catalog's
      // static `size_gb` values and Hugging Face's own byte
      // counts, or live download progress visibly disagrees with the "X GB"
      // size shown before downloading — e.g. a real 4.3 GB (decimal) model
      // would cap out at "~4.0 GB" downloaded if divided by 1024^3 instead
      // (same bytes, ~7% smaller-looking number, no bug in either reading
      // alone — just a units mismatch). Same bug class Voice Studio KH
      // fixed in v1.7.2/v1.7.3.
      if (!b || b <= 0) return "—";
      const units = ["B", "KB", "MB", "GB", "TB"];
      let i = 0;
      let v = b;
      while (v >= 1000 && i < units.length - 1) { v /= 1000; i++; }
      return v.toFixed(i === 0 ? 0 : 1) + " " + units[i];
    },
    formatGb(gb) {
      const n = Number(gb);
      return Number.isFinite(n) ? n.toFixed(2) + " GB" : "—";
    },
    formatNumber(n) {
      return new Intl.NumberFormat(undefined, { notation: "compact", maximumFractionDigits: 1 }).format(Number(n) || 0);
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
