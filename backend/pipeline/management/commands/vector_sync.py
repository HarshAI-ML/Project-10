import hashlib
import json
from datetime import date

from django.core.management.base import BaseCommand, CommandError
from django.db import connection

from pipeline.models import BronzeNewsArticle, GoldSectorSentiment, GoldStockInsight, SilverSentimentScore


EMBEDDING_DIM = 384
EMBEDDING_MODEL = "BAAI/bge-small-en-v1.5"


def _hash_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _vector_literal(values: list[float]) -> str:
    return "[" + ",".join(f"{v:.8f}" for v in values) + "]"


class Command(BaseCommand):
    help = "Sync project data into PostgreSQL pgvector table ai_vector_documents."

    def add_arguments(self, parser):
        parser.add_argument(
            "--source",
            type=str,
            default="all",
            choices=["all", "news", "stock_insights", "stock_sentiment", "sector_sentiment"],
            help="Data source to sync.",
        )
        parser.add_argument("--limit", type=int, default=500, help="Max rows per source.")
        parser.add_argument(
            "--embed",
            action="store_true",
            help="Generate embeddings using local HuggingFace sentence-transformers model.",
        )
        parser.add_argument(
            "--reembed",
            action="store_true",
            help="Recompute embeddings even if content hash did not change.",
        )

    def _ensure_postgres(self):
        if connection.vendor != "postgresql":
            raise CommandError("Vector store requires PostgreSQL with pgvector extension.")
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

    def _embed_texts(self, texts: list[str]) -> list[list[float]]:
        try:
            from sentence_transformers import SentenceTransformer
        except Exception as exc:  # pragma: no cover
            raise CommandError(
                "sentence-transformers is required. Install with: pip install sentence-transformers"
            ) from exc

        if not hasattr(self, "_hf_model"):
            self._hf_model = SentenceTransformer(EMBEDDING_MODEL)

        vectors = self._hf_model.encode(
            texts,
            normalize_embeddings=True,
            show_progress_bar=False,
            batch_size=32,
        )
        return [v.tolist() for v in vectors]

    def _upsert(self, rows: list[dict], do_embed: bool, reembed: bool) -> dict:
        inserted = 0
        updated = 0

        if not rows:
            return {"inserted": 0, "updated": 0}

        embeddings = None
        if do_embed:
            embeddings = self._embed_texts([r["content"] for r in rows])

        with connection.cursor() as cursor:
            for idx, row in enumerate(rows):
                content_hash = _hash_text(row["content"])
                vector = embeddings[idx] if embeddings else None
                vector_lit = _vector_literal(vector) if vector else None

                cursor.execute(
                    """
                    SELECT id, content_hash FROM ai_vector_documents
                    WHERE source_table = %s AND source_pk = %s
                    """,
                    [row["source_table"], row["source_pk"]],
                )
                existing = cursor.fetchone()

                if not existing:
                    if vector_lit:
                        cursor.execute(
                            """
                            INSERT INTO ai_vector_documents
                            (doc_type, source_table, source_pk, ticker, sector, geography, as_of_date, content, metadata, content_hash, embedding)
                            VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s::jsonb,%s,%s::vector)
                            """,
                            [
                                row["doc_type"],
                                row["source_table"],
                                row["source_pk"],
                                row.get("ticker"),
                                row.get("sector"),
                                row.get("geography"),
                                row.get("as_of_date"),
                                row["content"],
                                json.dumps(row.get("metadata", {})),
                                content_hash,
                                vector_lit,
                            ],
                        )
                    else:
                        cursor.execute(
                            """
                            INSERT INTO ai_vector_documents
                            (doc_type, source_table, source_pk, ticker, sector, geography, as_of_date, content, metadata, content_hash)
                            VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s::jsonb,%s)
                            """,
                            [
                                row["doc_type"],
                                row["source_table"],
                                row["source_pk"],
                                row.get("ticker"),
                                row.get("sector"),
                                row.get("geography"),
                                row.get("as_of_date"),
                                row["content"],
                                json.dumps(row.get("metadata", {})),
                                content_hash,
                            ],
                        )
                    inserted += 1
                    continue

                existing_id, existing_hash = existing
                if (existing_hash == content_hash) and not reembed:
                    continue

                if vector_lit:
                    cursor.execute(
                        """
                        UPDATE ai_vector_documents
                        SET doc_type=%s, ticker=%s, sector=%s, geography=%s, as_of_date=%s,
                            content=%s, metadata=%s::jsonb, content_hash=%s, embedding=%s::vector, updated_at=NOW()
                        WHERE id=%s
                        """,
                        [
                            row["doc_type"],
                            row.get("ticker"),
                            row.get("sector"),
                            row.get("geography"),
                            row.get("as_of_date"),
                            row["content"],
                            json.dumps(row.get("metadata", {})),
                            content_hash,
                            vector_lit,
                            existing_id,
                        ],
                    )
                else:
                    cursor.execute(
                        """
                        UPDATE ai_vector_documents
                        SET doc_type=%s, ticker=%s, sector=%s, geography=%s, as_of_date=%s,
                            content=%s, metadata=%s::jsonb, content_hash=%s, updated_at=NOW()
                        WHERE id=%s
                        """,
                        [
                            row["doc_type"],
                            row.get("ticker"),
                            row.get("sector"),
                            row.get("geography"),
                            row.get("as_of_date"),
                            row["content"],
                            json.dumps(row.get("metadata", {})),
                            content_hash,
                            existing_id,
                        ],
                    )
                updated += 1

        return {"inserted": inserted, "updated": updated}

    def _rows_news(self, limit: int) -> list[dict]:
        qs = (
            BronzeNewsArticle.objects
            .order_by("-ingested_at")
            .values("article_id", "title", "description", "company_tags", "published_at", "source", "source_quality")[:limit]
        )
        rows = []
        for n in qs:
            content = f"{n.get('title') or ''}\n\n{n.get('description') or ''}".strip()
            rows.append(
                {
                    "doc_type": "news",
                    "source_table": "pipeline_bronzenewsarticle",
                    "source_pk": n["article_id"],
                    "ticker": None,
                    "sector": None,
                    "geography": None,
                    "as_of_date": None,
                    "content": content,
                    "metadata": {
                        "company_tags": n.get("company_tags"),
                        "published_at": n.get("published_at"),
                        "source": n.get("source"),
                        "source_quality": n.get("source_quality"),
                    },
                }
            )
        return rows

    def _rows_stock_insights(self, limit: int) -> list[dict]:
        qs = (
            GoldStockInsight.objects
            .order_by("-date", "-updated_at")
            .values("id", "ticker", "date", "pe_ratio", "discount_level", "opportunity_score")[:limit]
        )
        rows = []
        for x in qs:
            content = (
                f"Ticker {x['ticker']} on {x['date']}: "
                f"PE ratio {x.get('pe_ratio')}, discount {x.get('discount_level')}, "
                f"opportunity score {x.get('opportunity_score')}."
            )
            rows.append(
                {
                    "doc_type": "stock_insight",
                    "source_table": "pipeline_goldstockinsight",
                    "source_pk": str(x["id"]),
                    "ticker": x["ticker"],
                    "sector": None,
                    "geography": None,
                    "as_of_date": x["date"],
                    "content": content,
                    "metadata": {
                        "pe_ratio": x.get("pe_ratio"),
                        "discount_level": x.get("discount_level"),
                        "opportunity_score": x.get("opportunity_score"),
                    },
                }
            )
        return rows

    def _rows_stock_sentiment(self, limit: int) -> list[dict]:
        qs = (
            SilverSentimentScore.objects
            .order_by("-date")
            .values("id", "ticker", "date", "sentiment_score", "sentiment_label", "article_count", "model_used")[:limit]
        )
        rows = []
        for x in qs:
            content = (
                f"Ticker {x['ticker']} sentiment on {x['date']}: "
                f"score {x.get('sentiment_score')} label {x.get('sentiment_label')} "
                f"from model {x.get('model_used')} using {x.get('article_count')} articles."
            )
            rows.append(
                {
                    "doc_type": "stock_sentiment",
                    "source_table": "pipeline_silversentimentscore",
                    "source_pk": str(x["id"]),
                    "ticker": x["ticker"],
                    "sector": None,
                    "geography": None,
                    "as_of_date": x["date"],
                    "content": content,
                    "metadata": {
                        "sentiment_score": x.get("sentiment_score"),
                        "sentiment_label": x.get("sentiment_label"),
                        "article_count": x.get("article_count"),
                        "model_used": x.get("model_used"),
                    },
                }
            )
        return rows

    def _rows_sector_sentiment(self, limit: int) -> list[dict]:
        qs = (
            GoldSectorSentiment.objects
            .order_by("-date")
            .values("id", "sector", "geography", "date", "sentiment_score", "sentiment_label", "stock_count")[:limit]
        )
        rows = []
        for x in qs:
            content = (
                f"Sector sentiment for {x['sector']} ({x['geography']}) on {x['date']}: "
                f"score {x.get('sentiment_score')} label {x.get('sentiment_label')} "
                f"covering {x.get('stock_count')} stocks."
            )
            rows.append(
                {
                    "doc_type": "sector_sentiment",
                    "source_table": "pipeline_goldsectorsentiment",
                    "source_pk": str(x["id"]),
                    "ticker": None,
                    "sector": x["sector"],
                    "geography": x.get("geography"),
                    "as_of_date": x["date"],
                    "content": content,
                    "metadata": {
                        "sentiment_score": x.get("sentiment_score"),
                        "sentiment_label": x.get("sentiment_label"),
                        "stock_count": x.get("stock_count"),
                    },
                }
            )
        return rows

    def handle(self, *args, **options):
        self._ensure_postgres()

        source = options["source"]
        limit = int(options["limit"])
        do_embed = bool(options["embed"])
        reembed = bool(options["reembed"])

        builders = []
        if source in ("all", "news"):
            builders.append(("news", self._rows_news))
        if source in ("all", "stock_insights"):
            builders.append(("stock_insights", self._rows_stock_insights))
        if source in ("all", "stock_sentiment"):
            builders.append(("stock_sentiment", self._rows_stock_sentiment))
        if source in ("all", "sector_sentiment"):
            builders.append(("sector_sentiment", self._rows_sector_sentiment))

        totals = {"inserted": 0, "updated": 0, "scanned": 0}
        for name, builder in builders:
            rows = builder(limit)
            result = self._upsert(rows, do_embed=do_embed, reembed=reembed)
            totals["inserted"] += result["inserted"]
            totals["updated"] += result["updated"]
            totals["scanned"] += len(rows)
            self.stdout.write(
                self.style.SUCCESS(
                    f"[{name}] scanned={len(rows)} inserted={result['inserted']} updated={result['updated']}"
                )
            )

        self.stdout.write("\nVector sync complete")
        self.stdout.write(
            f"Scanned={totals['scanned']} Inserted={totals['inserted']} Updated={totals['updated']}"
        )
        if do_embed:
            self.stdout.write(f"Embedding model: {EMBEDDING_MODEL}")
