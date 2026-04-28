(function () {
  const state = {
    templates: [],
    nodeTypes: [],
    edgeTypes: [],
    aiProviders: null,
    sourceSelection: null,
    targetSelection: null,
    sourceTimer: null,
    targetTimer: null,
  };

  function byId(id) {
    return document.getElementById(id);
  }

  function currentProject() {
    return window.IV_CURRENT_USER?.project || localStorage.getItem("iv_project") || null;
  }

  function setStatus(message, isError) {
    const el = byId("gs-status");
    if (!el) return;
    el.textContent = message || "";
    el.style.color = isError ? "#b00020" : "#666";
  }

  async function getJson(url, options) {
    const response = await fetch(url, options);
    const data = await response.json();
    if (!response.ok || data.success === false) {
      throw new Error(data.error || `Request failed: ${response.status}`);
    }
    return data;
  }

  function setSelectOptions(selectEl, items, placeholder) {
    if (!selectEl) return;
    selectEl.innerHTML = "";
    if (placeholder) {
      const option = document.createElement("option");
      option.value = "";
      option.textContent = placeholder;
      selectEl.appendChild(option);
    }
    items.forEach((item) => {
      const option = document.createElement("option");
      option.value = item.value;
      option.textContent = item.label;
      selectEl.appendChild(option);
    });
  }

  function renderTemplateOptions() {
    const selectEl = byId("gs-template");
    setSelectOptions(
      selectEl,
      state.templates.map((template) => ({ value: template.id, label: template.label })),
      "Choose a template"
    );
  }

  function guidedSearchMode() {
    return byId("gs-mode")?.value || "template";
  }

  function renderNodeTypeOptions() {
    const items = state.nodeTypes.map((type) => ({ value: type.name, label: type.name }));
    setSelectOptions(byId("gs-source-type"), items, "Choose source type");
    setSelectOptions(byId("gs-target-type"), items, "Choose target type");

    const sourceSelect = byId("gs-source-type");
    const targetSelect = byId("gs-target-type");
    if (items.length && sourceSelect && !sourceSelect.value) {
      sourceSelect.selectedIndex = 1;
    }
    if (items.length && targetSelect && !targetSelect.value) {
      targetSelect.selectedIndex = 1;
    }
  }

  function renderEdgeTypes() {
    const container = byId("gs-edge-types");
    if (!container) return;
    container.innerHTML = "";

    if (!state.edgeTypes.length) {
      container.innerHTML = '<div style="font-size:12px; color:#666;">No edge types available.</div>';
      return;
    }

    state.edgeTypes.forEach((edgeType) => {
      const label = document.createElement("label");
      label.style.display = "flex";
      label.style.alignItems = "center";
      label.style.gap = "6px";

      const checkbox = document.createElement("input");
      checkbox.type = "checkbox";
      checkbox.value = edgeType;
      checkbox.className = "gs-edge-type-checkbox";

      const text = document.createElement("span");
      text.textContent = edgeType;

      label.appendChild(checkbox);
      label.appendChild(text);
      container.appendChild(label);
    });
  }

  function allowedSourceTypesForTemplate(template) {
    if (!template) return null;

    const restrictedTemplates = new Set([
      "apex_app_writes_to_db_object",
      "apex_app_region_writes_to_db_object",
      "apex_source_db_access_to_db_object",
    ]);

    if (restrictedTemplates.has(template.id)) {
      return ["APEXApp", "APEXPage"];
    }

    return null;
  }  

  function selectedTemplate() {
    const templateId = byId("gs-template")?.value || "";
    return state.templates.find((template) => template.id === templateId) || null;
  }

/*
  function updateTemplateUI() {
    const template = selectedTemplate();
    const description = byId("gs-template-description");
    const targetBlock = byId("gs-target-block");
    const targetNameWrap = byId("gs-target-name-wrap");

    if (description) {
      description.textContent = template?.description || "";
    }

    const showTargetBlock = Boolean(template && (template.needs_target_node || template.needs_target_type));
    if (targetBlock) {
      targetBlock.style.display = showTargetBlock ? "grid" : "none";
    }
    if (targetNameWrap) {
      targetNameWrap.style.display = template?.needs_target_node ? "grid" : "none";
    }

    if (!showTargetBlock) {
      clearSelection("target");
      const targetName = byId("gs-target-name");
      if (targetName) targetName.value = "";
    }
  }
*/

  function updateTemplateUI() {
    const template = selectedTemplate();
    const description = byId("gs-template-description");
    const targetBlock = byId("gs-target-block");
    const targetNameWrap = byId("gs-target-name-wrap");
    const edgeFilterSection = byId("gs-edge-filter-section");
    const sourceTypeSelect = byId("gs-source-type");

    if (description) {
      description.textContent = template?.description || "";
    }

    const showTargetBlock = Boolean(template && (template.needs_target_node || template.needs_target_type));
    if (targetBlock) {
      targetBlock.style.display = showTargetBlock ? "grid" : "none";
    }
    if (targetNameWrap) {
      targetNameWrap.style.display = template?.needs_target_node ? "grid" : "none";
    }

    if (!showTargetBlock) {
      clearSelection("target");
      const targetName = byId("gs-target-name");
      if (targetName) targetName.value = "";
    }

    // show / hide edge filter section
    if (edgeFilterSection) {
      edgeFilterSection.style.display = template?.supports_edge_filter === false ? "none" : "grid";
    }

    // restrict source node type for selected templates
    if (sourceTypeSelect) {
      const allowed = allowedSourceTypesForTemplate(template);

      Array.from(sourceTypeSelect.options).forEach((opt) => {
        if (!opt.value) {
          opt.hidden = false;
          opt.disabled = false;
          return;
        }

        const isAllowed = !allowed || allowed.includes(opt.value);
        opt.hidden = !isAllowed;
        opt.disabled = !isAllowed;
      });

      if (
        allowed &&
        sourceTypeSelect.value &&
        !allowed.includes(sourceTypeSelect.value)
      ) {
        sourceTypeSelect.value = allowed[0];
        const input = byId("gs-source-name");
        if (input) input.value = "";
        clearSelection("source");
        hideSuggestions("source");
        fetchNodeSuggestions("source");
      }
    }
  }

  function syncGuidedAiModelOptions() {
    const providerSelect = byId("gs-ai-provider");
    const modelSelect = byId("gs-ai-model");
    if (!providerSelect || !modelSelect || !state.aiProviders) return;

    const providerId = providerSelect.value;
    const entry = state.aiProviders.find((provider) => provider.id === providerId) || state.aiProviders[0];
    const models = Array.isArray(entry?.models) ? entry.models : [];

    setSelectOptions(
      modelSelect,
      models.map((model) => ({ value: model, label: model })),
      models.length ? null : "No models available"
    );

    if (models.length) {
      modelSelect.value = models.includes(modelSelect.value) ? modelSelect.value : models[0];
    }
  }

  async function loadGuidedAiProviders() {
    if (state.aiProviders) return state.aiProviders;

    const providerSelect = byId("gs-ai-provider");
    const modelSelect = byId("gs-ai-model");
    if (providerSelect) setSelectOptions(providerSelect, [], "Loading providers...");
    if (modelSelect) setSelectOptions(modelSelect, [], "Loading models...");

    const data = await getJson("/api/ai/providers");
    state.aiProviders = Array.isArray(data.providers) ? data.providers : [];

    if (providerSelect) {
      setSelectOptions(
        providerSelect,
        state.aiProviders.map((provider) => ({ value: provider.id, label: provider.label || provider.id })),
        state.aiProviders.length ? null : "No providers available"
      );
      providerSelect.value = state.aiProviders[0]?.id || "";
      providerSelect.onchange = syncGuidedAiModelOptions;
    }

    syncGuidedAiModelOptions();
    return state.aiProviders;
  }

  function updateModeUI() {
    const mode = guidedSearchMode();
    const templatePanel = byId("gs-template-panel");
    const aiPanel = byId("gs-ai-panel");
    const buildButton = byId("gs-build-button");

    if (templatePanel) {
      templatePanel.style.display = mode === "template" ? "grid" : "none";
    }
    if (aiPanel) {
      aiPanel.style.display = mode === "ai" ? "grid" : "none";
    }
    if (buildButton) {
      buildButton.textContent = mode === "ai" ? "Generate Cypher" : "Build Cypher";
    }

    if (mode === "template") {
      updateTemplateUI();
      return;
    }

    loadGuidedAiProviders().catch((error) => {
      setStatus(error.message || String(error), true);
    });

    const aiQuestion = byId("gs-ai-question");
    if (aiQuestion) {
      aiQuestion.focus();
    }
  }

  function hideSuggestions(prefix) {
    const box = byId(`gs-${prefix}-suggestions`);
    if (box) {
      box.style.display = "none";
      box.innerHTML = "";
    }
  }

  function updateSelectionLabel(prefix) {
    const label = byId(`gs-${prefix}-selection`);
    const selection = prefix === "source" ? state.sourceSelection : state.targetSelection;
    if (!label) return;
    label.textContent = selection ? `Selected id_rc: ${selection.id_rc}` : "";
  }

  function clearSelection(prefix) {
    if (prefix === "source") {
      state.sourceSelection = null;
    } else {
      state.targetSelection = null;
    }
    updateSelectionLabel(prefix);
  }

  function chooseSuggestion(prefix, item) {
    if (prefix === "source") {
      state.sourceSelection = item;
    } else {
      state.targetSelection = item;
    }

    const input = byId(`gs-${prefix}-name`);
    if (input) input.value = item.name;
    updateSelectionLabel(prefix);
    hideSuggestions(prefix);
  }

  function renderSuggestions(prefix, items) {
    const box = byId(`gs-${prefix}-suggestions`);
    if (!box) return;

    if (!items.length) {
      box.innerHTML = '<div style="padding:8px; font-size:12px; color:#666;">No matches found.</div>';
      box.style.display = "block";
      return;
    }

    box.innerHTML = "";
    items.forEach((item) => {
      const row = document.createElement("button");
      row.type = "button";
      row.style.display = "block";
      row.style.width = "100%";
      row.style.textAlign = "left";
      row.style.padding = "8px";
      row.style.border = "0";
      row.style.borderBottom = "1px solid #eee";
      row.style.background = "#fff";
      row.style.color = "#111";
      row.style.borderRadius = "0";
      row.style.fontWeight = "400";
      row.textContent = `${item.name} (${item.id_rc})`;
      row.onmouseenter = function () {
        row.style.background = "#f3f6fb";
      };
      row.onmouseleave = function () {
        row.style.background = "#fff";
      };
      row.onclick = function () {
        chooseSuggestion(prefix, item);
      };
      box.appendChild(row);
    });
    box.style.display = "block";
  }

  async function fetchNodeSuggestions(prefix) {
    const nodeType = byId(`gs-${prefix}-type`)?.value || "";
    const input = byId(`gs-${prefix}-name`);
    const queryText = input?.value.trim() || "";

    if (!nodeType) {
      hideSuggestions(prefix);
      return;
    }

    try {
      const params = new URLSearchParams({
        node_type: nodeType,
        q: queryText,
        limit: "12",
      });
      const project = currentProject();
      if (project) params.set("project", project);

      const data = await getJson(`/api/search/node-names?${params.toString()}`);
      renderSuggestions(prefix, data.items || []);
    } catch (error) {
      hideSuggestions(prefix);
      setStatus(error.message || String(error), true);
    }
  }

  function queueAutocomplete(prefix) {
    const timerKey = prefix === "source" ? "sourceTimer" : "targetTimer";
    clearTimeout(state[timerKey]);
    state[timerKey] = setTimeout(() => {
      fetchNodeSuggestions(prefix);
    }, 220);
  }

  function selectedEdgeTypes() {
    return Array.from(document.querySelectorAll(".gs-edge-type-checkbox:checked")).map((checkbox) => checkbox.value);
  }

  async function loadTemplates() {
    const data = await getJson("/api/search/templates");
    state.templates = Array.isArray(data.templates) ? data.templates : [];
    renderTemplateOptions();
  }

  async function loadNodeTypes() {
    const project = currentProject();
    const candidateUrls = [];

    if (project) {
      candidateUrls.push(`/get_node_types?projectName=${encodeURIComponent(project)}`);
      candidateUrls.push(`/nodes/get_node_types?projectName=${encodeURIComponent(project)}`);
    }
    candidateUrls.push(`/get_node_types?projectName=ALL`);
    candidateUrls.push(`/nodes/get_node_types?projectName=ALL`);

    let lastError = null;
    for (const url of candidateUrls) {
      try {
        const response = await fetch(url, { credentials: "same-origin" });
        if (!response.ok) {
          lastError = new Error(`Request failed: ${response.status}`);
          continue;
        }
        const data = await response.json();
        if (Array.isArray(data) && data.length) {
          state.nodeTypes = data;
          renderNodeTypeOptions();
          return;
        }
      } catch (error) {
        lastError = error;
      }
    }

    state.nodeTypes = [];
    renderNodeTypeOptions();

    if (lastError) {
      throw lastError;
    }
  }

  async function loadEdgeTypes() {
    const params = new URLSearchParams();
    const project = currentProject();
    if (project) params.set("project", project);
    const suffix = params.toString() ? `?${params.toString()}` : "";
    const data = await getJson(`/api/search/edge-types${suffix}`);
    state.edgeTypes = Array.isArray(data.edge_types) ? data.edge_types : [];
    renderEdgeTypes();
  }

  async function ensureDialogData() {
    if (!state.templates.length) {
      await loadTemplates();
    }
    if (!state.nodeTypes.length) {
      await loadNodeTypes();
    }
    if (!state.edgeTypes.length) {
      await loadEdgeTypes();
    }
    if (!state.aiProviders) {
      await loadGuidedAiProviders();
    }
    updateModeUI();

    if (!state.nodeTypes.length) {
      setStatus("No source node types were returned from Neo4j. Check NodeType data and project filtering.", true);
    }
  }

  function payloadForBuild() {
    return {
      template: byId("gs-template")?.value || "",
      project: currentProject(),
      source: {
        id_rc: state.sourceSelection?.id_rc || "",
        node_type: byId("gs-source-type")?.value || "",
        name: byId("gs-source-name")?.value.trim() || "",
      },
      target: {
        id_rc: state.targetSelection?.id_rc || "",
        node_type: byId("gs-target-type")?.value || "",
        name: byId("gs-target-name")?.value.trim() || "",
      },
      edge_types: selectedEdgeTypes(),
    };
  }

  function payloadForAiBuild() {
    return {
      question: byId("gs-ai-question")?.value.trim() || "",
      provider: byId("gs-ai-provider")?.value || "",
      model: byId("gs-ai-model")?.value || "",
      project: currentProject(),
      source: {
        id_rc: state.sourceSelection?.id_rc || "",
        node_type: byId("gs-source-type")?.value || "",
        name: byId("gs-source-name")?.value.trim() || "",
      },
      target: {
        id_rc: state.targetSelection?.id_rc || "",
        node_type: byId("gs-target-type")?.value || "",
        name: byId("gs-target-name")?.value.trim() || "",
      },
      edge_types: selectedEdgeTypes(),
    };
  }

  function focusCypherDialog() {
    if (typeof window.openCypherDialog === "function") {
      window.openCypherDialog();
    } else {
      const dialog = byId("cypher-dialog");
      if (dialog) dialog.style.display = "block";
    }
    const textarea = byId("cypher-input");
    if (textarea) {
      textarea.focus();
      if (typeof window.resizeDialog === "function") {
        window.resizeDialog();
      }
    }
  }

  window.openGuidedSearchDialog = async function () {
    const dialog = byId("guided-search-dialog");
    if (!dialog) return;
    dialog.style.display = "block";
    if (typeof window.makeDialogDraggable === "function") {
      window.makeDialogDraggable(dialog);
    }
    setStatus("Loading guided search metadata...", false);

    try {
      await ensureDialogData();
      const aiQuestion = byId("gs-ai-question");
      if (aiQuestion && !aiQuestion.value.trim()) {
        aiQuestion.value = "Write Cypher that returns the graph for all procedures that do insert operations.";
      }
      setStatus(guidedSearchMode() === "ai" ? "Describe the graph you want in natural language." : "Choose a template and a source node.", false);
    } catch (error) {
      setStatus(error.message || String(error), true);
    }
  };

  window.closeGuidedSearchDialog = function () {
    const dialog = byId("guided-search-dialog");
    if (dialog) {
      dialog.style.display = "none";
    }
    hideSuggestions("source");
    hideSuggestions("target");
  };

  window.selectAllGuidedEdgeTypes = function (checked) {
    document.querySelectorAll(".gs-edge-type-checkbox").forEach((checkbox) => {
      checkbox.checked = Boolean(checked);
    });
  };

  window.buildGuidedSearchCypher = async function () {
    const mode = guidedSearchMode();
    const isAiMode = mode === "ai";
    setStatus(isAiMode ? "Generating Cypher with AI..." : "Building Cypher...", false);

    try {
      const payload = isAiMode ? payloadForAiBuild() : payloadForBuild();
      if (isAiMode && !payload.question) {
        throw new Error("Please describe the graph you want.");
      }

      const data = await getJson(isAiMode ? "/api/search/ai-build-cypher" : "/api/search/build-cypher", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload),
      });

      const textarea = byId("cypher-input");
      if (!textarea) {
        throw new Error("Cypher dialog textarea not found");
      }

      textarea.value = data.cypher || "";
      focusCypherDialog();
      setStatus(isAiMode ? "AI-generated Cypher inserted into the Cypher dialog." : "Cypher generated and inserted into the Cypher dialog.", false);
      window.closeGuidedSearchDialog();
    } catch (error) {
      setStatus(error.message || String(error), true);
    }
  };

  function installHandlers() {
    const modeSelect = byId("gs-mode");
    if (modeSelect) {
      modeSelect.addEventListener("change", function () {
        updateModeUI();
        setStatus(guidedSearchMode() === "ai" ? "Describe the graph you want in natural language." : "Choose a template and a source node.", false);
      });
    }

    const templateSelect = byId("gs-template");
    if (templateSelect) {
      templateSelect.addEventListener("change", updateTemplateUI);
    }

    const sourceType = byId("gs-source-type");
    if (sourceType) {
      sourceType.addEventListener("change", function () {
        const input = byId("gs-source-name");
        if (input) input.value = "";
        clearSelection("source");
        hideSuggestions("source");
        fetchNodeSuggestions("source");
      });
    }

    const targetType = byId("gs-target-type");
    if (targetType) {
      targetType.addEventListener("change", function () {
        const input = byId("gs-target-name");
        if (input) input.value = "";
        clearSelection("target");
        hideSuggestions("target");
        fetchNodeSuggestions("target");
      });
    }

    const sourceName = byId("gs-source-name");
    if (sourceName) {
      sourceName.addEventListener("input", function () {
        if (state.sourceSelection && sourceName.value.trim() !== state.sourceSelection.name) {
          clearSelection("source");
        }
        queueAutocomplete("source");
      });
      sourceName.addEventListener("focus", function () {
        fetchNodeSuggestions("source");
      });
    }

    const targetName = byId("gs-target-name");
    if (targetName) {
      targetName.addEventListener("input", function () {
        if (state.targetSelection && targetName.value.trim() !== state.targetSelection.name) {
          clearSelection("target");
        }
        queueAutocomplete("target");
      });
      targetName.addEventListener("focus", function () {
        fetchNodeSuggestions("target");
      });
    }

    document.addEventListener("click", function (event) {
      const sourceBox = byId("gs-source-suggestions");
      const targetBox = byId("gs-target-suggestions");
      const sourceInput = byId("gs-source-name");
      const targetInput = byId("gs-target-name");

      if (sourceBox && sourceInput && !sourceBox.contains(event.target) && event.target !== sourceInput) {
        hideSuggestions("source");
      }
      if (targetBox && targetInput && !targetBox.contains(event.target) && event.target !== targetInput) {
        hideSuggestions("target");
      }
    });
  }

  document.addEventListener("DOMContentLoaded", installHandlers);
})();
