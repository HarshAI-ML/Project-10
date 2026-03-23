# Auto Invest AI

Full-stack stock portfolio analytics platform with live market integration, ML-driven price prediction, stock comparison, risk-return clustering, and an AI-powered sector intelligence layer (AutoSignal) backed by Databricks, FinBERT, and Groq LLM.

## Tech Stack

| Layer | Technology |
|---|---|
| Backend | Django 4, Django REST Framework, SQLite |
| Frontend | React (Vite), Tailwind CSS, Recharts |
| Market Data | `yfinance` |
| Data Science | `pandas`, `scikit-learn`, `XGBoost`, `LSTM` |
| AI Intelligence | FinBERT (sentiment), Groq LLM (Llama 3.1) |
| Data Warehouse | Databricks Delta Lake (`bronze` / `silver` / `gold`) |
| Vector Search | ChromaDB (semantic transcript search) |

## Features

### Portfolio & Stocks
- Token-based authentication (`register`, `login`)
- Per-user portfolio creation and management
- Add/remove stocks; live search via `yfinance`
- Stock analytics: PE ratio, discount level, opportunity score
- 1-day stock prediction (linear trend model)
- Dynamic currency display (USD / INR based on ticker)

### Price Prediction
- XGBoost / LSTM prediction pipeline with historical period/frequency controls
- Plot outputs (forecast charts) saved to disk
- 24-hour request caching (`PredictionResultCache`)

### Compare & Clusters
- Compare two stocks: historical lines, scatter, Pearson correlation, best-fit regression
- Portfolio risk-return clustering with K-Means (graceful with sparse data)

### AutoSignal (AI Sector Intelligence)
- Sector heatmap — composite investment signal scores per company
- Company sentiment timeline (daily/weekly granularity)
- Sector insights panel: outlook, signal distribution, best/worst companies
- Corporate event detection from NSE announcements (NSE Bronze table)
- Full company intelligence page: signal, financials, stock history, transcript samples
- Groq LLM-generated analyst report per company (Llama 3.1 8B)
- FinBERT-powered sentiment inference on Databricks news data
- Semantic transcript search via ChromaDB vector store

## Project Structure

```text
auto_invest_AI/
├── backend/
│   ├── api/                          # DRF viewsets, serializers, routes
│   ├── analytics/
│   │   └── services/
│   │       ├── yahoo_search.py       # live search/detail/compare (yfinance)
│   │       ├── prediction.py         # 1-day prediction + caching
│   │       ├── price_prediction.py   # XGBoost/LSTM pipeline + plot generation
│   │       ├── cluster.py            # risk-return K-Means clustering
│   │       └── pipeline.py           # analytics generation + persistence
│   ├── autosignal/                   # AI sector intelligence module
│   │   ├── services.py               # Databricks queries + data assembly
│   │   ├── finbert.py                # FinBERT sentiment inference
│   │   ├── reports.py                # Groq LLM report generation
│   │   ├── views.py                  # API endpoints
│   │   └── urls.py
│   ├── accounts/                     # Auth (register/login)
│   ├── portfolio/                    # Portfolio & Stock models
│   └── manage.py
├── frontend/
│   └── src/
│       ├── pages/
│       │   ├── Portfolio.jsx
│       │   ├── Stocks.jsx
│       │   ├── StockDetail.jsx
│       │   ├── LiveStockDetail.jsx
│       │   ├── CompareStocks.jsx
│       │   ├── PortfolioClusters.jsx
│       │   ├── PricePrediction.jsx
│       │   ├── AutoSignal.jsx        # Sector heatmap + insights
│       │   └── AutoSignalCompany.jsx # Per-company intelligence view
│       ├── components/
│       └── api/stocks.js
└── docs/
    └── SEQUENCE_DIAGRAM.md
```

## Database Models

### Core Models
- **`Portfolio`** — `name`, `description`, `user` (FK)
- **`Stock`** — `portfolio`, `symbol`, `company_name`, `sector`, `current_price`
  - Prediction fields: `predicted_price_1d`, `expected_change_pct`, `direction_signal`, `model_confidence_r2`, `prediction_status`, `recommended_action`, `prediction_updated_at`
- **`StockAnalytics`** — `stock` (OneToOne), `pe_ratio`, `discount_level`, `opportunity_score`, `graph_data`, `last_updated`

### Prediction Cache Models
- **`PredictionResultCache`** — `stock_symbol`, `model_type`, `prediction_frequency`, `historical_period`, `generated_at`, `forecast_data`, `plots_path`
- **`PredictionModelState`** — `model_type`, `last_trained_at`

### Databricks Delta Tables (AutoSignal)
| Layer | Table | Contents |
|---|---|---|
| Bronze | `raw_nse_announcements` | NSE corporate events |
| Silver | `processed_stocks` | OHLCV + indicators |
| Silver | `processed_financials` | PE, EPS, margins, ROE |
| Silver | `processed_news` | Economic Times articles |
| Silver | `processed_transcripts` | Earnings call transcripts |
| Gold | `investment_signals` | Composite signal + scores |

## Setup

### Prerequisites
- Python 3.11+
- Node.js 18+
- Conda environment (recommended): `vibe-env`
- (Optional) Databricks workspace + token for AutoSignal features

### Backend

```powershell
cd backend
conda run -n vibe-env pip install -r requirements.txt
conda run -n vibe-env pip install -r requirements-prediction.txt
conda run -n vibe-env python manage.py migrate
conda run -n vibe-env python manage.py runserver
```

### Frontend

```powershell
cd frontend
npm install
npm run dev
```

Frontend default: `http://localhost:5173`  
Backend default: `http://127.0.0.1:8000`

### Environment Variables (`.env`)

```env
DJANGO_SECRET_KEY=your-secret-key
DJANGO_DEBUG=True
DJANGO_ALLOWED_HOSTS=localhost 127.0.0.1
CORS_ALLOWED_ORIGINS=http://localhost:5173

# AutoSignal — Databricks
DATABRICKS_HOST=https://<workspace>.azuredatabricks.net
DATABRICKS_HTTP_PATH=/sql/1.0/warehouses/<id>
DATABRICKS_TOKEN=<personal-access-token>

# AutoSignal — Groq LLM
GROQ_API_KEY=<groq-api-key>
```

## API Endpoints

### Auth
| Method | Endpoint | Description |
|---|---|---|
| POST | `/api/register/` | Create user account |
| POST | `/api/login/` | Get auth token |

### Portfolio
| Method | Endpoint | Description |
|---|---|---|
| GET | `/api/portfolio/` | List user portfolios |
| POST | `/api/portfolio/` | Create portfolio |
| POST | `/api/portfolio/{id}/add-stock/` | Add stock to portfolio |
| GET | `/api/portfolio/{id}/clusters/` | K-Means cluster analysis |

### Stocks
| Method | Endpoint | Description |
|---|---|---|
| GET | `/api/stocks/?portfolio={id}` | List stocks in portfolio |
| GET | `/api/stocks/{id}/` | Stock detail |
| DELETE | `/api/stocks/{id}/remove/` | Remove stock |
| GET | `/api/stocks/live-search/?q={query}` | Live Yahoo Finance search |
| GET | `/api/stocks/live-detail/?symbol={s}&period={p}&interval={i}` | Live stock detail |
| GET | `/api/stocks/live-compare/?symbol_a={A}&symbol_b={B}&period={p}&interval={i}` | Compare two stocks |

### Price Prediction
| Method | Endpoint | Description |
|---|---|---|
| GET | `/api/prediction/` | List prediction options |
| POST | `/api/prediction/run/` | Run XGBoost/LSTM prediction |

### AutoSignal
| Method | Endpoint | Description |
|---|---|---|
| GET | `/api/autosignal/heatmap/` | Sector heatmap (all companies) |
| GET | `/api/autosignal/sentiment/?company=X` | Company sentiment timeline |
| GET | `/api/autosignal/insights/` | Sector insights panel |
| GET | `/api/autosignal/events/?company=X` | NSE event detection |
| GET | `/api/autosignal/company/{slug}/` | Full company intelligence |
| GET | `/api/autosignal/search/?q={query}` | Semantic transcript search |
| GET | `/api/autosignal/report/` | Sector intelligence report |
| POST | `/api/autosignal/run-sentiment/` | Trigger FinBERT inference |
| POST | `/api/autosignal/run-report/` | Generate fresh Groq report |

## Main Runtime Flows

1. **Auth** — User registers/logs in, receives DRF token, stored in frontend.
2. **Portfolio** — User creates/selects a portfolio; stocks are user-scoped.
3. **Add Stock** — Backend fetches live data from `yfinance`, persists `Stock`, runs analytics pipeline → `StockAnalytics`, runs prediction service → populates prediction fields in `Stock`.
4. **Stocks Table** — Renders persisted analytics + prediction fields from DB (no live calls).
5. **Compare** — Live in-memory DataFrame analysis; Pearson correlation + best-fit regression line.
6. **Clusters** — K-Means on portfolio volatility/return from cached `yfinance` history.
7. **Price Prediction** — XGBoost or LSTM pipeline; results cached for 24 hours.
8. **AutoSignal** — Queries Databricks Delta tables; FinBERT runs inference on news; Groq LLM generates analyst reports; ChromaDB handles semantic search.

## Management Commands

```powershell
# Refresh analytics + predictions for all stocks
conda run -n vibe-env python manage.py run_analytics

# Warm XGBoost / LSTM caches (for scheduler/cron)
conda run -n vibe-env python manage.py run_prediction_maintenance --model xgboost --symbols AAPL TSLA BTC-USD
conda run -n vibe-env python manage.py run_prediction_maintenance --model lstm --symbols AAPL TSLA BTC-USD
```

## Notes

- Portfolio filtering is per authenticated user — each user only sees their own portfolios and stocks.
- Predictions use a 1-year linear trend model and are informational only.
- Prediction artifacts are saved under `/predictions/{stock}/{model}/`.
- Cache policy: identical request signature returns cached data if generated within the last 24 hours.
- Suggested scheduler cadence: XGBoost every 24h, LSTM every 3 days.
- AutoSignal gracefully degrades when Databricks is unconfigured (returns descriptive error objects).
- Clustering gracefully handles empty/insufficient data scenarios.

## Sequence Diagrams

See: [docs/SEQUENCE_DIAGRAM.md](docs/SEQUENCE_DIAGRAM.md)
