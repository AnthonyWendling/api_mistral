(function () {
  "use strict";

  const API_BASE = "/vectors";

  const $ = (sel, el = document) => el.querySelector(sel);
  const $$ = (sel, el = document) => el.querySelectorAll(sel);

  let currentCollectionId = null;
  let currentCollectionName = null;

  async function checkAuth() {
    try {
      const r = await fetch("/auth/check", { method: "GET", credentials: "include" });
      return r.ok;
    } catch (e) {
      return false;
    }
  }

  function showLoginScreen() {
    const login = $("#login-screen");
    const app = $("#app-content");
    if (login) login.hidden = false;
    if (app) app.hidden = true;
  }

  function showAppScreen() {
    const login = $("#login-screen");
    const app = $("#app-content");
    if (login) login.hidden = true;
    if (app) app.hidden = false;
    loadCollections();
  }

  function showRightPanel(panel) {
    const form = $("#section-create");
    const detail = $("#section-detail");
    const sources = $("#section-sources");
    if (form) form.hidden = panel !== "create";
    if (detail) detail.hidden = panel !== "detail";
    if (sources) sources.hidden = panel !== "sources";
    if (panel === "sources") loadSourcesList();
  }

  function showToast(message, isError = false) {
    const toast = $("#toast");
    toast.textContent = message;
    toast.className = "toast" + (isError ? " error" : "");
    toast.hidden = false;
    setTimeout(() => {
      toast.hidden = true;
    }, 4000);
  }

  function showMessage(containerId, message, type) {
    const el = $(containerId);
    if (!el) return;
    el.textContent = message;
    el.className = "message " + (type || "");
    el.hidden = false;
  }

  function hideMessage(containerId) {
    const el = $(containerId);
    if (el) el.hidden = true;
  }

  async function api(method, path, options = {}) {
    const url = path.startsWith("http") ? path : API_BASE + path;
    const res = await fetch(url, {
      method,
      headers: options.headers || {},
      body: options.body,
    });
    if (!res.ok) {
      const err = await res.json().catch(() => ({ detail: res.statusText }));
      throw new Error(err.detail || err.message || res.statusText);
    }
    if (res.status === 204) return null;
    return res.json();
  }

  let collectionsFlat = [];

  async function loadCollections() {
    const list = $("#collections-list");
    const loading = $("#collections-loading");
    const errEl = $("#collections-error");
    list.innerHTML = "";
    errEl.hidden = true;
    loading.hidden = false;
    try {
      const dataTree = await api("GET", "/collections?tree=true");
      const dataFlat = await api("GET", "/collections");
      collectionsFlat = dataFlat.collections || [];
      loading.hidden = true;
      const roots = dataTree.collections || [];
      if (roots.length === 0) {
        list.innerHTML = "<p class=\"empty\">Aucune collection. Créez-en une (ou une sous-collection).</p>";
        return;
      }
      function renderNode(node, depth, parentWrap) {
        const hasChildren = (node.children || []).length > 0;
        if (hasChildren && depth === 0) {
          const group = document.createElement("div");
          group.className = "collection-group";
          const card = document.createElement("div");
          card.className = "collection-card collection-card--parent";
          card.innerHTML = `
            <span class="collection-toggle" aria-label="Replier / déplier">▼</span>
            <div class="collection-card-body">
              <span class="name">${escapeHtml(node.name)}</span><br><span class="id">${escapeHtml(node.id)}</span>
            </div>`;
          const toggle = card.querySelector(".collection-toggle");
          const childrenWrap = document.createElement("div");
          childrenWrap.className = "collection-children";
          (node.children || []).forEach((child) => renderNode(child, depth + 1, childrenWrap));
          toggle.addEventListener("click", (e) => {
            e.stopPropagation();
            childrenWrap.classList.toggle("collapsed");
            toggle.textContent = childrenWrap.classList.contains("collapsed") ? "▶" : "▼";
            toggle.setAttribute("aria-label", childrenWrap.classList.contains("collapsed") ? "Déplier" : "Replier");
          });
          card.querySelector(".collection-card-body").addEventListener("click", (e) => { e.stopPropagation(); openCollection(node.id, node.name); });
          group.appendChild(card);
          group.appendChild(childrenWrap);
          list.appendChild(group);
        } else {
          const card = document.createElement("div");
          card.className = "collection-card" + (depth > 0 ? " collection-card--child" : "");
          card.style.setProperty("--depth", String(depth));
          const subLabel = depth > 0 ? "<span class=\"card-sub\">sous-collection</span> " : "";
          card.innerHTML = `<div>${subLabel}<span class="name">${escapeHtml(node.name)}</span><br><span class="id">${escapeHtml(node.id)}</span></div>`;
          card.addEventListener("click", (e) => { e.stopPropagation(); openCollection(node.id, node.name); });
          const target = parentWrap || list;
          target.appendChild(card);
          (node.children || []).forEach((child) => renderNode(child, depth + 1, target));
        }
      }
      roots.forEach((root) => renderNode(root, 0));
    } catch (e) {
      loading.hidden = true;
      errEl.textContent = e.message || "Erreur chargement collections";
      errEl.hidden = false;
    }
  }

  function fillParentSelect() {
    const sel = $("#input-collection-parent");
    if (!sel) return;
    sel.innerHTML = "<option value=\"\">— Aucune (collection racine) —</option>";
    collectionsFlat.filter((c) => !c.parent_id).forEach((c) => {
      const opt = document.createElement("option");
      opt.value = c.id;
      opt.textContent = c.name + " (" + c.id + ")";
      sel.appendChild(opt);
    });
  }

  async function loadSourcesList() {
    const list = $("#sources-list");
    const loading = $("#sources-loading");
    if (!list) return;
    list.innerHTML = "";
    if (loading) loading.hidden = false;
    try {
      const data = await api("GET", "/sources");
      const sources = Array.isArray(data) ? data : (data.sources || data);
      if (loading) loading.hidden = true;
      if (!sources || sources.length === 0) {
        list.innerHTML = "<p class=\"empty\">Aucune connexion. Ajoutez une table NocoDB ci-dessous.</p>";
        return;
      }
      sources.forEach((s) => {
        const row = document.createElement("div");
        row.className = "source-row";
        row.innerHTML = `
          <div class="source-info">
            <span class="source-name">${escapeHtml(s.name)}</span>
            <span class="source-type">${escapeHtml(s.type)}</span>
          </div>
          <div class="source-actions">
            <button type="button" class="btn btn-primary btn-sync-source" data-id="${escapeHtml(s.id)}">Indexer</button>
            <button type="button" class="btn btn-danger btn-delete-source" data-id="${escapeHtml(s.id)}">Suppr.</button>
          </div>
        `;
        row.querySelector(".btn-sync-source").addEventListener("click", () => syncSource(s.id));
        row.querySelector(".btn-delete-source").addEventListener("click", () => deleteSource(s.id));
        list.appendChild(row);
      });
    } catch (e) {
      if (loading) loading.hidden = true;
      list.innerHTML = "<p class=\"error\">" + escapeHtml(e.message) + "</p>";
    }
  }

  async function syncSource(sourceId) {
    const btn = document.querySelector(".btn-sync-source[data-id=\"" + sourceId + "\"]");
    if (btn) btn.disabled = true;
    try {
      const result = await api("POST", "/sources/" + encodeURIComponent(sourceId) + "/sync");
      showToast("Indexation : " + (result.indexed || 0) + " chunk(s). " + (result.errors && result.errors.length ? result.errors.length + " erreur(s)." : ""));
      loadSourcesList();
    } catch (e) {
      showToast(e.message || "Erreur sync", true);
    } finally {
      if (btn) btn.disabled = false;
    }
  }

  async function deleteSource(sourceId) {
    if (!confirm("Supprimer cette connexion API ?")) return;
    try {
      await api("DELETE", "/sources/" + encodeURIComponent(sourceId));
      showToast("Connexion supprimée");
      loadSourcesList();
    } catch (e) {
      showToast(e.message || "Erreur suppression", true);
    }
  }

  function escapeHtml(s) {
    if (s == null) return "";
    const div = document.createElement("div");
    div.textContent = s;
    return div.innerHTML;
  }

  function openCollection(id, name) {
    currentCollectionId = id;
    currentCollectionName = name;
    $("#detail-title").textContent = name;
    $("#detail-id").textContent = "ID : " + id;
    showRightPanel("detail");
    loadDocuments();
    $("#search-results").hidden = true;
    $("#search-results").innerHTML = "";
    $("#input-query").value = "";
    updateUploadButton();
  }

  async function loadDocuments() {
    if (!currentCollectionId) return;
    const list = $("#documents-list");
    const loading = $("#documents-loading");
    const empty = $("#documents-empty");
    list.innerHTML = "";
    empty.hidden = true;
    loading.hidden = false;
    try {
      const data = await api("GET", `/collections/${encodeURIComponent(currentCollectionId)}/documents`);
      loading.hidden = true;
      if (!data.documents || data.documents.length === 0) {
        empty.hidden = false;
        return;
      }
      data.documents.forEach((doc) => {
        const row = document.createElement("div");
        row.className = "document-row";
        const source = doc.source_file || doc.file_url || doc.document_id || "—";
        const meta = [doc.date, doc.document_id].filter(Boolean).join(" · ");
        row.innerHTML = `
          <div class="doc-info">
            <span class="source">${escapeHtml(source)}</span>
            ${meta ? `<div class="meta">${escapeHtml(meta)}</div>` : ""}
          </div>
          <button type="button" class="btn btn-danger btn-delete-doc" data-doc-id="${escapeHtml(doc.document_id)}">Supprimer</button>
        `;
        row.querySelector(".btn-delete-doc").addEventListener("click", (ev) => {
          ev.stopPropagation();
          deleteDocument(doc.document_id);
        });
        list.appendChild(row);
      });
    } catch (e) {
      loading.hidden = true;
      showToast(e.message || "Erreur chargement documents", true);
    }
  }

  async function deleteDocument(documentId) {
    if (!currentCollectionId || !confirm("Supprimer ce document de la collection ?")) return;
    try {
      await api("DELETE", `/collections/${encodeURIComponent(currentCollectionId)}/documents/${encodeURIComponent(documentId)}`);
      showToast("Document supprimé");
      loadDocuments();
    } catch (e) {
      showToast(e.message || "Erreur suppression", true);
    }
  }

  async function deleteCollection() {
    if (!currentCollectionId || !confirm("Supprimer toute la collection ? Cette action est irréversible.")) return;
    try {
      await api("DELETE", `/collections/${encodeURIComponent(currentCollectionId)}`);
      showToast("Collection supprimée");
      currentCollectionId = null;
      currentCollectionName = null;
      showRightPanel("create");
      loadCollections();
    } catch (e) {
      showToast(e.message || "Erreur suppression", true);
    }
  }

  $("#btn-back").addEventListener("click", () => {
    showRightPanel("create");
    loadCollections();
  });

  $("#btn-new-collection").addEventListener("click", () => {
    showRightPanel("create");
    $("#input-collection-name").value = "";
    fillParentSelect();
    $("#input-collection-name").focus();
    hideMessage("#create-message");
  });

  const btnCancelCreate = $("#btn-cancel-create");
  if (btnCancelCreate) btnCancelCreate.addEventListener("click", () => showRightPanel("create"));

  const btnSources = $("#btn-sources");
  if (btnSources) btnSources.addEventListener("click", () => showRightPanel("sources"));
  const btnSourcesBack = $("#btn-sources-back");
  if (btnSourcesBack) btnSourcesBack.addEventListener("click", () => showRightPanel("create"));

  const formCreateSource = $("#form-create-source");
  if (formCreateSource) {
    formCreateSource.addEventListener("submit", async (ev) => {
      ev.preventDefault();
      const name = $("#input-source-name") && $("#input-source-name").value.trim();
      const baseUrl = $("#input-source-base-url") && $("#input-source-base-url").value.trim();
      const apiKey = $("#input-source-api-key") && $("#input-source-api-key").value.trim();
      const tableId = $("#input-source-table-id") && $("#input-source-table-id").value.trim();
      const collectionId = $("#input-source-collection-id") && $("#input-source-collection-id").value.trim();
      let fieldMapping = {};
      const mappingEl = $("#input-source-field-mapping");
      if (mappingEl && mappingEl.value.trim()) {
        try {
          fieldMapping = JSON.parse(mappingEl.value.trim());
        } catch (e) {
          showMessage("#source-create-message", "Mapping JSON invalide.", "error");
          return;
        }
      }
      hideMessage("#source-create-message");
      try {
        await api("POST", "/sources", {
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            name: name || "NocoDB",
            type: "nocodb",
            enabled: true,
            config: {
              base_url: baseUrl,
              api_key: apiKey,
              table_id: tableId,
              collection_id: collectionId || "nocodb-documents",
              field_mapping: fieldMapping,
              limit: 100,
            },
          }),
        });
        showToast("Connexion ajoutée");
        formCreateSource.reset();
        loadSourcesList();
      } catch (e) {
        showMessage("#source-create-message", e.message || "Erreur", "error");
      }
    });
  }

  const btnBulkCreate = $("#btn-bulk-create-collections");
  if (btnBulkCreate) {
    btnBulkCreate.addEventListener("click", async () => {
      const raw = $("#input-collections-json") && $("#input-collections-json").value.trim();
      if (!raw) {
        showMessage("#bulk-create-message", "Collez un JSON (tableau de noms ou d'objets).", "error");
        return;
      }
      let items = [];
      try {
        const parsed = JSON.parse(raw);
        items = Array.isArray(parsed) ? parsed : [parsed];
      } catch (e) {
        showMessage("#bulk-create-message", "JSON invalide.", "error");
        return;
      }
      const collections = [];
      for (const it of items) {
        if (typeof it === "string") {
          if (it.trim()) collections.push({ name: it.trim(), parent_id: null });
        } else if (it && typeof it === "object" && it.name) {
          collections.push({ name: String(it.name).trim(), parent_id: it.parent_id || null });
        }
      }
      if (!collections.length) {
        showMessage("#bulk-create-message", "Aucune collection valide dans le JSON.", "error");
        return;
      }
      hideMessage("#bulk-create-message");
      btnBulkCreate.disabled = true;
      try {
        const result = await api("POST", "/collections/bulk", {
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ collections }),
        });
        showMessage("#bulk-create-message", result.count + " collection(s) créée(s).", "success");
        $("#input-collections-json").value = "";
        loadCollections();
      } catch (e) {
        showMessage("#bulk-create-message", e.message || "Erreur", "error");
      } finally {
        btnBulkCreate.disabled = false;
      }
    });
  }

  $("#btn-delete-collection").addEventListener("click", deleteCollection);

  $("#form-create-collection").addEventListener("submit", async (ev) => {
    ev.preventDefault();
    const name = $("#input-collection-name").value.trim();
    if (!name) return;
    const parentId = $("#input-collection-parent") && $("#input-collection-parent").value ? $("#input-collection-parent").value.trim() || null : null;
    hideMessage("#create-message");
    try {
      await api("POST", "/collections", {
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ name, parent_id: parentId || undefined }),
      });
      showToast(parentId ? "Sous-collection créée" : "Collection créée");
      showRightPanel("create");
      loadCollections();
    } catch (e) {
      showMessage("#create-message", e.message || "Erreur création", "error");
    }
  });

  const inputFile = $("#input-file");
  const uploadPlaceholder = $("#upload-placeholder");
  const btnUpload = $("#btn-upload");

  const inputFileUrl = $("#input-file-url");
  function updateUploadButton() {
    const hasFile = inputFile.files[0];
    const hasUrl = inputFileUrl && inputFileUrl.value.trim();
    btnUpload.disabled = !hasFile && !hasUrl;
  }
  inputFile.addEventListener("change", () => {
    uploadPlaceholder.textContent = inputFile.files[0] ? inputFile.files[0].name : "Choisir un fichier";
    updateUploadButton();
  });
  if (inputFileUrl) inputFileUrl.addEventListener("input", updateUploadButton);

  const formUpload = $("#form-upload");
  if (formUpload) {
    formUpload.addEventListener("dragover", (ev) => {
      ev.preventDefault();
      formUpload.classList.add("drag-over");
    });
    formUpload.addEventListener("dragleave", () => formUpload.classList.remove("drag-over"));
    formUpload.addEventListener("drop", (ev) => {
      ev.preventDefault();
      formUpload.classList.remove("drag-over");
      const file = ev.dataTransfer && ev.dataTransfer.files[0];
      if (file) {
        const dt = new DataTransfer();
        dt.items.add(file);
        inputFile.files = dt.files;
        uploadPlaceholder.textContent = file.name;
        btnUpload.disabled = false;
      }
    });
  }

  $("#form-upload").addEventListener("submit", async (ev) => {
    ev.preventDefault();
    const file = inputFile.files[0];
    const fileUrl = inputFileUrl && inputFileUrl.value.trim();
    if ((!file && !fileUrl) || !currentCollectionId) return;
    hideMessage("#upload-message");
    btnUpload.disabled = true;
    const formData = new FormData();
    const docId = $("#input-document-id").value.trim();
    if (docId) formData.append("document_id", docId);
    if (file) {
      formData.append("file", file);
    } else {
      formData.append("file_url", fileUrl);
    }
    try {
      const data = await fetch(API_BASE + `/collections/${encodeURIComponent(currentCollectionId)}/index`, {
        method: "POST",
        credentials: "include",
        body: formData,
      });
      if (!data.ok) {
        const err = await data.json().catch(() => ({}));
        throw new Error(err.detail || data.statusText);
      }
      const result = await data.json();
      const chunks = result.indexed_chunks ?? 0;
      showMessage("#upload-message", chunks > 0 ? `${chunks} chunk(s) indexé(s).` : (result.message || "Aucun texte extrait."), chunks > 0 ? "success" : "error");
      if (chunks > 0) {
        loadDocuments();
        inputFile.value = "";
        uploadPlaceholder.textContent = "Choisir un fichier";
        if (inputFileUrl) inputFileUrl.value = "";
      }
    } catch (e) {
      showMessage("#upload-message", e.message || "Erreur indexation", "error");
    } finally {
      updateUploadButton();
      btnUpload.disabled = !inputFile.files[0] && !(inputFileUrl && inputFileUrl.value.trim());
    }
  });

  $("#form-search").addEventListener("submit", async (ev) => {
    ev.preventDefault();
    const query = $("#input-query").value.trim();
    const topK = parseInt($("#input-top-k").value, 10) || 10;
    if (!query || !currentCollectionId) return;
    const resultsEl = $("#search-results");
    const loadingEl = $("#search-loading");
    resultsEl.hidden = true;
    resultsEl.innerHTML = "";
    loadingEl.hidden = false;
    const includeSub = $("#input-include-subcollections") && $("#input-include-subcollections").checked;
    try {
      const data = await api("POST", `/collections/${encodeURIComponent(currentCollectionId)}/search`, {
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ query, top_k: Math.max(1, Math.min(100, topK)), include_subcollections: includeSub }),
      });
      loadingEl.hidden = true;
      if (!data.results || data.results.length === 0) {
        resultsEl.innerHTML = "<p class=\"empty\">Aucun résultat.</p>";
      } else {
        data.results.forEach((r) => {
          const div = document.createElement("div");
          div.className = "search-result-item";
          const dist = r.distance != null ? "Distance : " + r.distance.toFixed(4) : "";
          const metaParts = [];
          if (r.metadata) {
            if (r.metadata._collection_id) metaParts.push("Collection : " + r.metadata._collection_id);
            if (r.metadata.source_file || r.metadata.document_id) metaParts.push([r.metadata.source_file, r.metadata.document_id].filter(Boolean).join(" · "));
          }
          const metaStr = metaParts.filter(Boolean).join(" — ");
          div.innerHTML = `
            <div class="score">${escapeHtml(dist)}</div>
            <div class="text">${escapeHtml(r.text)}</div>
            ${metaStr ? `<div class="meta">${escapeHtml(metaStr)}</div>` : ""}
          `;
          resultsEl.appendChild(div);
        });
      }
      resultsEl.hidden = false;
    } catch (e) {
      loadingEl.hidden = true;
      showToast(e.message || "Erreur recherche", true);
    }
  });

  async function init() {
    const ok = await checkAuth();
    if (ok) {
      showAppScreen();
    } else {
      showLoginScreen();
      const formLogin = $("#form-login");
      const msgEl = $("#login-message");
      if (formLogin) {
        formLogin.addEventListener("submit", async (ev) => {
          ev.preventDefault();
          const code = $("#input-login-code") && $("#input-login-code").value.trim();
          const password = $("#input-login-password") && $("#input-login-password").value;
          if (!code || !password) return;
          if (msgEl) msgEl.hidden = true;
          try {
            const r = await fetch("/auth/login", {
              method: "POST",
              credentials: "include",
              headers: { "Content-Type": "application/json" },
              body: JSON.stringify({ code, password }),
            });
            if (r.ok) {
              showAppScreen();
            } else {
              const err = await r.json().catch(() => ({}));
              if (msgEl) {
                msgEl.textContent = err.detail || "Code ou mot de passe incorrect.";
                msgEl.className = "message error";
                msgEl.hidden = false;
              }
            }
          } catch (e) {
            if (msgEl) {
              msgEl.textContent = e.message || "Erreur de connexion.";
              msgEl.className = "message error";
              msgEl.hidden = false;
            }
          }
        });
      }
    }
  }

  init();
})();
