"""
AXIOM RAG Service
Retrieval-Augmented Generation using SEC EDGAR 10-K filings + pgvector.
Grounds AI commentary in actual management language from filings.
"""

import json
import logging
import os
import re
import time
import urllib.request
from typing import Optional

import httpx

logger = logging.getLogger(__name__)

_OPENROUTER_BASE = "https://openrouter.ai/api/v1"
_EMBED_MODEL = "openai/text-embedding-3-small"
_EMBED_DIM = 1536
_CHUNK_SIZE = 500
_CHUNK_OVERLAP = 50
_EDGAR_SEARCH = "https://efts.sec.gov/LATEST/search-index"
_EDGAR_FULL_TEXT = "https://efts.sec.gov/LATEST/search-index"
_USER_AGENT = "AXIOM-Platform axiom@example.com"


def _api_key() -> str:
    key = os.environ.get("OPENROUTER_API_KEY", "")
    if not key:
        raise RuntimeError("OPENROUTER_API_KEY not set")
    return key


def _embed(text: str) -> list:
    """Embed text using OpenRouter embedding endpoint."""
    headers = {
        "Authorization": f"Bearer {_api_key()}",
        "Content-Type": "application/json",
    }
    resp = httpx.post(
        f"{_OPENROUTER_BASE}/embeddings",
        headers=headers,
        json={"model": _EMBED_MODEL, "input": text[:8000]},
        timeout=30,
    )
    resp.raise_for_status()
    return resp.json()["data"][0]["embedding"]


def _chunk_text(text: str, size: int = _CHUNK_SIZE, overlap: int = _CHUNK_OVERLAP) -> list:
    """Sliding-window token-approximate chunker (character-based)."""
    # ~4 chars per token
    char_size = size * 4
    char_overlap = overlap * 4
    chunks = []
    start = 0
    while start < len(text):
        end = min(start + char_size, len(text))
        chunk = text[start:end].strip()
        if chunk:
            chunks.append(chunk)
        if end >= len(text):
            break
        start += char_size - char_overlap
    return chunks


def _fetch_edgar_text(ticker: str, form_type: str = "10-K") -> dict:
    """
    Fetch latest 10-K full text from SEC EDGAR full-text search API.
    Returns {section_name: text} for MD&A, Risk Factors, Business.
    """
    try:
        search_url = (
            f"https://efts.sec.gov/LATEST/search-index?q=%22{ticker}%22"
            f"&dateRange=custom&startdt=2022-01-01&forms={form_type}"
        )
        req = urllib.request.Request(search_url, headers={"User-Agent": _USER_AGENT})
        with urllib.request.urlopen(req, timeout=20) as resp:
            data = json.loads(resp.read().decode())

        hits = data.get("hits", {}).get("hits", [])
        if not hits:
            logger.warning(f"No {form_type} filings found for {ticker}")
            return {}

        # Get most recent filing
        latest = hits[0].get("_source", {})
        file_date = latest.get("file_date", "")
        accession = latest.get("accession_no", "")
        cik = latest.get("entity_id", "")

        if not accession or not cik:
            return {}

        # Fetch the full filing index
        acc_clean = accession.replace("-", "")
        index_url = f"https://data.sec.gov/Archives/edgar/data/{cik}/{acc_clean}/{accession}-index.json"
        req = urllib.request.Request(index_url, headers={"User-Agent": _USER_AGENT})
        with urllib.request.urlopen(req, timeout=20) as resp:
            index_data = json.loads(resp.read().decode())

        # Find the main document (htm/html)
        main_doc = None
        for item in index_data.get("directory", {}).get("item", []):
            name = item.get("name", "")
            doc_type = item.get("type", "")
            if doc_type == form_type or (name.endswith(".htm") and "index" not in name.lower()):
                main_doc = name
                break

        if not main_doc:
            return {}

        doc_url = f"https://data.sec.gov/Archives/edgar/data/{cik}/{acc_clean}/{main_doc}"
        req = urllib.request.Request(doc_url, headers={"User-Agent": _USER_AGENT})
        with urllib.request.urlopen(req, timeout=30) as resp:
            raw_html = resp.read().decode("utf-8", errors="ignore")

        return _parse_10k_sections(raw_html, file_date)

    except Exception as e:
        logger.warning(f"EDGAR text fetch failed for {ticker}: {e}")
        return {}


def _parse_10k_sections(html: str, filing_date: str) -> dict:
    """Extract key 10-K sections from HTML. Returns {section: text}."""
    # Strip HTML tags
    text = re.sub(r"<[^>]+>", " ", html)
    text = re.sub(r"\s+", " ", text).strip()

    sections = {}
    section_patterns = {
        "business": r"item\s+1[.\s]+business",
        "risk_factors": r"item\s+1a[.\s]+risk\s+factors",
        "mda": r"item\s+7[.\s]+management.{0,50}discussion",
        "quantitative_risk": r"item\s+7a[.\s]+quantitative",
    }

    text_lower = text.lower()
    found_positions = {}
    for section, pattern in section_patterns.items():
        m = re.search(pattern, text_lower)
        if m:
            found_positions[section] = m.start()

    sorted_sections = sorted(found_positions.items(), key=lambda x: x[1])
    for i, (section, pos) in enumerate(sorted_sections):
        next_pos = sorted_sections[i + 1][1] if i + 1 < len(sorted_sections) else pos + 20000
        content = text[pos: min(pos + 15000, next_pos)].strip()
        if len(content) > 100:
            sections[section] = content

    sections["_filing_date"] = filing_date
    return sections


def _get_pg_conn():
    """Get PostgreSQL connection with pgvector support."""
    from config import Config
    import psycopg2
    conn = psycopg2.connect(Config.get_db_connection_string())
    return conn


def _ensure_schema():
    """Create document_chunks table + pgvector extension if not present."""
    try:
        conn = _get_pg_conn()
        cur = conn.cursor()
        cur.execute("CREATE EXTENSION IF NOT EXISTS vector;")
        cur.execute("""
            CREATE TABLE IF NOT EXISTS document_chunks (
                id SERIAL PRIMARY KEY,
                company_id INTEGER,
                ticker TEXT NOT NULL,
                doc_type TEXT NOT NULL,
                section TEXT,
                filing_date DATE,
                chunk_index INTEGER,
                content TEXT NOT NULL,
                embedding vector(%d),
                metadata JSONB DEFAULT '{}',
                created_at TIMESTAMP DEFAULT NOW()
            );
        """ % _EMBED_DIM)
        cur.execute("""
            CREATE INDEX IF NOT EXISTS document_chunks_ticker_idx 
            ON document_chunks(ticker, doc_type);
        """)
        conn.commit()
        cur.close()
        conn.close()
        logger.info("RAG schema ready")
    except Exception as e:
        logger.warning(f"Could not ensure RAG schema (pgvector may not be installed): {e}")


def ingest_10k(ticker: str, company_id: Optional[int] = None) -> int:
    """
    Fetch 10-K from EDGAR, parse sections, chunk, embed, store in pgvector.
    Returns number of chunks stored.
    """
    _ensure_schema()
    logger.info(f"Ingesting 10-K for {ticker}")

    sections = _fetch_edgar_text(ticker, "10-K")
    if not sections:
        raise ValueError(f"No 10-K text found for {ticker}")

    filing_date = sections.pop("_filing_date", None)
    conn = _get_pg_conn()
    cur = conn.cursor()

    # Remove existing chunks for this ticker/doc_type
    cur.execute(
        "DELETE FROM document_chunks WHERE ticker = %s AND doc_type = '10-K'",
        (ticker,),
    )

    total_chunks = 0
    for section_name, text in sections.items():
        chunks = _chunk_text(text)
        for idx, chunk in enumerate(chunks):
            try:
                embedding = _embed(chunk)
                cur.execute(
                    """INSERT INTO document_chunks
                       (company_id, ticker, doc_type, section, filing_date, chunk_index, content, embedding, metadata)
                       VALUES (%s, %s, '10-K', %s, %s, %s, %s, %s::vector, %s)""",
                    (
                        company_id,
                        ticker,
                        section_name,
                        filing_date,
                        idx,
                        chunk,
                        str(embedding),
                        json.dumps({"section": section_name, "chunk_index": idx}),
                    ),
                )
                total_chunks += 1
                if total_chunks % 10 == 0:
                    conn.commit()  # Commit in batches
            except Exception as e:
                logger.warning(f"Failed to embed chunk {idx} of {section_name}: {e}")
                continue

    conn.commit()
    cur.close()
    conn.close()
    logger.info(f"Ingested {total_chunks} chunks for {ticker}")
    return total_chunks


def retrieve_context(ticker: str, query: str, top_k: int = 5) -> list:
    """
    Embed query, cosine similarity search, return top-k chunks with metadata.
    Returns list of {content, section, score, filing_date}.
    Falls back to empty list if pgvector unavailable.
    """
    try:
        query_embedding = _embed(query)
        conn = _get_pg_conn()
        cur = conn.cursor()
        cur.execute(
            """SELECT content, section, filing_date,
                      1 - (embedding <=> %s::vector) AS score
               FROM document_chunks
               WHERE ticker = %s AND doc_type = '10-K'
               ORDER BY embedding <=> %s::vector
               LIMIT %s""",
            (str(query_embedding), ticker, str(query_embedding), top_k),
        )
        rows = cur.fetchall()
        cur.close()
        conn.close()
        return [
            {
                "content": r[0],
                "section": r[1],
                "filing_date": str(r[2]) if r[2] else None,
                "score": float(r[3]),
            }
            for r in rows
        ]
    except Exception as e:
        logger.warning(f"RAG retrieval failed for {ticker}: {e}")
        return []


def answer_question(ticker: str, question: str) -> dict:
    """
    retrieve_context() → LLM → structured answer with citations.
    Returns {answer, sources, confidence}.
    """
    from services.llm import _call, _ANALYST_SYSTEM

    chunks = retrieve_context(ticker, question)
    if not chunks:
        return {
            "answer": f"No filing text available for {ticker}. Ingest documents first via POST /api/company/<id>/ingest-docs.",
            "sources": [],
            "confidence": "LOW",
        }

    context_text = "\n\n---\n\n".join(
        f"[{c['section'].upper()} | {c.get('filing_date', 'unknown date')}]\n{c['content'][:800]}"
        for c in chunks
    )

    user = f"""Question about {ticker}: {question}

Relevant 10-K excerpts:
{context_text}

Answer the question using only the filing text above. Cite the section name for each claim.
Respond as JSON: {{"answer": "...", "sources": ["Section: ...", ...], "confidence": "HIGH|MEDIUM|LOW"}}"""

    from services.llm import _call_json
    return _call_json(_ANALYST_SYSTEM, user, max_tokens=500)


def list_ingested_docs(ticker: str) -> list:
    """List ingested documents for a ticker. Returns [] if pgvector unavailable."""
    try:
        conn = _get_pg_conn()
        cur = conn.cursor()
        cur.execute(
            """SELECT doc_type, section, filing_date, COUNT(*) as chunk_count
               FROM document_chunks WHERE ticker = %s
               GROUP BY doc_type, section, filing_date
               ORDER BY filing_date DESC""",
            (ticker,),
        )
        rows = cur.fetchall()
        cur.close()
        conn.close()
        return [
            {"doc_type": r[0], "section": r[1], "filing_date": str(r[2]) if r[2] else None, "chunks": r[3]}
            for r in rows
        ]
    except Exception as e:
        logger.warning(f"list_ingested_docs failed: {e}")
        return []
