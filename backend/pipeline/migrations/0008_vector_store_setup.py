from django.db import connection, migrations


def setup_vector_store(apps, schema_editor):
    if connection.vendor != "postgresql":
        return

    with connection.cursor() as cursor:
        # Do not attempt installation from migration; many environments lack
        # extension binaries or superuser rights. Proceed only if already installed.
        cursor.execute("SELECT 1 FROM pg_extension WHERE extname = 'vector' LIMIT 1;")
        if cursor.fetchone() is None:
            return
        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS ai_vector_documents (
                id BIGSERIAL PRIMARY KEY,
                doc_type TEXT NOT NULL,
                source_table TEXT NOT NULL,
                source_pk TEXT NOT NULL,
                ticker TEXT NULL,
                sector TEXT NULL,
                geography TEXT NULL,
                as_of_date DATE NULL,
                content TEXT NOT NULL,
                metadata JSONB NOT NULL DEFAULT '{}'::jsonb,
                content_hash TEXT NOT NULL,
                embedding vector(1536),
                created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                UNIQUE (source_table, source_pk)
            );
            """
        )
        cursor.execute(
            """
            CREATE INDEX IF NOT EXISTS idx_ai_vec_doc_type_ticker_date
            ON ai_vector_documents (doc_type, ticker, as_of_date DESC);
            """
        )
        cursor.execute(
            """
            CREATE INDEX IF NOT EXISTS idx_ai_vec_metadata_gin
            ON ai_vector_documents USING GIN (metadata);
            """
        )
        cursor.execute(
            """
            CREATE INDEX IF NOT EXISTS idx_ai_vec_embedding_ivfflat
            ON ai_vector_documents USING ivfflat (embedding vector_cosine_ops)
            WITH (lists = 100);
            """
        )


def teardown_vector_store(apps, schema_editor):
    if connection.vendor != "postgresql":
        return
    with connection.cursor() as cursor:
        cursor.execute("DROP TABLE IF EXISTS ai_vector_documents;")


class Migration(migrations.Migration):

    dependencies = [
        ("pipeline", "0007_bronzestockprice_candle_at_and_more"),
    ]

    operations = [
        migrations.RunPython(setup_vector_store, teardown_vector_store),
    ]
