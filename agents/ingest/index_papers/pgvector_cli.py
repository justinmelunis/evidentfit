"""
Pgvector helpers colocated with Module 2 (agents.ingest.index_papers).
"""
from __future__ import annotations
import argparse
import gzip
import json
import os
from pathlib import Path
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

def load_chunks(args: argparse.Namespace):
    chunks_path = Path("data/index/chunks.jsonl")
    if not chunks_path.exists() and Path("data/index/chunks.jsonl.gz").exists():
        chunks_path = Path("data/index/chunks.jsonl.gz")
    if not chunks_path.exists():
        raise SystemExit("data/index/chunks.jsonl(.gz) not found. Run index prep first.")
    rows = []
    for row in _iter_jsonl(chunks_path):
        rows.append((
            row["chunk_id"], row["paper_id"],
            row.get("title"), row.get("journal"), row.get("year"),
            row.get("study_type"), row.get("primary_goal"),
            row.get("supplements") or [],
            row.get("section"), row.get("passage_id"),
            row.get("text")
        ))
        if len(rows) >= 5000:
            _bulk_upsert_chunks(rows); rows.clear()
    if rows:
        _bulk_upsert_chunks(rows)
    print("✅ load-chunks complete")

def _bulk_upsert_chunks(rows: List[Tuple]):
    sql = """
    INSERT INTO ef_chunks(chunk_id,paper_id,title,journal,year,study_type,primary_goal,supplements,section,passage_id,text)
    VALUES %s
    ON CONFLICT (chunk_id) DO UPDATE SET
      paper_id=EXCLUDED.paper_id, title=EXCLUDED.title, journal=EXCLUDED.journal, year=EXCLUDED.year,
      study_type=EXCLUDED.study_type, primary_goal=EXCLUDED.primary_goal, supplements=EXCLUDED.supplements,
      section=EXCLUDED.section, passage_id=EXCLUDED.passage_id, text=EXCLUDED.text
    """
    with _conn() as cx, cx.cursor() as cur:
        psycopg2.extras.execute_values(cur, sql, rows, page_size=1000)
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

    args = ap.parse_args()
    args.func(args)

if __name__ == "__main__":
    main()

