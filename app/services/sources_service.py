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


def list_sources() -> list[dict]:
    """Liste toutes les sources (sans exposer les clés API en clair dans les configs sensibles)."""
    raw = _load_sources()
    out = []
    for s in raw:
        cfg = dict(s.get("config", {}))
        if cfg.get("api_key"):
            cfg["api_key"] = "********"
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
            return {**sources[i], "config": {k: "********" if k == "api_key" and v else v for k, v in sources[i]["config"].items()}}
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
