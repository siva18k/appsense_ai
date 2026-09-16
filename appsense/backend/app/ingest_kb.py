from __future__ import annotations

import re
from pathlib import Path

from pypdf import PdfReader

from . import db as database
from .rag import chunk_text, delete_by_metadata, kb_collection, upsert_chunks

TEXT_FILE_EXTS = {".txt", ".md", ".markdown", ".text", ".log", ".csv"}


def make_summary(body: str, limit: int = 240) -> str:
    text = re.sub(r"\s+", " ", body or "").strip()
    if not text:
        return ""
    if len(text) <= limit:
        return text
    cut = text[:limit].rsplit(" ", 1)[0]
    return f"{cut}…"


def extract_pdf_text(path: Path) -> str:
    reader = PdfReader(str(path))
    pages = []
    for page in reader.pages:
        pages.append(page.extract_text() or "")
    return "\n\n".join(pages).strip()


def extract_upload(path: Path, filename: str) -> tuple[str, str]:
    suffix = Path(filename).suffix.lower()
    if suffix == ".pdf":
        return extract_pdf_text(path), "pdf"
    return path.read_text(encoding="utf-8", errors="replace"), "file"


def index_kb_doc(doc: dict) -> int:
    delete_by_metadata(kb_collection(), {"doc_id": doc["id"]})
    chunks = chunk_text(doc["body"])
    ids = [f"{doc['id']}:{i}" for i in range(len(chunks))]
    metas = [
        {
            "project_id": doc["project_id"],
            "doc_id": doc["id"],
            "title": doc["title"],
            "source_type": doc["source_type"],
            "chunk_index": i,
        }
        for i in range(len(chunks))
    ]
    upsert_chunks(kb_collection(), ids, chunks, metas)
    return len(chunks)


def delete_kb_vectors(doc_id: str) -> None:
    delete_by_metadata(kb_collection(), {"doc_id": doc_id})


def _fetch(doc_id: str, project_id: str | None = None) -> dict | None:
    with database.db() as conn:
        if project_id:
            row = conn.execute(
                "SELECT * FROM kb_docs WHERE id = ? AND project_id = ?",
                (doc_id, project_id),
            ).fetchone()
        else:
            row = conn.execute("SELECT * FROM kb_docs WHERE id = ?", (doc_id,)).fetchone()
    return dict(row) if row else None


def create_text_doc(project_id: str, title: str, body: str) -> dict:
    doc_id = database.new_id()
    created = database.now_iso()
    display = title.strip() or "Untitled"
    summary = make_summary(body)
    with database.db() as conn:
        conn.execute(
            """INSERT INTO kb_docs
               (id, project_id, title, source_type, filename, body, created_at, updated_at, summary)
               VALUES (?, ?, ?, 'text', NULL, ?, ?, ?, ?)""",
            (doc_id, project_id, display, body, created, created, summary),
        )
    doc = _fetch(doc_id)
    assert doc
    index_kb_doc(doc)
    return doc


def create_upload_doc(project_id: str, title: str, filename: str, dest: Path) -> dict:
    body, source_type = extract_upload(dest, filename)
    doc_id = database.new_id()
    created = database.now_iso()
    display = title.strip() or Path(filename).stem
    summary = make_summary(body)
    with database.db() as conn:
        conn.execute(
            """INSERT INTO kb_docs
               (id, project_id, title, source_type, filename, body, created_at, updated_at, summary)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (doc_id, project_id, display, source_type, filename, body, created, created, summary),
        )
    doc = _fetch(doc_id)
    assert doc
    index_kb_doc(doc)
    return doc


def create_pdf_doc(project_id: str, title: str, filename: str, dest: Path) -> dict:
    return create_upload_doc(project_id, title, filename, dest)


def update_text_doc(project_id: str, doc_id: str, title: str, body: str) -> dict:
    existing = _fetch(doc_id, project_id)
    if not existing:
        raise ValueError("Document not found")
    if existing["source_type"] != "text":
        raise ValueError("This document was uploaded as a file; re-upload it instead of editing text.")
    updated = database.now_iso()
    display = title.strip() or existing["title"]
    summary = make_summary(body)
    source_type = "text"
    with database.db() as conn:
        conn.execute(
            """UPDATE kb_docs SET title = ?, body = ?, summary = ?, updated_at = ?, source_type = ?
               WHERE id = ?""",
            (display, body, summary, updated, source_type, doc_id),
        )
    doc = _fetch(doc_id)
    assert doc
    index_kb_doc(doc)
    return doc


def replace_upload_doc(project_id: str, doc_id: str, title: str, filename: str, dest: Path) -> dict:
    existing = _fetch(doc_id, project_id)
    if not existing:
        raise ValueError("Document not found")
    body, source_type = extract_upload(dest, filename)
    updated = database.now_iso()
    display = title.strip() or Path(filename).stem or existing["title"]
    summary = make_summary(body)
    with database.db() as conn:
        conn.execute(
            """UPDATE kb_docs
               SET title = ?, source_type = ?, filename = ?, body = ?, summary = ?, updated_at = ?
               WHERE id = ?""",
            (display, source_type, filename, body, summary, updated, doc_id),
        )
    doc = _fetch(doc_id)
    assert doc
    index_kb_doc(doc)
    return doc


def reindex_project_kb(project_id: str) -> int:
    with database.db() as conn:
        rows = conn.execute(
            "SELECT * FROM kb_docs WHERE project_id = ?", (project_id,)
        ).fetchall()
    total = 0
    for row in rows:
        doc = dict(row)
        if not doc.get("summary"):
            summary = make_summary(doc.get("body") or "")
            with database.db() as conn:
                conn.execute("UPDATE kb_docs SET summary = ? WHERE id = ?", (summary, doc["id"]))
            doc["summary"] = summary
        total += index_kb_doc(doc)
    return total


def upsert_learning_doc(
    project_id: str,
    title: str,
    body: str,
    filename: str,
    existing_id: str | None = None,
) -> dict:
    created = database.now_iso()
    summary = make_summary(body)
    if existing_id:
        existing = _fetch(existing_id, project_id)
        if existing:
            with database.db() as conn:
                conn.execute(
                    """UPDATE kb_docs SET title = ?, body = ?, filename = ?, source_type = 'code_scan',
                       summary = ?, updated_at = ?
                       WHERE id = ?""",
                    (title, body, filename, summary, created, existing_id),
                )
            doc = _fetch(existing_id)
            assert doc
            index_kb_doc(doc)
            return doc
    doc_id = database.new_id()
    with database.db() as conn:
        conn.execute(
            """INSERT INTO kb_docs
               (id, project_id, title, source_type, filename, body, created_at, updated_at, summary)
               VALUES (?, ?, ?, 'code_scan', ?, ?, ?, ?, ?)""",
            (doc_id, project_id, title, filename, body, created, created, summary),
        )
    doc = _fetch(doc_id)
    assert doc
    index_kb_doc(doc)
    return doc
