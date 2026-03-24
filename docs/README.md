# Dataflow README (Bronze -> Silver -> Gold)

This project uses a medallion architecture for stock analytics:

- Bronze: raw market/news ingestion
- Silver: cleaned and feature-enriched price series
- Gold: business-ready insights, signals, and forecasts

## 1) Bronze Layer (Raw Data)

Primary tables:

- `pipeline.BronzeStockPrice`
- `pipeline.BronzeNewsArticle`
- `pipeline.BronzeStockFundamentals`

What happens here:

- Data is fetched from external sources and stored as-is.
- No heavy transformations are applied.

Populate Bronze:

```bash
python manage.py run_pipeline --mode=prices --period=1y
python manage.py run_pipeline --mode=news
python manage.py fetch_fundamentals
```

## 2) Silver Layer (Processed Price Data)

Primary table:

- `pipeline.SilverCleanedPrice`

What happens here:

- Bronze prices are cleaned.
- Technical indicators are computed (returns, MAs, RSI, MACD, Bollinger, volatility, etc.).
- One processed row per ticker/date is saved.

Populate Silver:

```bash
python manage.py run_pipeline --mode=silver
```

## 3) Gold Layer (Serving/Insight Data)

Primary tables:

- `pipeline.GoldStockSignal`
- `pipeline.GoldForecastResult`
- `pipeline.GoldStockInsight`

What happens here:

- Signals are computed from Silver indicators.
- Forecasts are generated from Silver history.
- Portfolio-facing insights (PE proxy, discount level, opportunity score, chart payload) are generated and stored.

Populate Gold:

```bash
python manage.py run_pipeline --mode=gold
```

## 4) Sentiment Pipeline (Silver + Gold)

Sentiment mode combines:

- FinBERT news sentiment
- Price momentum signal
- Technical indicator signal

Writes:

- `pipeline.SilverSentimentScore` (ticker-level sentiment)
- `pipeline.GoldSectorSentiment` (sector-level sentiment)

Run sentiment only:

```bash
python manage.py run_pipeline --mode=sentiment --text-mode=title
```

`text-mode` options:

- `title` (fast, recommended for daily refresh)
- `both` (title + description, better context; recommended nightly)

Nightly/full sentiment:

```bash
python manage.py run_pipeline --mode=sentiment --text-mode=both
```

## Where `run_analytics` Fits

Command:

```bash
python manage.py run_analytics
```

Behavior:

- Checks if Bronze data exists per stock.
- Writes analytics insights to Gold (`GoldStockInsight`).
- Optionally refreshes stock prediction fields on `portfolio.Stock`.
- Supports:
  - `--skip-prediction`
  - `--limit N`

Important:

- `run_analytics` does not build Silver.
- Silver must be built via `run_pipeline --mode=silver` (or `--mode=all/full`) first.

## Recommended Execution Order

For fresh or full refresh runs:

```bash
python manage.py run_pipeline --mode=prices --period=1y
python manage.py run_pipeline --mode=silver
python manage.py run_pipeline --mode=gold
python manage.py run_pipeline --mode=sentiment --text-mode=title
python manage.py run_analytics --skip-prediction
```

Optional final prediction refresh:

```bash
python manage.py run_analytics
```

## Sentiment Verification

Quick checks:

```bash
python manage.py shell -c "from pipeline.models import SilverSentimentScore, GoldSectorSentiment; print('SilverSentimentScore:', SilverSentimentScore.objects.count()); print('GoldSectorSentiment:', GoldSectorSentiment.objects.count())"
```

Label distribution:

```bash
python manage.py shell -c "from django.db.models import Count; from pipeline.models import SilverSentimentScore; print(list(SilverSentimentScore.objects.values('sentiment_label').annotate(c=Count('sentiment_label')).order_by('sentiment_label')))"
```

## Quick Mental Model

- Raw fetched data lands in Bronze.
- Processed/feature-rich time series lives in Silver.
- End-user insights and decision outputs are served from Gold.
