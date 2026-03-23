import pandas as pd
import math
from datetime import datetime, timezone
from transformers import pipeline
from .services import get_databricks_df, DATABRICKS_AVAILABLE

# ── Config ────────────────────────────────────────────────────────────────────

FINBERT_MODEL = "ProsusAI/finbert"
BATCH_SIZE    = 16
MAX_CHUNKS    = 300  # cap to avoid timeout

_finbert = None

# ── Helpers ───────────────────────────────────────────────────────────────────

def now():
    return datetime.now(timezone.utc).replace(tzinfo=None).isoformat()

def get_finbert():
    global _finbert
    if _finbert is None:
        print("Loading FinBERT...")
        _finbert = pipeline(
            "text-classification",
            model=FINBERT_MODEL,
            top_k=None,
        )
        print("FinBERT loaded.")
    return _finbert

# ── Sentiment Scoring ─────────────────────────────────────────────────────────

def score_chunks(chunks: list) -> list:
    """Run FinBERT on a list of text chunks. Returns list of dicts with scores."""
    finbert = get_finbert()
    results = []

    for i in range(0, len(chunks), BATCH_SIZE):
        batch = chunks[i:i + BATCH_SIZE]
        try:
            batch_results = finbert(batch, truncation=True, max_length=512)
            results.extend(batch_results)
        except Exception as e:
            print(f"  FinBERT batch error: {e}")
            results.extend([None] * len(batch))

        print(f"  Processed {min(i + BATCH_SIZE, len(chunks))}/{len(chunks)} chunks...")

    return results


def compute_company_scores(chunks_df: pd.DataFrame, finbert_results: list) -> pd.DataFrame:
    """
    Compute probability-weighted sentiment score (0-10) per company.
    """
    LABEL_WEIGHTS = {"positive": 1, "neutral": 0, "negative": -1}

    rows = []
    for i, (_, row) in enumerate(chunks_df.iterrows()):
        result = finbert_results[i]
        if result is None:
            continue

        # Compute weighted score for this chunk
        weighted = sum(
            LABEL_WEIGHTS.get(r["label"], 0) * r["score"]
            for r in result
        )
        rows.append({
            "company":        row.get("company") or row.get("company_tags", "sector"),
            "chunk_id":       row.get("chunk_id", ""),
            "weighted":       weighted,
            "source":         row.get("source", ""),
            "data_type":      row.get("data_type", "news"),
        })

    if not rows:
        return pd.DataFrame()

    chunks_scored = pd.DataFrame(rows)

    # Aggregate per company
    company_scores = []
    for company, grp in chunks_scored.groupby("company"):
        if company == "sector" or not company:
            continue

        avg_weighted    = grp["weighted"].mean()
        sentiment_score = round((avg_weighted + 1) / 2 * 10, 2)
        sentiment_score = max(0.0, min(10.0, sentiment_score))

        article_count    = len(grp[grp["data_type"] == "news"])
        transcript_count = len(grp[grp["data_type"] != "news"])
        intensity        = round(sentiment_score * math.log(max(article_count, 1) + 1), 4)

        company_scores.append({
            "company":             company,
            "sentiment_score":     sentiment_score,
            "weighted_sentiment":  round(float(avg_weighted), 6),
            "article_count":       article_count,
            "transcript_count":    transcript_count,
            "sentiment_intensity": intensity,
            "granularity":         "daily",
            "score_date":          now(),
            "computed_at":         now(),
            "ma_7d_sentiment":     sentiment_score,
            "momentum":            0.0,
        })

    return pd.DataFrame(company_scores)


# ── Main Inference Function ───────────────────────────────────────────────────

def run_sentiment_analysis() -> dict:
    """
    Full FinBERT pipeline:
    1. Fetch chunks from Databricks silver tables
    2. Run FinBERT
    3. Write scores to gold.company_sentiment_scores (Delta)
    4. Return summary
    """
    if not DATABRICKS_AVAILABLE:
        return {"error": "Databricks not configured"}

    print("Fetching news chunks from Databricks...")
    news_df = get_databricks_df(f"""
        SELECT chunk_id, chunk_text, company_tags AS company,
               source, 'news' AS data_type
        FROM silver.processed_news
        WHERE chunk_text IS NOT NULL
        AND chunk_text != ''
        AND chunk_words >= 10
        LIMIT {MAX_CHUNKS}
    """)

    print("Fetching transcript chunks from Databricks...")
    transcripts_df = get_databricks_df(f"""
        SELECT chunk_id, chunk_text, company,
               source, 'transcript' AS data_type
        FROM silver.processed_transcripts
        WHERE has_text = true
        AND chunk_text IS NOT NULL
        AND chunk_text != ''
        LIMIT {MAX_CHUNKS}
    """)

    # Combine
    frames = [df for df in [news_df, transcripts_df] if not df.empty]
    if not frames:
        return {"error": "No chunks found in Databricks"}

    combined = pd.concat(frames, ignore_index=True)
    combined = combined[combined["chunk_text"].str.len() > 20]
    print(f"Total chunks to score: {len(combined)}")

    # Run FinBERT
    chunks_list = combined["chunk_text"].tolist()
    results     = score_chunks(chunks_list)

    # Compute scores
    scores_df = compute_company_scores(combined, results)
    if scores_df.empty:
        return {"error": "No company scores computed"}

    # Write to Databricks Delta
    try:
        from databricks import sql as databricks_sql
        import os

        with databricks_sql.connect(
            server_hostname = os.environ.get("DATABRICKS_HOST"),
            http_path       = os.environ.get("DATABRICKS_HTTP_PATH"),
            access_token    = os.environ.get("DATABRICKS_TOKEN"),
        ) as conn:
            with conn.cursor() as cursor:
                # Create table if not exists
                cursor.execute("""
                    CREATE TABLE IF NOT EXISTS gold.company_sentiment_scores (
                        company             STRING,
                        sentiment_score     DOUBLE,
                        weighted_sentiment  DOUBLE,
                        article_count       INT,
                        transcript_count    INT,
                        sentiment_intensity DOUBLE,
                        granularity         STRING,
                        score_date          STRING,
                        computed_at         STRING,
                        ma_7d_sentiment     DOUBLE,
                        momentum            DOUBLE
                    )
                """)

                # Delete existing scores for today
                cursor.execute(f"""
                    DELETE FROM gold.company_sentiment_scores
                    WHERE DATE(score_date) = '{datetime.now().strftime('%Y-%m-%d')}'
                """)

                # Insert new scores
                for _, row in scores_df.iterrows():
                    cursor.execute("""
                        INSERT INTO gold.company_sentiment_scores VALUES
                        (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """, (
                        row["company"], row["sentiment_score"],
                        row["weighted_sentiment"], row["article_count"],
                        row["transcript_count"], row["sentiment_intensity"],
                        row["granularity"], row["score_date"],
                        row["computed_at"], row["ma_7d_sentiment"],
                        row["momentum"]
                    ))

        print("Scores written to gold.company_sentiment_scores")

    except Exception as e:
        print(f"Databricks write error: {e}")
        return {"error": f"Failed to write to Databricks: {e}"}

    return {
        "status":        "success",
        "chunks_scored": len(combined),
        "companies":     scores_df[["company", "sentiment_score", "article_count"]].to_dict(orient="records"),
        "computed_at":   now(),
    }