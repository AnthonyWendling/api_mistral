(function () {
  "use strict";

  const API_BASE = "/vectors";

  const $ = (sel, el = document) => el.querySelector(sel);
  const $$ = (sel, el = document) => el.querySelectorAll(sel);

  let currentCollectionId = null;
  let currentCollectionName = null;

  function showSection(sectionId) {
    $("#section-list").hidden = sectionId !== "list";
    $("#section-detail").hidden = sectionId !== "detail";
    $("#section-create").hidden = sectionId !== "create";
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

  async function loadCollections() {
    const list = $("#collections-list");
    const loading = $("#collections-loading");
    const errEl = $("#collections-error");
    list.innerHTML = "";
    errEl.hidden = true;
    loading.hidden = false;
    try {
      const data = await api("GET", "/collections");
      loading.hidden = true;
      if (!data.collections || data.collections.length === 0) {
        list.innerHTML = "<p class=\"empty\">Aucune collection. Créez-en une.</p>";
        return;
      }
      data.collections.forEach((c) => {
        const card = document.createElement("div");
        card.className = "collection-card";
        card.innerHTML = `<div><span class="name">${escapeHtml(c.name)}</span><br><span class="id">${escapeHtml(c.id)}</span></div>`;
        card.addEventListener("click", () => openCollection(c.id, c.name));
        list.appendChild(card);
      });
    } catch (e) {
      loading.hidden = true;
      errEl.textContent = e.message || "Erreur chargement collections";
      errEl.hidden = false;
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
    showSection("detail");
    loadDocuments();
    $("#search-results").hidden = true;
    $("#search-results").innerHTML = "";
    $("#input-query").value = "";
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
      showSection("list");
      loadCollections();
    } catch (e) {
      showToast(e.message || "Erreur suppression", true);
    }
  }

  $("#btn-back").addEventListener("click", () => {
    showSection("list");
    loadCollections();
  });

  $("#btn-new-collection").addEventListener("click", () => {
    showSection("create");
    $("#input-collection-name").value = "";
    $("#input-collection-name").focus();
    hideMessage("#create-message");
  });

  $("#btn-cancel-create").addEventListener("click", () => {
    showSection("list");
  });

  $("#btn-delete-collection").addEventListener("click", deleteCollection);

  $("#form-create-collection").addEventListener("submit", async (ev) => {
    ev.preventDefault();
    const name = $("#input-collection-name").value.trim();
    if (!name) return;
    hideMessage("#create-message");
    try {
      await api("POST", "/collections", {
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ name }),
      });
      showToast("Collection créée");
      showSection("list");
      loadCollections();
    } catch (e) {
      showMessage("#create-message", e.message || "Erreur création", "error");
    }
  });

  const inputFile = $("#input-file");
  const uploadPlaceholder = $("#upload-placeholder");
  const btnUpload = $("#btn-upload");

  inputFile.addEventListener("change", () => {
    const file = inputFile.files[0];
    uploadPlaceholder.textContent = file ? file.name : "Choisir un fichier";
    btnUpload.disabled = !file;
  });

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
    if (!file || !currentCollectionId) return;
    hideMessage("#upload-message");
    btnUpload.disabled = true;
    const formData = new FormData();
    formData.append("file", file);
    const docId = $("#input-document-id").value.trim();
    if (docId) formData.append("document_id", docId);
    try {
      const data = await fetch(API_BASE + `/collections/${encodeURIComponent(currentCollectionId)}/index`, {
        method: "POST",
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
      }
    } catch (e) {
      showMessage("#upload-message", e.message || "Erreur indexation", "error");
    } finally {
      btnUpload.disabled = !inputFile.files[0];
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
    try {
      const data = await api("POST", `/collections/${encodeURIComponent(currentCollectionId)}/search`, {
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ query, top_k: Math.max(1, Math.min(100, topK)) }),
      });
      loadingEl.hidden = true;
      if (!data.results || data.results.length === 0) {
        resultsEl.innerHTML = "<p class=\"empty\">Aucun résultat.</p>";
      } else {
        data.results.forEach((r) => {
          const div = document.createElement("div");
          div.className = "search-result-item";
          const dist = r.distance != null ? "Distance : " + r.distance.toFixed(4) : "";
          const metaStr = r.metadata && (r.metadata.source_file || r.metadata.document_id) ? [r.metadata.source_file, r.metadata.document_id].filter(Boolean).join(" · ") : "";
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

  loadCollections();
})();
