# Vector DB Setup (PostgreSQL + pgvector)

This project now includes a vector store foundation for retrieval use cases.

## What was added

- Migration:
  - `backend/pipeline/migrations/0008_vector_store_setup.py`
- Sync command:
  - `python manage.py vector_sync`
- Search command:
  - `python manage.py vector_search --q "your query"`

## Table

`ai_vector_documents` (PostgreSQL)

Key columns:

- `doc_type`
- `source_table`, `source_pk` (unique pair)
- `ticker`, `sector`, `geography`, `as_of_date`
- `content`
- `metadata` (jsonb)
- `content_hash`
- `embedding vector(1536)`

Indexes:

- btree: `(doc_type, ticker, as_of_date desc)`
- gin: `metadata`
- ivfflat: `embedding vector_cosine_ops`

## Important prerequisite

Your PostgreSQL server must have pgvector extension binaries installed.

Then inside DB:

```sql
CREATE EXTENSION vector;
```

If pgvector is not installed:

- Migration `0008` will safely no-op.
- `vector_sync` / `vector_search` will show a clear error and exit.

## Sync data into vector store

Example (without embeddings, metadata/content only):

```bash
python manage.py vector_sync --source all --limit 500
```

With embeddings (OpenAI):

```bash
python manage.py vector_sync --source all --limit 500 --embed
```

Recompute embeddings/content updates:

```bash
python manage.py vector_sync --source all --limit 500 --embed --reembed
```

Supported `--source` values:

- `all`
- `news`
- `stock_insights`
- `stock_sentiment`
- `sector_sentiment`

## Semantic search

```bash
python manage.py vector_search --q "top auto stocks sentiment" --k 5
```

Optional filter:

```bash
python manage.py vector_search --q "banking outlook" --doc-type sector_sentiment --k 5
```

## Notes

- This is **vector infrastructure only** (no chatbot wiring).
- For numeric/ranking questions, keep SQL-first querying as primary source of truth.
- Use vector retrieval mainly for semantic context (news/insight text).

