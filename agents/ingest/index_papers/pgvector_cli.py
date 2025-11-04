"""
Pgvector helpers colocated with Module 2 (agents.ingest.index_papers).
"""
from __future__ import annotations
import argparse
import gzip
import json
import os
from pathlib import Path
import hashlib
from typing import Any, Dict, Iterable, List, Tuple
import sys
import time
import typing as T

import psycopg2
import psycopg2.extras

def _conn():
    url = os.getenv("DATABASE_URL")
    if not url:
        raise SystemExit("Set DATABASE_URL")
    return psycopg2.connect(url)

def _iter_jsonl(path: Path):
    opener = gzip.open if str(path).endswith(".gz") else open
    with opener(path, "rt", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                yield json.loads(line)

def _exec(cur, sql: str, params=None):
    cur.execute(sql, params or ())

def _synthesize_ids(row: Dict[str, Any]) -> Tuple[str, str]:
    """Return (chunk_id, paper_id) synthesizing if missing.
    paper_id defaults to f"pmid_{pmid}" when pmid is present.
    chunk_id is sha1 of (paper_id, section_norm, start, end, text_prefix).
    """
    paper_id = str(row.get("paper_id") or "").strip()
    pmid = str(row.get("pmid") or "").strip()
    if not paper_id and pmid:
        paper_id = f"pmid_{pmid}"
    section_norm = str(row.get("section_norm") or row.get("section") or "other")
    start = row.get("start") if isinstance(row.get("start"), int) else 0
    end = row.get("end") if isinstance(row.get("end"), int) else 0
    txt = (row.get("text") or "")
    text_prefix = txt[:64]
    chunk_id = str(row.get("chunk_id") or "").strip()
    if not chunk_id:
        h = hashlib.sha1()
        h.update((paper_id or "").encode("utf-8"))
        h.update(b"|")
        h.update(section_norm.encode("utf-8"))
        h.update(b"|")
        h.update(str(start).encode("utf-8"))
        h.update(b"|")
        h.update(str(end).encode("utf-8"))
        h.update(b"|")
        h.update(text_prefix.encode("utf-8"))
        chunk_id = f"{paper_id}#" + h.hexdigest()[:16]
    return chunk_id, paper_id

def load_chunks(args: argparse.Namespace):
    # Allow explicit --chunks path; otherwise auto-detect default jsonl(.gz)
    if getattr(args, "chunks", None):
        chunks_path = Path(args.chunks)
        if not chunks_path.exists() and str(chunks_path).endswith(".jsonl") and Path(str(chunks_path) + ".gz").exists():
            chunks_path = Path(str(chunks_path) + ".gz")
    else:
        chunks_path = Path("data/index/chunks.jsonl")
        if not chunks_path.exists() and Path("data/index/chunks.jsonl.gz").exists():
            chunks_path = Path("data/index/chunks.jsonl.gz")
    if not chunks_path.exists():
        raise SystemExit("chunks file not found. Provide --chunks or generate data/index/chunks.jsonl(.gz).")
    rows = []
    for row in _iter_jsonl(chunks_path):
        ck_id, paper_id = _synthesize_ids(row)
        # Normalize booleans safely
        is_results = bool(row.get("is_results")) if row.get("is_results") is not None else None
        is_methods = bool(row.get("is_methods")) if row.get("is_methods") is not None else None
        rows.append((
            ck_id, paper_id,
            row.get("pmid"),
            row.get("title"), row.get("journal"), row.get("year"),
            row.get("study_type"), row.get("primary_goal"),
            row.get("supplements") or [],
            row.get("section"), row.get("section_norm"), row.get("section_priority"),
            is_results, is_methods,
            row.get("passage_id"), row.get("start"), row.get("end"),
            row.get("text")
        ))
        if len(rows) >= 5000:
            _bulk_upsert_chunks(rows); rows.clear()
    if rows:
        _bulk_upsert_chunks(rows)
    print("✅ load-chunks complete")
    # Auto backfill canonical metadata unless disabled
    if not getattr(args, "no_backfill", False):
        try:
            ns = argparse.Namespace(canonical=getattr(args, "canonical", None))
            backfill_meta(ns)
        except SystemExit as e:
            # Missing canonical file should not fail the load step; just warn
            try:
                print(f"⚠️  backfill-meta skipped: {e}")
            except Exception:
                pass

def _bulk_upsert_chunks(rows: List[Tuple]):
    sql = """
    CREATE TABLE IF NOT EXISTS public.ef_chunks (
        chunk_id TEXT PRIMARY KEY,
        paper_id TEXT NOT NULL,
        pmid     TEXT,
        title    TEXT,
        journal  TEXT,
        year     INTEGER,
        study_type TEXT,
        primary_goal TEXT,
        supplements TEXT[],
        section  TEXT,
        section_norm TEXT,
        section_priority INTEGER,
        is_results BOOLEAN,
        is_methods BOOLEAN,
        passage_id TEXT,
        start    INTEGER,
        "end"    INTEGER,
        text     TEXT
    );

    INSERT INTO ef_chunks(
        chunk_id,paper_id,pmid,
        title,journal,year,study_type,primary_goal,supplements,
        section,section_norm,section_priority,is_results,is_methods,passage_id,start,"end",text)
    VALUES %s
    ON CONFLICT (chunk_id) DO UPDATE SET
      paper_id=EXCLUDED.paper_id, pmid=EXCLUDED.pmid,
      title=EXCLUDED.title, journal=EXCLUDED.journal, year=EXCLUDED.year,
      study_type=EXCLUDED.study_type, primary_goal=EXCLUDED.primary_goal, supplements=EXCLUDED.supplements,
      section=EXCLUDED.section, section_norm=EXCLUDED.section_norm, section_priority=EXCLUDED.section_priority,
      is_results=EXCLUDED.is_results, is_methods=EXCLUDED.is_methods,
      passage_id=EXCLUDED.passage_id, start=EXCLUDED.start, "end"=EXCLUDED."end", text=EXCLUDED.text
    """
    with _conn() as cx, cx.cursor() as cur:
        # Run the DDL first (safe if exists), then upsert
        cur.execute(sql.split(";\n\n")[0] + ";")
        # Ensure all expected columns exist (handles older minimal schemas)
        try:
            cur.execute("""
                SELECT column_name FROM information_schema.columns
                WHERE table_schema='public' AND table_name='ef_chunks'
            """)
            existing = {r[0] for r in cur.fetchall()}
            # Map: logical name -> (rendered name, type)
            required = {
                "chunk_id": ("chunk_id", "TEXT"),
                "paper_id": ("paper_id", "TEXT"),
                "pmid": ("pmid", "TEXT"),
                "title": ("title", "TEXT"),
                "journal": ("journal", "TEXT"),
                "year": ("year", "INTEGER"),
                "study_type": ("study_type", "TEXT"),
                "primary_goal": ("primary_goal", "TEXT"),
                "supplements": ("supplements", "TEXT[]"),
                "section": ("section", "TEXT"),
                "section_norm": ("section_norm", "TEXT"),
                "section_priority": ("section_priority", "INTEGER"),
                "is_results": ("is_results", "BOOLEAN"),
                "is_methods": ("is_methods", "BOOLEAN"),
                "passage_id": ("passage_id", "TEXT"),
                "start": ("start", "INTEGER"),
                "end": ('"end"', "INTEGER"),
                "text": ("text", "TEXT"),
            }
            missing = [k for k in required.keys() if k not in existing]
            for k in missing:
                col_name, col_type = required[k]
                cur.execute(f"ALTER TABLE public.ef_chunks ADD COLUMN IF NOT EXISTS {col_name} {col_type}")
        except Exception:
            # best-effort; continue to upsert
            pass
        # Deduplicate by chunk_id within this batch to avoid ON CONFLICT affecting a row twice
        unique_by_id = {}
        for r in rows:
            unique_by_id[r[0]] = r  # keep last occurrence
        deduped_rows = list(unique_by_id.values())
        upsert_sql = ";\n\n".join(sql.split(";\n\n")[1:])
        psycopg2.extras.execute_values(cur, upsert_sql, deduped_rows, page_size=1000)
        cx.commit()

def _get_model_and_tokenizer(model_name: str | None):
    from sentence_transformers import SentenceTransformer
    model = SentenceTransformer(model_name or os.getenv("EMBEDDING_MODEL", "intfloat/e5-base-v2"))
    dim = len(model.encode(["dim_probe"])[0])
    return model, dim

def _iter_texts_to_embed(cur, limit: int | None = None):
    sql = """
      SELECT c.chunk_id, c.text
      FROM ef_chunks c
      LEFT JOIN ef_chunk_embeddings e ON e.chunk_id = c.chunk_id
      WHERE e.chunk_id IS NULL AND c.text IS NOT NULL AND c.text <> ''
    """
    if limit:
        sql += f" LIMIT {int(limit)}"
    cur.execute(sql)
    for chunk_id, text in cur:
        yield chunk_id, text

def embed(args: argparse.Namespace):
    model, dim = _get_model_and_tokenizer(args.model)
    with _conn() as cx, cx.cursor() as cur:
        # Ensure extension and embeddings table exist
        try:
            cur.execute("CREATE EXTENSION IF NOT EXISTS vector;")
            cur.execute("""
                CREATE TABLE IF NOT EXISTS ef_chunk_embeddings (
                    chunk_id   TEXT PRIMARY KEY REFERENCES ef_chunks(chunk_id) ON DELETE CASCADE,
                    embedding  vector(768)
                )
            """)
            cx.commit()
        except Exception:
            pass
        cur.execute("SELECT atttypmod-4 FROM pg_attribute WHERE attrelid = 'ef_chunk_embeddings'::regclass AND attname='embedding'")
        current = cur.fetchone()
        current_dim = current[0] if current else None
        if current_dim != dim:
            print(f"Resizing embedding dim {current_dim} -> {dim}")
            cur.execute(f"ALTER TABLE ef_chunk_embeddings ALTER COLUMN embedding TYPE vector({dim})")
            cx.commit()
    batch = int(os.getenv("BATCH_SIZE", "64"))
    todo: List[Tuple[str, str]] = []
    with _conn() as cx, cx.cursor() as cur:
        for chunk_id, text in _iter_texts_to_embed(cur, limit=args.limit):
            todo.append((chunk_id, text))
            if len(todo) >= batch:
                _embed_batch(model, todo); todo.clear()
        if todo:
            _embed_batch(model, todo)
    print("✅ embed complete")

def build_ann(args: argparse.Namespace):
    lists = int(getattr(args, "lists", 200) or 200)
    recreate = bool(getattr(args, "recreate", False))
    with _conn() as cx, cx.cursor() as cur:
        cur.execute("CREATE EXTENSION IF NOT EXISTS vector;")
        if recreate:
            cur.execute("DROP INDEX IF EXISTS ef_chunk_embeddings_ivfflat_cos")
        cur.execute(
            f"""
            CREATE INDEX IF NOT EXISTS ef_chunk_embeddings_ivfflat_cos
            ON ef_chunk_embeddings
            USING ivfflat (embedding vector_cosine_ops)
            WITH (lists = {lists})
            """
        )
        cx.commit()
    print("✅ build-ann complete")

def analyze(args: argparse.Namespace):
    with _conn() as cx, cx.cursor() as cur:
        cur.execute("ANALYZE ef_chunk_embeddings;")
        cx.commit()
    print("✅ analyze complete")

def backfill_meta(args: argparse.Namespace):
    # Populate missing metadata in ef_chunks from canonical_papers.jsonl(.gz)
    canonical_path = Path(getattr(args, "canonical", None) or "data/index/canonical_papers.jsonl")
    if not canonical_path.exists() and Path(str(canonical_path) + ".gz").exists():
        canonical_path = Path(str(canonical_path) + ".gz")
    if not canonical_path.exists():
        raise SystemExit(f"canonical file not found: {canonical_path}")

    rows: List[Tuple[str, Any, Any, Any, Any, Any, List[str]]] = []
    for obj in _iter_jsonl(canonical_path):
        pmid = str(obj.get("pmid") or "").strip()
        if not pmid:
            continue
        title = obj.get("title")
        journal = obj.get("journal")
        year = obj.get("year")
        study_type = obj.get("study_type")
        primary_goal = obj.get("primary_goal")
        supplements = obj.get("supplements") or []
        try:
            supplements = list(supplements)
        except Exception:
            supplements = []
        rows.append((pmid, title, journal, year, study_type, primary_goal, supplements))

    if not rows:
        print("No rows to backfill from canonical; exiting")
        return

    with _conn() as cx, cx.cursor() as cur:
        cur.execute("DROP TABLE IF EXISTS tmp_canonical_meta;")
        cur.execute(
            """
            CREATE TEMP TABLE tmp_canonical_meta (
                pmid TEXT PRIMARY KEY,
                title TEXT,
                journal TEXT,
                year INTEGER,
                study_type TEXT,
                primary_goal TEXT,
                supplements TEXT[]
            ) ON COMMIT DROP
            """
        )
        psycopg2.extras.execute_values(
            cur,
            "INSERT INTO tmp_canonical_meta(pmid,title,journal,year,study_type,primary_goal,supplements) VALUES %s",
            rows,
            page_size=2000,
        )
        cur.execute(
            """
            UPDATE ef_chunks c
            SET
              title = COALESCE(c.title, m.title),
              journal = COALESCE(c.journal, m.journal),
              year = COALESCE(c.year, m.year),
              study_type = COALESCE(c.study_type, m.study_type),
              primary_goal = COALESCE(c.primary_goal, m.primary_goal),
              supplements = CASE
                 WHEN c.supplements IS NULL OR array_length(c.supplements, 1) IS NULL OR array_length(c.supplements,1)=0
                 THEN m.supplements
                 ELSE c.supplements
              END
            FROM tmp_canonical_meta m
            WHERE c.pmid = m.pmid
            """
        )
        cx.commit()
    print("✅ backfill-meta complete")

def _embed_batch(model, pairs: List[Tuple[str, str]]):
    ids, texts = zip(*pairs)
    vecs = model.encode(list(texts), normalize_embeddings=True, show_progress_bar=False)
    # Ensure vectors are native Python floats (not numpy float32) for psycopg2 adaptation
    rows: List[Tuple[str, List[float]]] = []
    for i in range(len(ids)):
        v = vecs[i]
        try:
            py_list = [float(x) for x in v.tolist()]  # works if v is a numpy array
        except Exception:
            py_list = [float(x) for x in v]  # fallback if already list-like
        rows.append((ids[i], py_list))
    sql = "INSERT INTO ef_chunk_embeddings(chunk_id, embedding) VALUES %s ON CONFLICT (chunk_id) DO UPDATE SET embedding=EXCLUDED.embedding"
    with _conn() as cx, cx.cursor() as cur:
        psycopg2.extras.execute_values(cur, sql, rows, template="(%s, %s::vector)", page_size=500)
        cx.commit()

def search(args: argparse.Namespace):
    from sentence_transformers import SentenceTransformer
    q = args.q.strip()
    k = int(args.k)
    model_id = os.getenv("EMBEDDING_MODEL", "intfloat/e5-base-v2")
    model = SentenceTransformer(model_id)
    # e5-style query prefix improves relevance substantially
    q_vec = model.encode([f"query: {q}"], normalize_embeddings=True)[0].tolist()

    supp = (getattr(args, "supp", None) or "").strip().lower()
    supp_mode = (getattr(args, "supp_mode", None) or "meta").strip().lower()

    # Tiny scoring bonuses (lower distance is better)
    results_boost = float(os.getenv("RESULTS_BOOST_EPS", "0.02")) if getattr(args, "results_first", False) else 0.0
    meta_bonus    = float(os.getenv("SUPP_META_BONUS", "0.02"))
    text_bonus    = float(os.getenv("SUPP_TEXT_BONUS", "0.01"))

    # Match expressions
    meta_match_sql = "EXISTS (SELECT 1 FROM unnest(c.supplements) s WHERE lower(s) = %s OR lower(s) LIKE %s)"
    text_match_sql = "(to_tsvector('english', lower(c.title)) @@ plainto_tsquery('english', %s) OR ((lower(c.section) LIKE 'results%%' OR lower(c.section) LIKE 'abstract%%') AND to_tsvector('english', lower(c.text)) @@ plainto_tsquery('english', %s)))"

    # Score expression: distance minus tiny bonuses when conditions hold
    score_expr = "(e.embedding <-> %s::vector)"
    score_params: List[Any] = [q_vec]
    if results_boost > 0:
        # Approximate results-section using section name since ef_chunks has no boolean flag
        score_expr += " - (CASE WHEN lower(c.section) LIKE 'results%%' THEN %s ELSE 0 END)"
        score_params.append(results_boost)
    if supp:
        score_expr += " - (CASE WHEN " + meta_match_sql + " THEN %s ELSE 0 END)" \
                      + " - (CASE WHEN " + text_match_sql + " THEN %s ELSE 0 END)"
        # meta condition params (two), then meta bonus value
        score_params.extend([supp, f"%{supp}%"])  # for meta_match_sql
        score_params.append(meta_bonus)
        # text condition params (two), then text bonus value
        score_params.extend([supp, supp])          # for text_match_sql
        score_params.append(text_bonus)

    # Optional WHERE clause
    where_sql = ""
    where_params: List[Any] = []
    if supp:
        if supp_mode == "meta":
            where_sql = "WHERE " + meta_match_sql
            where_params.extend([supp, f"%{supp}%"])
        elif supp_mode == "text":
            where_sql = "WHERE " + text_match_sql
            where_params.extend([supp, supp])
        else:  # both
            where_sql = "WHERE (" + meta_match_sql + " OR " + text_match_sql + ")"
            where_params.extend([supp, f"%{supp}%", supp, supp])

    sql = f"""
    SELECT c.paper_id, c.title, c.journal, c.year, c.study_type, c.primary_goal,
           c.section, e.chunk_id, {score_expr} AS score
    FROM ef_chunk_embeddings e
    JOIN ef_chunks c ON c.chunk_id = e.chunk_id
    {where_sql}
    ORDER BY score
    LIMIT %s
    """
    params = tuple(score_params + where_params + [k])

    with _conn() as cx, cx.cursor() as cur:
        cur.execute(sql, params)
        rows = cur.fetchall()
    for r in rows:
        # 0 paper_id, 1 title, 2 journal, 3 year, 4 study_type, 5 primary_goal, 6 section, 7 chunk_id, 8 score
        paper_id, title, journal, year, study_type, primary_goal, section, chunk_id, score = r
        try:
            score_f = float(score)
        except Exception:
            score_f = score
        print(f"{chunk_id:<28}  score={score_f:0.3f}  [{year} {study_type}]  {title}")

def main():
    ap = argparse.ArgumentParser(prog="index_papers_pgvector", description="Embeddings + Postgres (pgvector)")
    sub = ap.add_subparsers(dest="cmd", required=True)

    p1 = sub.add_parser("load-chunks")
    p1.add_argument("--chunks", type=str, default=None)
    p1.add_argument("--no-backfill", action="store_true", help="Skip canonical metadata backfill")
    p1.add_argument("--canonical", type=str, default=None, help="Path to canonical_papers.jsonl(.gz)")
    p1.set_defaults(func=load_chunks)

    p2 = sub.add_parser("embed")
    p2.add_argument("--limit", type=int, default=None)
    p2.add_argument("--model", type=str, default=None)
    p2.set_defaults(func=embed)

    p3 = sub.add_parser("search")
    p3.add_argument("--q", type=str, required=True)
    p3.add_argument("-k", type=int, default=10)
    p3.add_argument("--supp", type=str, default=None, help="Optional supplement filter, e.g., creatine")
    p3.add_argument("--results-first", action="store_true", help="Slightly boost Results-section chunks")
    p3.set_defaults(func=search)

    p4 = sub.add_parser("build-ann")
    p4.add_argument("--lists", type=int, default=200)
    p4.add_argument("--recreate", action="store_true")
    p4.set_defaults(func=build_ann)

    p5 = sub.add_parser("analyze")
    p5.set_defaults(func=analyze)

    p6 = sub.add_parser("backfill-meta")
    p6.add_argument("--canonical", type=str, default=None, help="Path to canonical_papers.jsonl(.gz)")
    p6.set_defaults(func=backfill_meta)

    args = ap.parse_args()
    args.func(args)

if __name__ == "__main__":
    main()

