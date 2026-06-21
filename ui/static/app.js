(function () {
  const state = window.__SECOND_BRAIN__ || {};
  const messagesEl = document.getElementById("messages");
  const inputEl = document.getElementById("message-input");
  const sendButton = document.getElementById("send-button");
  const micButton = document.getElementById("mic-button");
  const clearButton = document.getElementById("clear-button");
  const refreshButton = document.getElementById("refresh-state");
  const workspaceInput = document.getElementById("workspace-input");
  const workspaceApply = document.getElementById("workspace-apply");
  const fileTreeToggle = document.getElementById("file-tree-toggle");
  const filesEl = document.getElementById("file-tree");
  const voiceStatus = document.getElementById("voice-status");
  const connectionText = document.getElementById("connection-text");
  const connectionDot = document.getElementById("connection-dot");
  const chatTab = document.getElementById("chat-tab");
  const dhConfigTab = document.getElementById("dh-config-tab");
  const helpTab = document.getElementById("help-tab");
  const chatView = document.getElementById("chat-view");
  const dhConfigPanel = document.getElementById("dh-config-panel");
  const helpPanel = document.getElementById("help-panel");
  const dhConfigPath = document.getElementById("dh-config-path");
  const dhConfigStatus = document.getElementById("dh-config-status");
  const dhConfigReload = document.getElementById("dh-config-reload");
  const dhConfigSave = document.getElementById("dh-config-save");
  const dhTableTabs = document.getElementById("dh-table-tabs");
  const dhRuleBody = document.getElementById("dh-rule-body");
  const dhNewColumn = document.getElementById("dh-new-column");
  const dhAddColumn = document.getElementById("dh-add-column");
  const dhNewLibrary = document.getElementById("dh-new-library");
  const dhAddLibrary = document.getElementById("dh-add-library");
  const dhLibraryList = document.getElementById("dh-library-list");
  const dhLibraryTitle = document.getElementById("dh-library-title");
  const dhLibraryMeta = document.getElementById("dh-library-meta");
  const dhDeleteLibrary = document.getElementById("dh-delete-library");
  const dhNewCode = document.getElementById("dh-new-code");
  const dhNewDesc = document.getElementById("dh-new-desc");
  const dhAddCode = document.getElementById("dh-add-code");
  const dhCodeBody = document.getElementById("dh-code-body");

  const DH_TABLE_TYPES = [
    "COLLAR",
    "SURVEY",
    "LITHOLOGY",
    "ASSAY",
    "MINERALIZATION",
    "OXIDATION",
    "GEOTECH",
    "RQD",
    "VEIN",
    "ALTERATION",
    "DENSITY",
  ];

  let busy = false;
  let voiceRecorder = null;
  let voiceChunks = [];
  let voiceStream = null;
  let isRecording = false;
  let isTranscribing = false;
  let voiceStopTimer = null;
  const voiceMaxMs = 60000;
  let fileTreeCollapsed = true;
  let dhConfig = null;
  let dhActiveTable = "COLLAR";
  let dhActiveLibraryId = "";
  let dhDirty = false;

  function setConnection(text, ok = true) {
    connectionText.textContent = text;
    connectionDot.style.background = ok ? "var(--accent)" : "var(--danger)";
  }

  function autosize() {
    inputEl.style.height = "auto";
    inputEl.style.height = Math.min(inputEl.scrollHeight, 180) + "px";
  }

  function scrollToBottom() {
    messagesEl.scrollTop = messagesEl.scrollHeight;
  }

  function addMessage(role, content, cls = "") {
    const bubble = document.createElement("div");
    bubble.className = `message ${role}${cls ? " " + cls : ""}`;
    bubble.textContent = content;
    messagesEl.appendChild(bubble);
    scrollToBottom();
    return bubble;
  }

  function el(tag, className = "", text = "") {
    const node = document.createElement(tag);
    if (className) node.className = className;
    if (text) node.textContent = text;
    return node;
  }

  function clone(value) {
    return JSON.parse(JSON.stringify(value));
  }

  function normalizeColumnName(value) {
    return value.trim().toUpperCase().replace(/[\s().]+/g, "_").replace(/_+$/g, "");
  }

  function setDhStatus(text, kind = "idle") {
    dhConfigStatus.textContent = text;
    dhConfigStatus.dataset.kind = kind;
  }

  function markDhDirty() {
    dhDirty = true;
    setDhStatus("Unsaved changes", "dirty");
  }

  function setView(view) {
    const chatActive = view === "chat";
    const configActive = view === "dh-config";
    const helpActive = view === "help";
    chatView.hidden = !chatActive;
    dhConfigPanel.hidden = !configActive;
    helpPanel.hidden = !helpActive;
    chatTab.classList.toggle("active", chatActive);
    dhConfigTab.classList.toggle("active", configActive);
    helpTab.classList.toggle("active", helpActive);
    chatTab.setAttribute("aria-selected", String(chatActive));
    dhConfigTab.setAttribute("aria-selected", String(configActive));
    helpTab.setAttribute("aria-selected", String(helpActive));
    if (configActive && !dhConfig) {
      loadDhConfig();
    }
  }

  function renderHistory(history) {
    messagesEl.innerHTML = "";
    if (!history || !history.length) {
      return;
    }
    history.forEach((entry) => addMessage(entry.role === "user" ? "user" : "assistant", entry.content));
  }

  function normalizeEntries(nextState) {
    if (Array.isArray(nextState.workspace_entries)) {
      return nextState.workspace_entries;
    }
    const files = nextState.workspace_files || nextState.recent_files || [];
    return files.map((path) => ({
      path,
      name: path.split("/").filter(Boolean).pop() || path,
      type: "file",
    }));
  }

  function buildFileTree(entries) {
    const root = { dirs: new Map(), files: [] };
    entries.forEach((entry) => {
      const path = entry.path || "";
      const parts = path.split("/").filter(Boolean);
      if (!parts.length) return;
      let node = root;
      parts.forEach((part, index) => {
        const isLast = index === parts.length - 1;
        const isFile = isLast && entry.type !== "directory";
        if (isFile) {
          node.files.push({ name: part, path });
          return;
        }
        if (!node.dirs.has(part)) {
          node.dirs.set(part, { dirs: new Map(), files: [] });
        }
        node = node.dirs.get(part);
      });
    });
    return root;
  }

  function createFileButton(file, depth) {
    const button = document.createElement("button");
    button.type = "button";
    button.className = "file-node file-leaf";
    button.textContent = file.name;
    button.dataset.path = file.path;
    button.style.setProperty("--depth", depth);
    button.title = file.path;
    button.addEventListener("click", () => {
      inputEl.value = `/read ${file.path}`;
      autosize();
      inputEl.focus();
    });
    return button;
  }

  function renderTreeNode(node, container, depth = 0) {
    Array.from(node.dirs.entries())
      .sort(([left], [right]) => left.localeCompare(right))
      .forEach(([name, child]) => {
        const folder = document.createElement("details");
        folder.className = "tree-folder";

        const summary = document.createElement("summary");
        summary.className = "file-node folder-node";
        summary.style.setProperty("--depth", depth);
        summary.textContent = name;
        folder.appendChild(summary);

        renderTreeNode(child, folder, depth + 1);
        container.appendChild(folder);
      });

    node.files
      .sort((left, right) => left.name.localeCompare(right.name))
      .forEach((file) => container.appendChild(createFileButton(file, depth)));
  }

  function setFileTreeCollapsed(collapsed) {
    fileTreeCollapsed = collapsed;
    filesEl.hidden = collapsed;
    fileTreeToggle.setAttribute("aria-expanded", String(!collapsed));
    fileTreeToggle.classList.toggle("collapsed", collapsed);
  }

  function renderState(nextState) {
    const entries = normalizeEntries(nextState);
    filesEl.innerHTML = "";
    if (!entries.length) {
      const empty = document.createElement("div");
      empty.className = "small-copy";
      empty.textContent = "No files.";
      filesEl.appendChild(empty);
      setFileTreeCollapsed(fileTreeCollapsed);
      return;
    }
    renderTreeNode(buildFileTree(entries), filesEl);
    setFileTreeCollapsed(fileTreeCollapsed);
  }

  async function refreshState() {
    const response = await fetch("/api/state");
    const data = await response.json();
    state.workspace = data.workspace;
    state.model = data.model;
    state.base_url = data.base_url;
    state.llm_provider = data.llm_provider;
    workspaceInput.value = data.workspace;
    renderState(data);
    if (!dhConfigPanel.hidden) await loadDhConfig();
    setConnection(`Ready • ${data.llm_provider || "local"} • ${data.model}`, true);
  }

  async function loadHistory() {
    const response = await fetch("/api/history");
    const data = await response.json();
    renderHistory(data.history || []);
  }

  async function applyWorkspace() {
    const workspace = workspaceInput.value.trim();
    if (!workspace || busy) return;

    busy = true;
    workspaceApply.disabled = true;
    refreshButton.disabled = true;
    setConnection("Switching workspace...", true);

    try {
      const response = await fetch("/api/workspace", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ workspace }),
      });
      const data = await response.json();
      if (!response.ok || data.error) {
        throw new Error(data.error || "Workspace switch failed");
      }
      workspaceInput.value = data.state.workspace;
      state.workspace = data.state.workspace;
      state.model = data.state.model;
      state.base_url = data.state.base_url;
      state.llm_provider = data.state.llm_provider;
      renderState(data.state);
      await loadHistory();
      if (!dhConfigPanel.hidden) await loadDhConfig();
      setConnection(`Ready • ${data.state.llm_provider || "local"} • ${data.state.model}`, true);
    } catch (error) {
      addMessage("assistant", String(error.message || error), "error");
      setConnection("Workspace error", false);
    } finally {
      busy = false;
      workspaceApply.disabled = false;
      refreshButton.disabled = false;
      inputEl.focus();
    }
  }

  async function loadDhConfig() {
    setDhStatus("Loading...", "idle");
    const response = await fetch("/api/dh/config");
    const data = await response.json();
    if (!response.ok || data.error) {
      setDhStatus(data.error || "Load failed", "error");
      throw new Error(data.error || "Load failed");
    }
    dhConfig = clone(data.config);
    dhConfigPath.textContent = data.path;
    dhDirty = false;
    setDhStatus("Saved", "saved");
    ensureDhSelection();
    renderDhConfig();
  }

  async function saveDhConfig() {
    if (!dhConfig) return;
    setDhStatus("Saving...", "idle");
    const response = await fetch("/api/dh/config", {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ config: dhConfig }),
    });
    const data = await response.json();
    if (!response.ok || data.error) {
      setDhStatus(data.error || "Save failed", "error");
      throw new Error(data.error || "Save failed");
    }
    dhConfig = clone(data.config);
    dhDirty = false;
    setDhStatus("Saved", "saved");
    ensureDhSelection();
    renderDhConfig();
  }

  function ensureDhSelection() {
    if (!dhConfig) return;
    if (!Array.isArray(dhConfig.configs)) dhConfig.configs = [];
    if (!Array.isArray(dhConfig.libraries)) dhConfig.libraries = [];
    if (!dhConfig.configs.some((config) => config.tableType === dhActiveTable)) {
      dhActiveTable = dhConfig.configs[0]?.tableType || "COLLAR";
    }
    if (!dhConfig.libraries.some((library) => library.id === dhActiveLibraryId)) {
      dhActiveLibraryId = dhConfig.libraries[0]?.id || "";
    }
  }

  function currentDhConfig() {
    return dhConfig?.configs?.find((config) => config.tableType === dhActiveTable) || null;
  }

  function currentDhLibrary() {
    return dhConfig?.libraries?.find((library) => library.id === dhActiveLibraryId) || null;
  }

  function renderDhConfig() {
    if (!dhConfig) return;
    ensureDhSelection();
    renderDhTableTabs();
    renderDhRules();
    renderDhLibraries();
    renderDhCodes();
  }

  function renderDhTableTabs() {
    dhTableTabs.innerHTML = "";
    DH_TABLE_TYPES.forEach((table) => {
      const button = el("button", "table-tab", table);
      button.type = "button";
      button.classList.toggle("active", table === dhActiveTable);
      button.addEventListener("click", () => {
        if (!dhConfig.configs.some((config) => config.tableType === table)) {
          dhConfig.configs.push({ tableType: table, columns: [] });
          markDhDirty();
        }
        dhActiveTable = table;
        renderDhConfig();
      });
      dhTableTabs.appendChild(button);
    });
  }

  function renderDhRules() {
    dhRuleBody.innerHTML = "";
    const config = currentDhConfig();
    if (!config) return;
    config.columns.forEach((column, index) => {
      const row = document.createElement("tr");
      row.dataset.index = String(index);
      row.appendChild(textCell(column.columnName || ""));
      row.appendChild(checkboxCell(column.isSchemaRequired, "schema"));
      row.appendChild(checkboxCell(column.isMandatory, "mandatory"));
      row.appendChild(selectCell(column.type || "string", "type", [["string", "String"], ["float", "Number"], ["number", "Number"]]));
      row.appendChild(selectCell(validationMode(column), "mode", [["none", "No validation"], ["range", "Numeric range"], ["lookup", "Lookup library"], ["key", "Key reference"]]));
      row.appendChild(ruleConfigCell(column, index));
      const action = document.createElement("td");
      const remove = el("button", "table-action danger", "Delete");
      remove.type = "button";
      remove.dataset.action = "delete-column";
      action.appendChild(remove);
      row.appendChild(action);
      dhRuleBody.appendChild(row);
    });
    if (!config.columns.length) {
      const row = document.createElement("tr");
      const empty = el("td", "empty-cell", "No column rules configured for this table.");
      empty.colSpan = 7;
      row.appendChild(empty);
      dhRuleBody.appendChild(row);
    }
  }

  function textCell(text) {
    const cell = document.createElement("td");
    const code = el("span", "mono-chip", text);
    cell.appendChild(code);
    return cell;
  }

  function checkboxCell(checked, field) {
    const cell = document.createElement("td");
    const input = document.createElement("input");
    input.type = "checkbox";
    input.checked = Boolean(checked);
    input.dataset.field = field;
    cell.appendChild(input);
    return cell;
  }

  function selectCell(value, field, options) {
    const cell = document.createElement("td");
    const select = document.createElement("select");
    select.dataset.field = field;
    options.forEach(([optionValue, label]) => {
      const option = document.createElement("option");
      option.value = optionValue;
      option.textContent = label;
      option.selected = optionValue === value;
      select.appendChild(option);
    });
    cell.appendChild(select);
    return cell;
  }

  function validationMode(column) {
    if (column.validation?.range) return "range";
    if (column.validation?.lookup) return "lookup";
    if (column.validation?.isKeyReference) return "key";
    return "none";
  }

  function ruleConfigCell(column, index) {
    const cell = document.createElement("td");
    const mode = validationMode(column);
    if (mode === "range") {
      const wrap = el("div", "range-editor");
      wrap.appendChild(numberInput("min", column.validation.range.min, index));
      wrap.appendChild(numberInput("max", column.validation.range.max, index));
      const label = el("label", "check-label", "Strict");
      const strict = document.createElement("input");
      strict.type = "checkbox";
      strict.checked = Boolean(column.validation.range.strict);
      strict.dataset.field = "range-strict";
      label.prepend(strict);
      wrap.appendChild(label);
      cell.appendChild(wrap);
      return cell;
    }
    if (mode === "lookup") {
      const wrap = el("div", "lookup-editor");
      const select = document.createElement("select");
      select.dataset.field = "lookup-library";
      if (!dhConfig.libraries.length) {
        const option = document.createElement("option");
        option.value = "";
        option.textContent = "No libraries";
        select.appendChild(option);
      }
      dhConfig.libraries.forEach((library) => {
        const option = document.createElement("option");
        option.value = library.id;
        option.textContent = library.name || library.id;
        option.selected = library.id === column.validation.lookup.libraryId;
        select.appendChild(option);
      });
      wrap.appendChild(select);
      const label = el("label", "check-label", "Case sensitive");
      const caseBox = document.createElement("input");
      caseBox.type = "checkbox";
      caseBox.checked = Boolean(column.validation.lookup.caseSensitive);
      caseBox.dataset.field = "lookup-case";
      label.prepend(caseBox);
      wrap.appendChild(label);
      cell.appendChild(wrap);
      return cell;
    }
    if (mode === "key") {
      cell.appendChild(el("span", "rule-note", "Validates existence in Collar"));
      return cell;
    }
    cell.appendChild(el("span", "rule-note", "No additional rules"));
    return cell;
  }

  function numberInput(field, value) {
    const input = document.createElement("input");
    input.type = "number";
    input.placeholder = field.toUpperCase();
    input.value = value ?? "";
    input.dataset.field = `range-${field}`;
    return input;
  }

  function renderDhLibraries() {
    dhLibraryList.innerHTML = "";
    if (!dhConfig.libraries.length) {
      dhLibraryList.appendChild(el("div", "empty-list", "No libraries."));
      return;
    }
    dhConfig.libraries.forEach((library) => {
      const button = el("button", "library-item", library.name || library.id);
      button.type = "button";
      button.classList.toggle("active", library.id === dhActiveLibraryId);
      button.addEventListener("click", () => {
        dhActiveLibraryId = library.id;
        renderDhLibraries();
        renderDhCodes();
      });
      dhLibraryList.appendChild(button);
    });
  }

  function renderDhCodes() {
    const library = currentDhLibrary();
    dhCodeBody.innerHTML = "";
    dhDeleteLibrary.disabled = !library;
    dhAddCode.disabled = !library;
    dhLibraryTitle.textContent = library ? library.name || library.id : "Select a library";
    dhLibraryMeta.textContent = library ? `${library.items?.length || 0} codes` : "No library selected.";
    if (!library) return;
    if (!Array.isArray(library.items)) library.items = [];
    library.items.forEach((item, index) => {
      const row = document.createElement("tr");
      row.dataset.index = String(index);
      row.appendChild(editableCell(item.code || "", "code"));
      row.appendChild(editableCell(item.description || "", "description"));
      const action = document.createElement("td");
      const remove = el("button", "table-action danger", "Delete");
      remove.type = "button";
      remove.dataset.action = "delete-code";
      action.appendChild(remove);
      row.appendChild(action);
      dhCodeBody.appendChild(row);
    });
    if (!library.items.length) {
      const row = document.createElement("tr");
      const empty = el("td", "empty-cell", "No codes defined yet.");
      empty.colSpan = 3;
      row.appendChild(empty);
      dhCodeBody.appendChild(row);
    }
  }

  function editableCell(value, field) {
    const cell = document.createElement("td");
    const input = document.createElement("input");
    input.type = "text";
    input.value = value;
    input.dataset.field = field;
    cell.appendChild(input);
    return cell;
  }

  function updateColumn(index, changes) {
    const config = currentDhConfig();
    if (!config) return;
    config.columns[index] = { ...config.columns[index], ...changes };
    markDhDirty();
    renderDhRules();
  }

  function updateColumnValidation(index, mode) {
    const config = currentDhConfig();
    const column = config?.columns[index];
    if (!column) return;
    if (mode === "range") {
      column.type = "float";
      column.validation = { range: { min: 0, strict: false } };
    } else if (mode === "lookup") {
      column.type = "string";
      column.validation = { lookup: { libraryId: dhConfig.libraries[0]?.id || "", caseSensitive: false } };
    } else if (mode === "key") {
      column.type = "string";
      column.validation = { isKeyReference: true };
    } else {
      column.validation = {};
    }
    markDhDirty();
    renderDhRules();
  }

  async function sendMessage() {
    const message = inputEl.value.trim();
    if (!message || busy) return;

    busy = true;
    sendButton.disabled = true;
    micButton.disabled = true;
    addMessage("user", message);
    inputEl.value = "";
    autosize();
    setConnection("Thinking...", true);

    try {
      const response = await fetch("/api/chat", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ message }),
      });
      const data = await response.json();
      if (!response.ok || data.error) {
        throw new Error(data.error || "Request failed");
      }
      const reply = data.reply || "";
      addMessage("assistant", reply);
      await refreshState();
      if (data.kind === "workspace-switch") {
        await loadHistory();
      }
      setConnection("Ready", true);
    } catch (error) {
      addMessage("assistant", String(error.message || error), "error");
      setConnection("Error", false);
    } finally {
      busy = false;
      sendButton.disabled = false;
      updateVoiceButtonState();
      inputEl.focus();
    }
  }

  function setVoiceStatus(message) {
    voiceStatus.textContent = message || "Idle";
  }

  function voiceSupported() {
    return Boolean(navigator.mediaDevices?.getUserMedia && window.MediaRecorder);
  }

  function updateVoiceButtonState() {
    micButton.disabled = busy || isTranscribing || !voiceSupported();
    micButton.classList.toggle("is-recording", isRecording);
    micButton.classList.toggle("active", isRecording);
    micButton.title = isRecording ? "Stop voice recording" : "Use local voice dictation";
  }

  function cleanupVoiceRecording() {
    if (voiceStream) {
      voiceStream.getTracks().forEach((track) => track.stop());
    }
    voiceRecorder = null;
    voiceStream = null;
    voiceChunks = [];
    if (voiceStopTimer) {
      clearTimeout(voiceStopTimer);
      voiceStopTimer = null;
    }
  }

  function insertDictationText(text) {
    const clean = String(text || "").trim();
    if (!clean) return;
    const current = inputEl.value.trim();
    inputEl.value = current ? `${current} ${clean}` : clean;
    inputEl.dispatchEvent(new Event("input", { bubbles: true }));
    inputEl.focus();
  }

  async function startVoiceDictation() {
    if (busy || isTranscribing) return;
    if (!voiceSupported()) {
      micButton.disabled = true;
      setVoiceStatus("Unavailable");
      return;
    }

    try {
      voiceStream = await navigator.mediaDevices.getUserMedia({ audio: true });
      voiceChunks = [];
      voiceRecorder = new MediaRecorder(voiceStream);
      voiceRecorder.ondataavailable = (event) => {
        if (event.data && event.data.size > 0) {
          voiceChunks.push(event.data);
        }
      };
      voiceRecorder.onstop = handleVoiceRecordingStop;
      voiceRecorder.start();
      isRecording = true;
      setVoiceStatus("Recording...");
      setConnection("Recording...", true);
      updateVoiceButtonState();
      voiceStopTimer = setTimeout(() => {
        if (isRecording) stopVoiceDictation();
      }, voiceMaxMs);
    } catch (error) {
      console.error(error);
      setVoiceStatus("Error");
      setConnection("Microphone error", false);
      cleanupVoiceRecording();
      updateVoiceButtonState();
    }
  }

  function stopVoiceDictation() {
    if (!voiceRecorder || voiceRecorder.state === "inactive") return;
    if (voiceStopTimer) {
      clearTimeout(voiceStopTimer);
      voiceStopTimer = null;
    }
    isRecording = false;
    setVoiceStatus("Transcribing locally...");
    setConnection("Transcribing locally...", true);
    updateVoiceButtonState();
    voiceRecorder.stop();
  }

  async function handleVoiceRecordingStop() {
    isTranscribing = true;
    updateVoiceButtonState();

    try {
      const mimeType = voiceRecorder?.mimeType || "audio/webm";
      const blob = new Blob(voiceChunks, { type: mimeType });
      if (!blob.size) {
        setVoiceStatus("No audio");
        return;
      }
      const formData = new FormData();
      formData.append("audio", blob, "dictation.webm");

      const response = await fetch("/api/voice/transcribe", {
        method: "POST",
        body: formData,
      });
      const data = await response.json();
      if (!response.ok || data.error) {
        throw new Error(data.error || "Voice transcription failed");
      }
      if (data.text) {
        insertDictationText(data.text);
        setVoiceStatus("Done");
        setConnection("Voice inserted", true);
      } else {
        setVoiceStatus("No speech detected");
        setConnection("Ready", true);
      }
    } catch (error) {
      console.error(error);
      setVoiceStatus("Error");
      setConnection("Voice error", false);
    } finally {
      isTranscribing = false;
      cleanupVoiceRecording();
      updateVoiceButtonState();
    }
  }

  sendButton.addEventListener("click", sendMessage);
  inputEl.addEventListener("input", autosize);
  inputEl.addEventListener("keydown", (event) => {
    if (event.key === "Enter" && !event.shiftKey) {
      event.preventDefault();
      sendMessage();
    }
  });

  micButton.addEventListener("click", () => {
    if (isRecording) {
      stopVoiceDictation();
    } else {
      startVoiceDictation();
    }
  });

  clearButton.addEventListener("click", async () => {
    await fetch("/api/history", { method: "DELETE" });
    await loadHistory();
    setConnection("History cleared", true);
  });

  refreshButton.addEventListener("click", refreshState);
  fileTreeToggle.addEventListener("click", () => setFileTreeCollapsed(!fileTreeCollapsed));
  workspaceApply.addEventListener("click", applyWorkspace);
  workspaceInput.addEventListener("keydown", (event) => {
    if (event.key === "Enter") {
      event.preventDefault();
      applyWorkspace();
    }
  });

  chatTab.addEventListener("click", () => setView("chat"));
  dhConfigTab.addEventListener("click", () => setView("dh-config"));
  helpTab.addEventListener("click", () => setView("help"));

  dhConfigReload.addEventListener("click", async () => {
    try {
      await loadDhConfig();
    } catch (error) {
      addMessage("assistant", String(error.message || error), "error");
    }
  });

  dhConfigSave.addEventListener("click", async () => {
    try {
      await saveDhConfig();
    } catch (error) {
      addMessage("assistant", String(error.message || error), "error");
    }
  });

  dhRuleBody.addEventListener("change", (event) => {
    const target = event.target;
    const row = target.closest("tr");
    const config = currentDhConfig();
    if (!row || !config) return;
    const index = Number(row.dataset.index);
    const column = config.columns[index];
    if (!column) return;
    const field = target.dataset.field;
    if (field === "schema") updateColumn(index, { isSchemaRequired: target.checked });
    if (field === "mandatory") updateColumn(index, { isMandatory: target.checked });
    if (field === "type") updateColumn(index, { type: target.value });
    if (field === "mode") updateColumnValidation(index, target.value);
    if (field === "range-min" || field === "range-max") {
      const key = field === "range-min" ? "min" : "max";
      column.validation = column.validation || { range: {} };
      column.validation.range = column.validation.range || {};
      if (target.value === "") {
        delete column.validation.range[key];
      } else {
        column.validation.range[key] = Number(target.value);
      }
      markDhDirty();
    }
    if (field === "range-strict") {
      column.validation.range.strict = target.checked;
      markDhDirty();
    }
    if (field === "lookup-library") {
      column.validation.lookup.libraryId = target.value;
      markDhDirty();
    }
    if (field === "lookup-case") {
      column.validation.lookup.caseSensitive = target.checked;
      markDhDirty();
    }
  });

  dhRuleBody.addEventListener("click", (event) => {
    const button = event.target.closest("button[data-action='delete-column']");
    if (!button) return;
    const row = button.closest("tr");
    const config = currentDhConfig();
    if (!row || !config) return;
    config.columns.splice(Number(row.dataset.index), 1);
    markDhDirty();
    renderDhRules();
  });

  function addDhColumn() {
    const config = currentDhConfig();
    const name = normalizeColumnName(dhNewColumn.value);
    if (!config || !name) return;
    if (config.columns.some((column) => column.columnName === name)) {
      setDhStatus(`Column ${name} already exists`, "error");
      return;
    }
    config.columns.push({
      columnName: name,
      label: name,
      isSchemaRequired: false,
      isMandatory: false,
      type: "string",
      validation: {},
    });
    dhNewColumn.value = "";
    markDhDirty();
    renderDhRules();
  }

  dhAddColumn.addEventListener("click", addDhColumn);
  dhNewColumn.addEventListener("keydown", (event) => {
    if (event.key === "Enter") {
      event.preventDefault();
      addDhColumn();
    }
  });

  function addDhLibrary() {
    if (!dhConfig) return;
    const name = dhNewLibrary.value.trim();
    if (!name) return;
    const baseId = name.toLowerCase().replace(/[^a-z0-9]+/g, "_").replace(/^_+|_+$/g, "") || "library";
    let id = baseId;
    let counter = 2;
    while (dhConfig.libraries.some((library) => library.id === id)) {
      id = `${baseId}_${counter}`;
      counter += 1;
    }
    dhConfig.libraries.push({ id, name, items: [] });
    dhActiveLibraryId = id;
    dhNewLibrary.value = "";
    markDhDirty();
    renderDhConfig();
  }

  dhAddLibrary.addEventListener("click", addDhLibrary);
  dhNewLibrary.addEventListener("keydown", (event) => {
    if (event.key === "Enter") {
      event.preventDefault();
      addDhLibrary();
    }
  });

  dhDeleteLibrary.addEventListener("click", () => {
    if (!dhConfig || !dhActiveLibraryId) return;
    dhConfig.libraries = dhConfig.libraries.filter((library) => library.id !== dhActiveLibraryId);
    dhActiveLibraryId = dhConfig.libraries[0]?.id || "";
    markDhDirty();
    renderDhConfig();
  });

  function addDhCode() {
    const library = currentDhLibrary();
    if (!library) return;
    const code = dhNewCode.value.trim();
    const description = dhNewDesc.value.trim();
    if (!code) return;
    library.items = library.items || [];
    if (library.items.some((item) => String(item.code).toLowerCase() === code.toLowerCase())) {
      setDhStatus(`Code ${code} already exists`, "error");
      return;
    }
    library.items.push({ code, description });
    dhNewCode.value = "";
    dhNewDesc.value = "";
    markDhDirty();
    renderDhCodes();
  }

  dhAddCode.addEventListener("click", addDhCode);
  [dhNewCode, dhNewDesc].forEach((input) => {
    input.addEventListener("keydown", (event) => {
      if (event.key === "Enter") {
        event.preventDefault();
        addDhCode();
      }
    });
  });

  dhCodeBody.addEventListener("input", (event) => {
    const target = event.target;
    const row = target.closest("tr");
    const library = currentDhLibrary();
    if (!row || !library) return;
    const item = library.items[Number(row.dataset.index)];
    if (!item) return;
    item[target.dataset.field] = target.value;
    markDhDirty();
  });

  dhCodeBody.addEventListener("click", (event) => {
    const button = event.target.closest("button[data-action='delete-code']");
    if (!button) return;
    const row = button.closest("tr");
    const library = currentDhLibrary();
    if (!row || !library) return;
    library.items.splice(Number(row.dataset.index), 1);
    markDhDirty();
    renderDhCodes();
  });

  document.querySelectorAll("[data-fill]").forEach((button) => {
    button.addEventListener("click", () => {
      const value = button.getAttribute("data-fill") || "";
      inputEl.value = value;
      autosize();
      inputEl.focus();
    });
  });

  if (!voiceSupported()) {
    setVoiceStatus("Unavailable");
  }
  updateVoiceButtonState();
  renderState(state);
  loadHistory();
  autosize();
  setConnection(`Ready • ${state.llm_provider || "local"} • ${state.model || "gemma4:e2b"}`, true);
})();
