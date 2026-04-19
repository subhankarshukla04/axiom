-- AXIOM RAG: pgvector extension + document_chunks table
-- Run: psql $DATABASE_URL -f migrations/add_pgvector.sql

CREATE EXTENSION IF NOT EXISTS vector;

CREATE TABLE IF NOT EXISTS document_chunks (
    id SERIAL PRIMARY KEY,
    company_id INTEGER REFERENCES companies(id) ON DELETE CASCADE,
    ticker TEXT NOT NULL,
    doc_type TEXT NOT NULL DEFAULT '10-K',
    section TEXT,
    filing_date DATE,
    chunk_index INTEGER,
    content TEXT NOT NULL,
    embedding vector(1536),
    metadata JSONB DEFAULT '{}',
    created_at TIMESTAMP DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS document_chunks_ticker_idx
    ON document_chunks(ticker, doc_type);

CREATE INDEX IF NOT EXISTS document_chunks_embedding_idx
    ON document_chunks USING ivfflat (embedding vector_cosine_ops)
    WITH (lists = 100);

COMMENT ON TABLE document_chunks IS 'RAG document chunks for 10-K/10-Q filings with pgvector embeddings';
