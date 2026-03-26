# Sequence Diagrams

## 1. Authentication Flow

```mermaid
sequenceDiagram
    autonumber
    actor U as User
    participant F as Frontend (Login/Register)
    participant API as Django API
    participant DB as Database

    U->>F: Submit register/login form
    F->>API: POST /api/register/ or /api/login/
    API->>DB: create / find user + generate token
    API-->>F: { token, user }
    F-->>U: Store token in localStorage, unlock protected routes
```

---

## 2. Add Stock + Persist Analytics + Prediction

```mermaid
sequenceDiagram
    autonumber
    actor U as User
    participant F as Frontend (Stocks Page)
    participant API as Django API
    participant YF as Yahoo Finance (yfinance)
    participant DB as Database
    participant AN as Analytics Pipeline
    participant PR as Prediction Service

    U->>F: Click "Add Stock" (symbol search)
    F->>API: POST /api/portfolio/{id}/add-stock/
    API->>YF: fetch_live_stock_detail(symbol)
    YF-->>API: live quote + history + metadata
    API->>DB: upsert Stock row
    API->>AN: generate_and_persist_stock_analytics(stock)
    AN->>YF: fetch 1Y history
    AN->>DB: upsert StockAnalytics
    API->>PR: refresh_stock_prediction(stock)
    PR->>YF: fetch 1Y Adj Close
    PR->>DB: update Stock prediction fields
    API-->>F: updated stock list payload
    F-->>U: Table refreshed with analytics + prediction columns
```

---

## 3. Portfolio Stocks Page Load

```mermaid
sequenceDiagram
    autonumber
    actor U as User
    participant F as Frontend (Stocks Page)
    participant API as Django API
    participant DB as Database

    U->>F: Navigate to /stocks?portfolio={id}
    F->>API: GET /api/portfolio/
    F->>API: GET /api/stocks/?portfolio={id}
    API->>DB: read Portfolio + Stock + StockAnalytics + prediction fields (current user only)
    DB-->>API: filtered queryset
    API-->>F: normalized stock list
    F-->>U: Render table, PE chart, prediction columns
```

---

## 4. Compare Stocks (Live In-Memory Analysis)

```mermaid
sequenceDiagram
    autonumber
    actor U as User
    participant F as Frontend (Compare Page)
    participant API as Django API
    participant CL as Compare Service
    participant YF as Yahoo Finance (yfinance)

    U->>F: Select Stock A, Stock B, run comparison
    F->>API: GET /api/stocks/live-compare/?symbol_a=A&symbol_b=B&period=...
    API->>CL: fetch_live_stock_comparison(A, B)
    CL->>YF: download A history
    CL->>YF: download B history
    CL->>CL: build DataFrames, align by date, drop NA
    CL->>CL: compute Pearson correlation + linear regression + y_fit
    CL-->>API: comparison payload
    API-->>F: historical + scatter + summary
    F-->>U: Line chart, scatter, best-fit line, equation
```

---

## 5. Portfolio Clustering Analysis

```mermaid
sequenceDiagram
    autonumber
    actor U as User
    participant F as Frontend (Clusters Page)
    participant API as Django API
    participant CS as Cluster Service
    participant Cache as Django Cache
    participant YF as Yahoo Finance (yfinance)
    participant DB as Database

    U->>F: Navigate to /portfolio/:id/clusters
    F->>API: GET /api/portfolio/{id}/clusters/?n_clusters=3
    API->>CS: build_portfolio_clusters(portfolio_id)
    CS->>DB: read portfolio stock symbols
    loop each symbol
        CS->>Cache: check cached history
        alt cache miss
            CS->>YF: download 1Y Adj Close
            CS->>Cache: store history DataFrame
        end
        CS->>CS: compute avg_return + volatility
    end
    CS->>CS: KMeans clustering + cluster label interpretation
    CS-->>API: rows + centroids + cluster summary
    API-->>F: clustering payload
    F-->>U: Risk-return scatter + cluster summary + assignment table
```

---

## 6. Price Prediction (XGBoost / LSTM)

```mermaid
sequenceDiagram
    autonumber
    actor U as User
    participant F as Frontend (Price Prediction Page)
    participant API as Django API
    participant PC as Prediction Cache (DB)
    participant PP as Prediction Pipeline
    participant YF as Yahoo Finance (yfinance)
    participant FS as Filesystem

    U->>F: Select symbol, model, period, frequency → click Run
    F->>API: POST /api/prediction/run/
    API->>PC: lookup cache (symbol + model + period + freq, age < 24h)
    alt cache hit
        PC-->>API: cached forecast_data + plots_path
    else cache miss
        API->>PP: run XGBoost or LSTM pipeline
        PP->>YF: download historical OHLCV
        PP->>PP: train model + generate forecast
        PP->>FS: save plot images to /predictions/{symbol}/{model}/
        PP-->>API: forecast_data + plots_path
        API->>PC: write new PredictionResultCache entry
    end
    API-->>F: forecast data + plot URLs
    F-->>U: Render forecast chart + model metrics
```

---

## 7. AutoSignal — Sector Heatmap & Insights

```mermaid
sequenceDiagram
    autonumber
    actor U as User
    participant F as Frontend (AutoSignal Page)
    participant API as Django API
    participant SVC as AutoSignal Services
    participant DB as Databricks Delta Lake

    U->>F: Navigate to /autosignal
    F->>API: GET /api/autosignal/heatmap/
    F->>API: GET /api/autosignal/insights/
    API->>SVC: get_sector_heatmap()
    SVC->>DB: SELECT from gold.investment_signals
    DB-->>SVC: composite_score, signal, RSI, MA20 per company
    SVC-->>API: heatmap payload
    API->>SVC: get_sector_insights()
    SVC->>DB: SELECT from gold.investment_signals
    SVC->>DB: SELECT from silver.processed_news (top 3)
    SVC->>DB: SELECT from bronze.raw_nse_announcements (negative events)
    SVC->>SVC: compute avg / outlook / signal distribution
    SVC-->>API: insights payload
    API-->>F: heatmap + insights
    F-->>U: Render heatmap tiles + sector outlook panel
```

---

## 8. AutoSignal — Company Intelligence Page

```mermaid
sequenceDiagram
    autonumber
    actor U as User
    participant F as Frontend (AutoSignalCompany Page)
    participant API as Django API
    participant SVC as AutoSignal Services
    participant DB as Databricks Delta Lake
    participant Groq as Groq LLM (Llama 3.1 8B)

    U->>F: Navigate to /autosignal/{slug}
    F->>API: GET /api/autosignal/company/{slug}/
    API->>SVC: get_company_detail(slug)
    SVC->>DB: SELECT from gold.investment_signals WHERE company = X
    SVC->>DB: SELECT from silver.processed_financials WHERE company = X
    SVC->>DB: SELECT from silver.processed_stocks WHERE ticker = X (stock history)
    SVC->>DB: SELECT from bronze.raw_nse_announcements WHERE company = X (events)
    SVC->>DB: SELECT from silver.processed_transcripts WHERE company = X (3 chunks)
    SVC->>Groq: generate analyst report (signal + financials + events + news → prompt)
    Groq-->>SVC: 3-paragraph analyst report text
    SVC-->>API: company intelligence payload
    API-->>F: signal, financials, history, events, transcripts, report
    F-->>U: Render company detail: signal badge, charts, events, AI report
```

---

## 9. AutoSignal — FinBERT Sentiment Inference

```mermaid
sequenceDiagram
    autonumber
    actor Admin as Admin / Scheduler
    participant API as Django API
    participant FB as FinBERT Module
    participant DB as Databricks Delta Lake

    Admin->>API: POST /api/autosignal/run-sentiment/
    API->>FB: run_sentiment_analysis()
    FB->>DB: SELECT news from silver.processed_news
    FB->>FB: tokenize + run FinBERT inference per article
    FB->>DB: WRITE sentiment scores → silver layer
    FB-->>API: { status, count, duration }
    API-->>Admin: response
    Note over FB,DB: Takes ~2-3 minutes for full batch
```

---

## 10. AutoSignal — Semantic Transcript Search

```mermaid
sequenceDiagram
    autonumber
    actor U as User
    participant F as Frontend (AutoSignal Search)
    participant API as Django API
    participant VS as Vector Store (ChromaDB)

    U->>F: Type query e.g. "EV strategy" → search
    F->>API: GET /api/autosignal/search/?q=EV+strategy&collection=transcripts&company=Tata+Motors
    API->>VS: search(query, collection, company, n=5)
    VS->>VS: embed query + cosine similarity search
    VS-->>API: top-N matching transcript chunks + metadata
    API-->>F: { query, results, source: "vector_store" }
    F-->>U: Render matching transcript excerpts
```
