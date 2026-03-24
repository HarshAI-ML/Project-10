from django.core.management.base import BaseCommand, CommandError
from django.db import connection


EMBEDDING_MODEL = "BAAI/bge-small-en-v1.5"


def _vector_literal(values: list[float]) -> str:
    return "[" + ",".join(f"{v:.8f}" for v in values) + "]"


class Command(BaseCommand):
    help = "Run semantic search on ai_vector_documents using pgvector."

    def add_arguments(self, parser):
        parser.add_argument("--q", type=str, required=True, help="Search query text.")
        parser.add_argument("--k", type=int, default=5, help="Top K results.")
        parser.add_argument(
            "--doc-type",
            type=str,
            default=None,
            choices=[None, "news", "stock_insight", "stock_sentiment", "sector_sentiment"],
            help="Optional doc_type filter.",
        )

    def _ensure_postgres(self):
        if connection.vendor != "postgresql":
            raise CommandError("Vector search requires PostgreSQL with pgvector.")
        with connection.cursor() as cursor:
            cursor.execute("SELECT 1 FROM pg_extension WHERE extname = 'vector' LIMIT 1;")
            if cursor.fetchone() is None:
                raise CommandError(
                    "pgvector extension is not installed in this PostgreSQL DB. "
                    "Install it and run: CREATE EXTENSION vector;"
                )
            cursor.execute("SELECT to_regclass('public.ai_vector_documents');")
            if cursor.fetchone()[0] is None:
                raise CommandError(
                    "ai_vector_documents table is missing. Re-run migrations after pgvector installation."
                )

    def _embed(self, text: str) -> list[float]:
        try:
            from sentence_transformers import SentenceTransformer
        except Exception as exc:  # pragma: no cover
            raise CommandError(
                "sentence-transformers is required. Install with: pip install sentence-transformers"
            ) from exc

        if not hasattr(self, "_hf_model"):
            self._hf_model = SentenceTransformer(EMBEDDING_MODEL)

        vec = self._hf_model.encode(
            [text],
            normalize_embeddings=True,
            show_progress_bar=False,
        )[0]
        return vec.tolist()

    def handle(self, *args, **options):
        self._ensure_postgres()
        query = options["q"].strip()
        top_k = int(options["k"])
        doc_type = options.get("doc_type")

        emb = self._embed(query)
        emb_lit = _vector_literal(emb)

        sql = """
            SELECT id, doc_type, source_table, source_pk, ticker, sector, geography, as_of_date,
                   LEFT(content, 220) AS snippet,
                   (embedding <=> %s::vector) AS distance
            FROM ai_vector_documents
            WHERE embedding IS NOT NULL
        """
        params = [emb_lit]
        if doc_type:
            sql += " AND doc_type = %s"
            params.append(doc_type)
        sql += " ORDER BY embedding <=> %s::vector LIMIT %s"
        params.extend([emb_lit, top_k])

        with connection.cursor() as cursor:
            cursor.execute(sql, params)
            rows = cursor.fetchall()

        if not rows:
            self.stdout.write("No results.")
            return

        self.stdout.write(f"Top {len(rows)} results for: {query}\n")
        for row in rows:
            self.stdout.write(
                f"[id={row[0]}] {row[1]} | {row[4] or row[5] or '-'} | date={row[7]} | dist={row[9]:.4f}"
            )
            self.stdout.write(f"  {row[8]}\n")
