"""
Gestion des connexions API (sources) et synchronisation NocoDB → indexation vectorielle.
"""
import json
import re
import uuid
from pathlib import Path

import httpx

from app.config import settings
from app.services.vector_store_service import create_collection, list_collections

SOURCES_FILE = Path(settings.chroma_data_path).parent / "sources.json"


def _load_sources() -> list[dict]:
    if not SOURCES_FILE.exists():
        return []
    try:
        data = json.loads(SOURCES_FILE.read_text(encoding="utf-8"))
        return data.get("sources", [])
    except Exception:
        return []


def _save_sources(sources: list[dict]) -> None:
    SOURCES_FILE.parent.mkdir(parents=True, exist_ok=True)
    SOURCES_FILE.write_text(json.dumps({"sources": sources}, indent=2, ensure_ascii=False), encoding="utf-8")


def _slug(s: str) -> str:
    return re.sub(r"[^a-z0-9_-]", "-", (s or "").lower()).strip("-") or "default"


def _mask_secrets(config: dict) -> dict:
    """Masque les secrets dans la config pour l'affichage."""
    cfg = dict(config)
    for key in ("api_key", "client_secret"):
        if cfg.get(key):
            cfg[key] = "********"
    return cfg


def list_sources() -> list[dict]:
    """Liste toutes les sources (sans exposer les clés API en clair dans les configs sensibles)."""
    raw = _load_sources()
    out = []
    for s in raw:
        cfg = _mask_secrets(s.get("config", {}))
        out.append({
            "id": s.get("id", ""),
            "name": s.get("name", ""),
            "type": s.get("type", "nocodb"),
            "enabled": s.get("enabled", True),
            "config": cfg,
        })
    return out


def get_source(source_id: str) -> dict | None:
    """Retourne une source par id (avec la vraie api_key pour le sync)."""
    for s in _load_sources():
        if s.get("id") == source_id:
            return s
    return None


def create_source(payload: dict) -> dict:
    """Crée une source et la persiste."""
    sources = _load_sources()
    sid = str(uuid.uuid4())[:8]
    entry = {
        "id": sid,
        "name": payload.get("name", "Sans nom"),
        "type": payload.get("type", "nocodb"),
        "enabled": payload.get("enabled", True),
        "config": payload.get("config", {}),
    }
    sources.append(entry)
    _save_sources(sources)
    return {"id": entry["id"], "name": entry["name"], "type": entry["type"], "enabled": entry["enabled"], "config": entry["config"]}


def update_source(source_id: str, payload: dict) -> dict | None:
    """Met à jour une source (fusion partielle de config)."""
    sources = _load_sources()
    for i, s in enumerate(sources):
        if s.get("id") == source_id:
            if "name" in payload and payload["name"] is not None:
                sources[i]["name"] = payload["name"]
            if "enabled" in payload and payload["enabled"] is not None:
                sources[i]["enabled"] = payload["enabled"]
            if "config" in payload and payload["config"] is not None:
                existing = dict(sources[i].get("config", {}))
                existing.update(payload["config"])
                sources[i]["config"] = existing
            _save_sources(sources)
            return {**sources[i], "config": _mask_secrets(sources[i].get("config", {}))}
    return None


def delete_source(source_id: str) -> bool:
    """Supprime une source."""
    sources = [s for s in _load_sources() if s.get("id") != source_id]
    if len(sources) == len(_load_sources()):
        return False
    _save_sources(sources)
    return True


def _resolve_collection_id(template: str, record: dict) -> str:
    """Remplace {{champ}} dans template par les valeurs du record."""
    result = template
    for key, value in record.items():
        if isinstance(value, (str, int, float)):
            result = result.replace("{{" + str(key) + "}}", str(value))
    result = re.sub(r"\ \{\{[^}]+\}\}", "", result)
    result = _slug(result) or "default"
    return result


async def sync_nocodb_source(source_id: str) -> dict:
    """
    Synchronise une source NocoDB : récupère les enregistrements, assure les collections,
    indexe chaque document via l'endpoint d'indexation (appel interne).
    """
    source = get_source(source_id)
    if not source:
        return {"ok": False, "error": "Source non trouvée", "indexed": 0}
    if source.get("type") != "nocodb":
        return {"ok": False, "error": "Type de source non supporté pour sync", "indexed": 0}
    config = source.get("config", {})
    base_url = (config.get("base_url") or "").rstrip("/")
    api_key = config.get("api_key") or ""
    table_id = config.get("table_id") or ""
    collection_id_tpl = config.get("collection_id") or "nocodb-documents"
    field_mapping = config.get("field_mapping") or {}
    limit = int(config.get("limit", 100))
    file_url_key = field_mapping.get("file_url") or "file_url"
    if not base_url or not table_id:
        return {"ok": False, "error": "base_url et table_id requis", "indexed": 0}

    headers = {}
    if api_key:
        headers["xc-token"] = api_key
    url = f"{base_url}/api/v2/tables/{table_id}/records"
    params = {"limit": limit}

    try:
        async with httpx.AsyncClient(timeout=60.0) as client:
            r = await client.get(url, headers=headers, params=params)
            r.raise_for_status()
            data = r.json()
    except httpx.HTTPStatusError as e:
        return {"ok": False, "error": f"NocoDB API: {e.response.status_code}", "indexed": 0}
    except Exception as e:
        return {"ok": False, "error": str(e), "indexed": 0}

    list_key = "list" if "list" in data else "records"
    records = data.get(list_key, data) if isinstance(data, dict) else []
    if not isinstance(records, list):
        records = []

    from app.services.vector_store_service import add_documents
    from app.services.extraction import extract_text

    indexed_total = 0
    errors = []
    for rec in records:
        row = rec if isinstance(rec, dict) else getattr(rec, "__dict__", {})
        file_url = row.get(file_url_key) or row.get("file_url") or row.get("Attachment") or row.get("attachment_url")
        if not file_url:
            continue
        try:
            coll_id = _resolve_collection_id(collection_id_tpl, row)
            existing = {c["id"] for c in list_collections()}
            if coll_id not in existing:
                create_collection(coll_id)
            meta = {}
            for our_key, nocodb_key in field_mapping.items():
                if our_key in ("file_url",):
                    continue
                val = row.get(nocodb_key)
                if val is not None and our_key in (
                    "document_id", "nocodb_record_id", "nocodb_table_name", "nocodb_base_id",
                    "affaire_id", "numero_affaire", "folder_path",
                ):
                    meta[our_key] = str(val)
            doc_id = meta.get("document_id") or str(row.get("id", row.get("Id", "")))
            try:
                async with httpx.AsyncClient(follow_redirects=True, timeout=60.0) as c2:
                    r2 = await c2.get(file_url)
                    r2.raise_for_status()
                    content = r2.content
                    fn = (file_url or "").split("/")[-1] or "document"
                    cd = r2.headers.get("content-disposition") or ""
                    if "filename=" in cd:
                        m = re.search(r'filename\*?=(?:UTF-8\'?\')?["\']?([^"\';\s]+)', cd, re.I)
                        if not m:
                            m = re.search(r'filename=["\']?([^"\';\s]+)', cd, re.I)
                        if m:
                            fn = m.group(1).strip()
                    if not fn or fn == "download" or "." not in fn:
                        src_key = field_mapping.get("source_file") or field_mapping.get("filename")
                        if src_key and row.get(src_key):
                            fn = str(row.get(src_key)).strip()
                    if not fn or "." not in fn:
                        fn = fn or "document"
                text = extract_text(content, filename=fn)
            except Exception as e1:
                errors.append(f"Record {doc_id}: {e1}")
                continue
            if not text:
                continue
            n = add_documents(
                coll_id,
                [text],
                document_id=doc_id,
                source_file=fn,
                file_url=file_url,
                metadata_per_doc=meta or None,
                deduplicate=True,
            )
            indexed_total += n
        except Exception as e2:
            errors.append(str(e2))

    return {
        "ok": True,
        "indexed": indexed_total,
        "records_fetched": len(records),
        "errors": errors[:10],
    }


# --- SharePoint (Microsoft Graph) ---

GRAPH_BASE = "https://graph.microsoft.com/v1.0"
GRAPH_SCOPE = "https://graph.microsoft.com/.default"
SUPPORTED_EXTENSIONS = {".pdf", ".docx", ".xlsx", ".pptx", ".png", ".jpg", ".jpeg", ".gif", ".txt"}


async def _get_graph_token(tenant_id: str, client_id: str, client_secret: str) -> str:
    """Obtient un token d'accès Microsoft Graph (client credentials)."""
    url = f"https://login.microsoftonline.com/{tenant_id}/oauth2/v2.0/token"
    async with httpx.AsyncClient(timeout=30.0) as client:
        r = await client.post(
            url,
            data={
                "grant_type": "client_credentials",
                "client_id": client_id,
                "client_secret": client_secret,
                "scope": GRAPH_SCOPE,
            },
            headers={"Content-Type": "application/x-www-form-urlencoded"},
        )
        r.raise_for_status()
        return r.json()["access_token"]


def _parse_site_url(site_url: str) -> tuple[str, str]:
    """Extrait hostname et chemin serveur depuis l'URL du site (ex. https://contoso.sharepoint.com/sites/MySite)."""
    from urllib.parse import urlparse, quote
    parsed = urlparse(site_url.rstrip("/"))
    hostname = parsed.netloc or ""
    path = (parsed.path or "/").strip()
    if not path.startswith("/"):
        path = "/" + path
    path_encoded = quote(path, safe="/")
    return hostname, path_encoded


async def _graph_get(token: str, path: str, params: dict | None = None) -> dict:
    """GET sur l'API Microsoft Graph."""
    url = f"{GRAPH_BASE}{path}" if path.startswith("/") else f"{GRAPH_BASE}/{path}"
    async with httpx.AsyncClient(timeout=60.0) as client:
        r = await client.get(url, headers={"Authorization": f"Bearer {token}"}, params=params or {})
        r.raise_for_status()
        return r.json()


async def _list_files_in_folder(
    token: str,
    site_id: str,
    drive_id: str,
    folder_path: str,
    limit: int,
    collected: list[dict],
    prefix: str = "",
) -> None:
    """Liste récursivement les fichiers d'un dossier (Graph API). Remplit collected (max limit)."""
    if len(collected) >= limit:
        return
    path = f"/sites/{site_id}/drive/root:/{folder_path}:/children" if folder_path else f"/sites/{site_id}/drive/root/children"
    params = {"$select": "id,name,file,folder,parentReference,@microsoft.graph.downloadUrl"}
    try:
        data = await _graph_get(token, path, params)
        items = data.get("value", [])
    except Exception:
        items = []
    for item in items:
        if len(collected) >= limit:
            return
        name = item.get("name", "")
        if item.get("folder"):
            sub_path = f"{folder_path}/{name}".strip("/") if folder_path else name
            await _list_files_in_folder(token, site_id, drive_id, sub_path, limit, collected, prefix=f"{prefix}{name}/")
        elif item.get("file"):
            ext = (Path(name).suffix or "").lower()
            if ext in SUPPORTED_EXTENSIONS:
                download_url = item.get("@microsoft.graph.downloadUrl")
                if download_url:
                    collected.append({
                        "id": item.get("id"),
                        "name": name,
                        "download_url": download_url,
                        "folder_path": prefix.rstrip("/"),
                        "drive_id": drive_id,
                        "site_id": site_id,
                    })


async def sync_sharepoint_source(source_id: str) -> dict:
    """
    Synchronise une source SharePoint : récupère les fichiers du site/dossier via Microsoft Graph,
    télécharge chaque fichier supporté, extrait le texte et indexe dans la collection.
    """
    source = get_source(source_id)
    if not source:
        return {"ok": False, "error": "Source non trouvée", "indexed": 0}
    if source.get("type") != "sharepoint":
        return {"ok": False, "error": "Type de source non supporté pour sync", "indexed": 0}
    config = source.get("config", {})
    tenant_id = (config.get("tenant_id") or "").strip()
    client_id = (config.get("client_id") or "").strip()
    client_secret = config.get("client_secret") or ""
    site_url = (config.get("site_url") or "").strip().rstrip("/")
    folder_path = (config.get("folder_path") or "").strip().strip("/")
    collection_id = (config.get("collection_id") or "sharepoint-documents").strip()
    limit = int(config.get("limit", 200))
    if not all([tenant_id, client_id, client_secret, site_url]):
        return {"ok": False, "error": "tenant_id, client_id, client_secret et site_url requis", "indexed": 0}

    try:
        token = await _get_graph_token(tenant_id, client_id, client_secret)
    except httpx.HTTPStatusError as e:
        return {"ok": False, "error": f"Graph auth: {e.response.status_code}", "indexed": 0}
    except Exception as e:
        return {"ok": False, "error": str(e), "indexed": 0}

    hostname, server_path = _parse_site_url(site_url)
    if not hostname:
        return {"ok": False, "error": "site_url invalide", "indexed": 0}
    try:
        site_res = await _graph_get(token, f"/sites/{hostname}:{server_path}")
        site_id = site_res.get("id")
        drive_id = site_res.get("drive", {}).get("id")
        if not drive_id:
            drive_res = await _graph_get(token, f"/sites/{site_id}/drive")
            drive_id = drive_res.get("id")
    except Exception as e:
        return {"ok": False, "error": f"Site/Drive: {e}", "indexed": 0}
    if not site_id or not drive_id:
        return {"ok": False, "error": "Impossible de résoudre le site ou le drive", "indexed": 0}

    files: list[dict] = []
    await _list_files_in_folder(token, site_id, drive_id, folder_path, limit, files)

    from app.services.vector_store_service import add_documents
    from app.services.extraction import extract_text

    existing = {c["id"] for c in list_collections()}
    if collection_id not in existing:
        create_collection(collection_id)

    indexed_total = 0
    errors = []
    for f in files:
        try:
            async with httpx.AsyncClient(follow_redirects=True, timeout=90.0) as client:
                r = await client.get(f["download_url"])
                r.raise_for_status()
                content = r.content
            fn = f.get("name", "document")
            text = extract_text(content, filename=fn)
            if not text:
                continue
            meta = {
                "sharepoint_item_id": f.get("id"),
                "drive_id": f.get("drive_id"),
                "site_id": f.get("site_id"),
                "folder_path": f.get("folder_path", ""),
            }
            doc_id = f.get("id") or fn
            n = add_documents(
                collection_id,
                [text],
                document_id=doc_id,
                source_file=fn,
                file_url="",
                metadata_per_doc=meta,
                deduplicate=True,
            )
            indexed_total += n
        except Exception as e1:
            errors.append(f"{f.get('name', '?')}: {e1}")

    return {
        "ok": True,
        "indexed": indexed_total,
        "files_fetched": len(files),
        "errors": errors[:10],
    }
