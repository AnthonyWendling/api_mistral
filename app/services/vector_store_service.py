import hashlib
import re
from datetime import datetime, timezone

import chromadb
from chromadb.config import Settings as ChromaSettings

from app.config import settings
from app.services.embedding_service import embed_texts, embed_query


def _slug(name: str) -> str:
    return re.sub(r"[^a-z0-9_-]", "-", name.lower()).strip("-") or "default"


def get_client() -> chromadb.PersistentClient:
    return chromadb.PersistentClient(
        path=settings.chroma_data_path,
        settings=ChromaSettings(anonymized_telemetry=False),
    )


def create_collection(name: str) -> str:
    client = get_client()
    id_ = _slug(name)
    client.get_or_create_collection(name=id_, metadata={"name": name})
    return id_


def list_collections() -> list[dict]:
    client = get_client()
    return [
        {"id": c.name, "name": c.metadata.get("name", c.name)}
        for c in client.list_collections()
    ]


def delete_collection(collection_id: str) -> None:
    """Supprime une collection et tout son contenu."""
    client = get_client()
    client.delete_collection(name=collection_id)


def delete_document(collection_id: str, document_id: str) -> None:
    """Supprime tous les chunks d'un document dans une collection."""
    coll = get_collection(collection_id)
    coll.delete(where={"document_id": document_id})


def get_collection(collection_id: str):
    client = get_client()
    return client.get_collection(name=collection_id)


def _chunk_text(text: str, chunk_size: int | None = None, overlap: int | None = None) -> list[str]:
    size = chunk_size or settings.chunk_size
    over = overlap or settings.chunk_overlap
    chunks = []
    start = 0
    while start < len(text):
        end = start + size
        chunk = text[start:end]
        if not chunk.strip():
            start = end - over
            continue
        chunks.append(chunk)
        start = end - over
    return chunks


def _content_hash(content: str) -> str:
    return hashlib.sha256(content.encode("utf-8")).hexdigest()[:16]


def add_documents(
    collection_id: str,
    texts: list[str],
    metadata_per_doc: dict | None = None,
    document_id: str | None = None,
    source_file: str = "",
    file_url: str = "",
    deduplicate: bool = True,
) -> int:
    coll = get_collection(collection_id)
    meta = metadata_per_doc or {}
    now = datetime.now(timezone.utc).isoformat()
    doc_id = document_id or _content_hash((source_file or "") + (file_url or "") + str(texts))

    if deduplicate:
        existing = coll.get(where={"document_id": doc_id}, include=[])
        if existing and existing["ids"]:
            return 0

    chunks = []
    for t in texts:
        chunks.extend(_chunk_text(t))

    if not chunks:
        return 0

    embeddings = embed_texts(chunks)
    ids = [f"{doc_id}_{i}" for i in range(len(chunks))]
    metadatas = [
        {
            **meta,
            "source_file": source_file,
            "file_url": file_url,
            "index": i,
            "date": now,
            "document_id": doc_id,
        }
        for i in range(len(chunks))
    ]
    coll.add(ids=ids, embeddings=embeddings, documents=chunks, metadatas=metadatas)
    return len(chunks)


def list_documents(collection_id: str, limit_chunks: int = 2000) -> list[dict]:
    """Liste les documents uniques de la collection (document_id, source_file, file_url)."""
    coll = get_collection(collection_id)
    # Récupérer un échantillon de chunks pour extraire les métadonnées document
    try:
        result = coll.get(include=["metadatas"], limit=min(limit_chunks, 5000))
    except TypeError:
        result = coll.get(include=["metadatas"])
    if not result or not result.get("metadatas"):
        return []
    seen = set()
    docs = []
    for meta in result["metadatas"]:
        if not meta:
            continue
        doc_id = meta.get("document_id") or meta.get("source_file") or ""
        if not doc_id or doc_id in seen:
            continue
        seen.add(doc_id)
        doc = {
            "document_id": doc_id,
            "source_file": meta.get("source_file", ""),
            "file_url": meta.get("file_url", ""),
            "date": meta.get("date", ""),
        }
        if meta.get("folder_path"):
            doc["folder_path"] = meta["folder_path"]
        if meta.get("sharepoint_item_id"):
            doc["sharepoint_item_id"] = meta["sharepoint_item_id"]
        if meta.get("drive_id"):
            doc["drive_id"] = meta["drive_id"]
        if meta.get("site_id"):
            doc["site_id"] = meta["site_id"]
        if meta.get("nocodb_record_id"):
            doc["nocodb_record_id"] = meta["nocodb_record_id"]
        if meta.get("nocodb_table_name"):
            doc["nocodb_table_name"] = meta["nocodb_table_name"]
        if meta.get("nocodb_base_id"):
            doc["nocodb_base_id"] = meta["nocodb_base_id"]
        if meta.get("affaire_id"):
            doc["affaire_id"] = meta["affaire_id"]
        if meta.get("numero_affaire"):
            doc["numero_affaire"] = meta["numero_affaire"]
        docs.append(doc)
    return docs


def search(collection_id: str, query: str, top_k: int = 10) -> list[dict]:
    coll = get_collection(collection_id)
    q_embed = embed_query(query)
    result = coll.query(query_embeddings=[q_embed], n_results=top_k, include=["documents", "metadatas", "distances"])
    out = []
    if result["ids"] and result["ids"][0]:
        for i, id_ in enumerate(result["ids"][0]):
            out.append({
                "chunk_id": id_,
                "text": result["documents"][0][i] if result["documents"] else "",
                "metadata": (result["metadatas"][0][i] or {}) if result["metadatas"] else {},
                "distance": result["distances"][0][i] if result.get("distances") and result["distances"][0] else None,
            })
    return out
