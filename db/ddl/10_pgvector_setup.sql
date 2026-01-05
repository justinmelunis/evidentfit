-- Enable pgvector and create minimal tables for EvidentFit chunks + embeddings.
-- Run once: psql "$DATABASE_URL" -f db/ddl/10_pgvector_setup.sql

CREATE EXTENSION IF NOT EXISTS vector;

-- Adjust text columns to your needs; keep it lean for speed.
CREATE TABLE IF NOT EXISTS ef_chunks (
  chunk_id       TEXT PRIMARY KEY,
  paper_id       TEXT NOT NULL,
  title          TEXT,
  journal        TEXT,
  year           INTEGER,
  study_type     TEXT,
  primary_goal   TEXT,
  supplements    TEXT[],          -- from JSON list
  section        TEXT,
  passage_id     TEXT,
  text           TEXT             -- optional; keep for debug / embedding; you can drop later
);

-- Set dimension at runtime via CLI; we'll ALTER COLUMN to the correct dim if needed.
DO $$
BEGIN
  IF NOT EXISTS (SELECT 1 FROM information_schema.columns
                 WHERE table_name='ef_chunk_embeddings' AND column_name='embedding') THEN
    CREATE TABLE ef_chunk_embeddings (
      chunk_id   TEXT PRIMARY KEY REFERENCES ef_chunks(chunk_id) ON DELETE CASCADE,
      embedding  vector(768) -- temporary default; CLI will resize if model dim differs
    );
  END IF;
END$$;

-- Vector index (IVFFLAT) requires a list size and works best after ANALYZE + sufficient rows.
-- We'll (re)create it from the CLI once we know the actual dimension.

-- ---------- Optional but recommended FTS indexes for fast text filtering ----------
-- Speed up title text queries (used by --supp-mode text/both)
CREATE INDEX IF NOT EXISTS ef_chunks_title_fts
  ON ef_chunks
  USING gin (to_tsvector('english', lower(title)));

-- Speed up content text queries restricted to Results/Abstract (the search uses this condition)
CREATE INDEX IF NOT EXISTS ef_chunks_text_fts
  ON ef_chunks
  USING gin (to_tsvector('english', lower(text)));

