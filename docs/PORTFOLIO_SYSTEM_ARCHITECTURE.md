# Portfolio Management System Architecture

## Overview

This document describes how stocks are added to individual user portfolios in the Django/React financial application. The system implements a sophisticated portfolio management layer on top of a Medallion Architecture data pipeline.

---

## Table of Contents

1. [System Context](#system-context)
2. [Core Data Models](#core-data-models)
3. [Stock Addition Flows](#stock-addition-flows)
4. [Data Flow Diagrams](#data-flow-diagrams)
5. [API Endpoints](#api-endpoints)
6. [Prediction & Analytics Integration](#prediction--analytics-integration)
7. [Important Notes](#important-notes)
8. [Usage Examples](#usage-examples)

---

## System Context

The portfolio system sits on top of the Medallion Architecture pipeline:

```
[Medallion Pipeline]
        │
        ▼
[BronzeStockPrice, BronzeNewsArticle, BronzeStockFundamentals]
        │
        ▼
[SilverCleanedPrice] (technical indicators)
        │
        ▼
[GoldStockSignal, GoldForecastResult] (signals + predictions)
        │
        ▼
[Portfolio System] ← This document's focus
```

The portfolio system manages:
- **User portfolios** (themed groups of stocks)
- **Stock catalog** (400 approved stocks from StockMaster)
- **Portfolio holdings** (which stocks belong to which user's portfolios)
- **Live predictions** (integrated from Gold layer)

---

## Core Data Models

### 1. StockMaster (Master Catalog)

```python
class StockMaster(models.Model):
    ticker = models.CharField(max_length=30, unique=True, db_index=True)
    name = models.CharField(max_length=200)
    sector = models.CharField(max_length=100)
    geography = models.CharField(max_length=5, choices=[('IN', 'India'), ('US', 'US')], default='IN')
    is_active = models.BooleanField(default=True)
    added_at = models.DateTimeField(auto_now_add=True)
```

**Purpose**: Admin-managed master table of all 400 approved stocks. Never modified by users. Single source of truth for available tickers.

**Source**: Seeded from `scripts/nifty500_top200.py` via `python manage.py seed_stock_master`

**Example entries**:
```
('RELIANCE.NS', 'Reliance Industries Ltd.', 'Oil Gas & Consumable Fuels', 'IN')
('AAPL', 'Apple Inc.', 'Technology', 'US')
('360ONE.NS', '360 ONE WAM Ltd.', 'Financial Services', 'IN')
```

---

### 2. Portfolio (User's Portfolio Container)

```python
class Portfolio(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name="portfolios")
    name = models.CharField(max_length=100)
    description = models.TextField(blank=True)
    is_default = models.BooleanField(default=False)
    portfolio_type = models.CharField(max_length=20, choices=[('default', 'Default'), ('custom', 'Custom')])
    geography = models.CharField(max_length=5, choices=[('IN', 'India'), ('US', 'US'), ('ALL', 'All')], default='ALL')
```

**Purpose**: Represents a themed group of stocks owned by a specific user.

**Types**:
- **Default portfolios**: Auto-created at registration/login (25 sector-based portfolios)
- **Custom portfolios**: User-created via API

**Default portfolio examples**:
```
- Nifty Auto (Automobile sector, India)
- Nifty Bank (Financial Services, India)
- US Technology (Technology, US)
- Nifty Pharma (Healthcare, India)
```

---

### 3. PortfolioStock (Join Table)

```python
class PortfolioStock(models.Model):
    portfolio = models.ForeignKey(Portfolio, on_delete=models.CASCADE, related_name='portfolio_stocks')
    stock_master = models.ForeignKey('StockMaster', on_delete=models.SET_NULL, null=True, blank=True, related_name='portfolio_entries')
    ticker = models.CharField(max_length=30, db_index=True)
    company_name = models.CharField(max_length=200, blank=True)
    sector = models.CharField(max_length=100, blank=True)
    geography = models.CharField(max_length=5, blank=True)
    added_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = [['portfolio', 'ticker']]
```

**Purpose**: The **correct** normalized way to associate stocks with portfolios. This is the many-to-many join table.

**Key points**:
- `stock_master` FK links to the master catalog
- `ticker`, `company_name`, `sector`, `geography` are **denormalized** for fast reads without joins
- Unique constraint: one stock can appear only once per portfolio

**Comments in code** (`portfolio/models.py:76-77`):
> "This is the correct way to add stocks to portfolios - never modify the Stock master table rows directly."

---

### 4. Stock (Legacy Denormalized Model)

```python
class Stock(models.Model):
    portfolio = models.ForeignKey(Portfolio, on_delete=models.CASCADE, null=True, blank=True, related_name="stocks")
    symbol = models.CharField(max_length=20, unique=True)
    company_name = models.CharField(max_length=255)
    sector = models.CharField(max_length=100)
    current_price = models.FloatField()
    predicted_price_1d = models.FloatField(null=True, blank=True)
    expected_change_pct = models.FloatField(null=True, blank=True)
    direction_signal = models.CharField(max_length=30, blank=True, default="")
    model_confidence_r2 = models.FloatField(null=True, blank=True)
    prediction_status = models.CharField(max_length=30, default="unavailable")
    recommended_action = models.CharField(max_length=50, blank=True, default="")
    prediction_updated_at = models.DateTimeField(null=True, blank=True, default=timezone.now)
    ticker = models.CharField(max_length=30, unique=True, null=True, blank=True)
    name = models.CharField(max_length=200, null=True, blank=True)
    geography = models.CharField(max_length=5, choices=[("IN", "India"), ("US", "US")], default="IN")
    is_active = models.BooleanField(default=True)
```

**Purpose**: Denormalized per-portfolio stock with live predictions embedded. Used by the API for fast reads.

**Key points**:
- Has `portfolio` FK (odd: typically stocks shouldn't be portfolio-specific)
- `symbol` is unique (not per-portfolio), which is problematic for multi-portfolio scenarios
- Stores predictions inline to avoid joins on every read
- Created/updated when using `POST /portfolio/{id}/add-stock`

**Status**: This model appears to be a legacy denormalization that co-exists with `PortfolioStock`. The two models serve different purposes but have overlapping data.

---

## Stock Addition Flows

### Flow 1: Automatic Default Portfolios (At User Creation)

**Trigger**: User registration or first login

**Endpoint**: `POST /api/register/` or `POST /api/login/`

**Code Path**:
```
api/views.py (AuthViewSet)
  ├─ register() or login()
  │   └─ create_default_portfolios_for_user(user)
  │       └─ portfolio/services.py:48-104
```

**Process**:
1. For each of the 25 default portfolio configurations:
   ```python
   config = {
     "name": "Nifty IT",
     "description": "Information technology sector",
     "sectors": ["Information Technology"],
     "geography": "IN"
   }
   ```
2. Create `Portfolio` record with `is_default=True`
3. Query `StockMaster` for all active stocks matching:
   ```
   sector IN config['sectors'] AND geography == config['geography']
   ```
4. For each matching StockMaster, create a `PortfolioStock` entry

**Result**: User gets 25 portfolios pre-populated with all relevant stocks from the 400-stock catalog.

**Example**: User registers → Gets "Nifty IT" portfolio with ~10 IT stocks (TCS, Infosys, Wipro, etc.)

---

### Flow 2: Manual Stock Addition (User Action)

**Trigger**: User clicks "Add Stock" in frontend

**Endpoint**: `POST /portfolio/{portfolio_id}/add-stock`

**Body**: `{"symbol": "RELIANCE.NS"}`

**Code Path**:
```
api/views.py (PortfolioViewSet.add_stock)
  ├─ Validate symbol
  ├─ Look up StockMaster via get_stock_info(symbol)
  ├─ Fetch latest price via get_latest_price(symbol)
  ├─ Stock.objects.update_or_create(symbol=symbol, defaults={...})
  │   └─ Creates/updates denormalized Stock with:
  │       • portfolio = portfolio
  │       • company_name, sector from StockMaster
  │       • current_price from latest data
  ├─ generate_and_persist_stock_analytics(stock)
  ├─ refresh_stock_prediction(stock)
  │   └─ analytics/services/prediction.py:150-156
  │       ├─ get_stock_prediction(symbol)
  │       │   ├─ Check cache (24h TTL)
  │       │   ├─ Freshness check (6h TTL)
  │       │   └─ If stale: _compute_prediction()
  │       │       ├─ Load history from BronzeStockPrice
  │       │       ├─ Train LinearRegression
  │       │       ├─ Predict 1-day forward
  │       │       └─ Cache result
  │       └─ Update Stock fields:
  │           • predicted_price_1d
  │           • expected_change_pct
  │           • direction_signal (↑ Increase / ↓ Decrease)
  │           • model_confidence_r2
  │           • prediction_status (ok / insufficient_data / unavailable)
  │           • recommended_action (Buy Bias / Reduce Bias / Hold/Watch / etc.)
  │           • prediction_updated_at
  └─ Return Stock via StockListSerializer
```

**Result**: A `Stock` row is created/updated with predictions. **Note**: This does **not** create a `PortfolioStock` entry. The system maintains both.

---

### Flow 3: Bulk Population (Setup/Dev)

**Trigger**: Manual command execution

**Command**: `python manage.py populate_portfolio_stocks [--user=username] [--clear]`

**Code Path**:
```
portfolio/management/commands/populate_portfolio_stocks.py
  └─ handle()
      ├─ Load all active StockMaster into memory
      ├─ For each user (or single user if --user):
      │   └─ For each default portfolio of user:
      │       ├─ Match stocks by (sector, geography) using PORTFOLIO_SECTOR_MAP
      │       ├─ If --clear: delete existing PortfolioStock rows
      │       └─ Bulk create PortfolioStock entries
      └─ Print summary statistics
```

**Result**: Populates the normalized `PortfolioStock` join table for all default portfolios. This is the bulk of the data seeding.

**Used in**: `bootstrap_data` command (step 4/6)

---

## Data Flow Diagrams

### High-Level Flow

```
┌─────────────────────────────────────────────────────────────────┐
│                        External Data Sources                     │
│   Yahoo Finance API (prices + fundamentals)                     │
│   RSS Feeds (Economic Times news)                               │
└────────────────────────────┬────────────────────────────────────┘
                             │
                             ▼
┌─────────────────────────────────────────────────────────────────┐
│                      Medallion Pipeline                         │
│                                                                 │
│   Bronze: BronzeStockPrice, BronzeNewsArticle,                 │
│           BronzeStockFundamentals                              │
│         │                                                       │
│         ▼                                                       │
│   Silver: SilverCleanedPrice (with RSI, MACD, Bollinger, etc.) │
│         │                                                       │
│         ▼                                                       │
│   Gold: GoldStockSignal (BUY/SELL/HOLD)                        │
│         GoldForecastResult (1-day prediction)                  │
└────────────────────────────┬────────────────────────────────────┘
                             │
                             ▼
┌─────────────────────────────────────────────────────────────────┐
│                    Portfolio System                            │
│                                                                 │
│   ┌─────────────────┐         ┌─────────────────────────────┐ │
│   │  StockMaster    │◄────────┤    Default Portfolios      │ │
│   │  (400 stocks)   │         │    (25 per user)           │ │
│   └────────┬────────┘         └─────────────┬───────────────┘ │
│            │                                  │                 │
│            │ User manually adds               │ Auto on login   │
│            ▼                                  ▼                 │
│   ┌─────────────────┐         ┌─────────────────────────────┐ │
│   │     Stock       │         │   PortfolioStock (join)     │ │
│   │ (denormalized + │         │   (normalized)              │ │
│   │  predictions)   │         └─────────────────────────────┘ │
│   └─────────────────┘                                          │
│                                                                 │
└─────────────────────────────────────────────────────────────────┘
```

---

### Detailed Add-Stock Flow

```
User Frontend
     │
     │ POST /portfolio/{id}/add-stock {"symbol": "RELIANCE.NS"}
     ▼
PortfolioViewSet.add_stock()
     │
     ├─► Validate symbol exists in StockMaster
     │   └─ get_stock_info("RELIANCE.NS")
     │       └─ SELECT * FROM StockMaster WHERE ticker='RELIANCE.NS'
     │
     ├─► Fetch latest price from SilverCleanedPrice
     │   └─ get_latest_price("RELIANCE.NS")
     │       └─ SELECT * FROM SilverCleanedPrice WHERE ticker='RELIANCE.NS'
     │           ORDER BY date DESC LIMIT 1
     │
     ├─► Create/Update Stock row
     │   └─ Stock.objects.update_or_create(
     │         symbol='RELIANCE.NS',
     │         portfolio=portfolio,
     │         defaults={
     │           company_name='Reliance Industries Ltd.',
     │           sector='Oil Gas & Consumable Fuels',
     │           current_price=2875.50,
     │         }
     │       )
     │
     ├─► Generate analytics
     │   └─ generate_and_persist_stock_analytics(stock)
     │       └─ Creates/updates StockAnalytics record
     │           (PE ratio, discount level, opportunity score, graph data)
     │
     ├─► Refresh prediction (ON-DEMAND!)
     │   └─ refresh_stock_prediction(stock)
     │       │
     │       ├─► Check cache (key: stock_prediction:RELIANCE.NS)
     │       │   └─ Cache TTL: 24h
     │       │
     │       ├─► Freshness check:
     │       │   └─ Compare cached last_data_date vs latest Bronze data
     │       │       TTL: 6h
     │       │
     │       ├─► If stale, compute:
     │       │   └─ _compute_prediction()
     │       │       ├─ Load history: get_stock_history('RELIANCE.NS', days=365)
     │       │       │   └─ FROM BronzeStockPrice WHERE ticker='RELIANCE.NS'
     │       │       │       (last 365 days)
     │       │       │
     │       │       ├─ Train LinearRegression:
     │       │       │   X = [[0], [1], [2], ...]  (day numbers)
     │       │       │   y = [price0, price1, price2, ...]
     │       │       │
     │       │       ├─ Predict next day:
     │       │       │   predicted = model.predict([[last_day+1]])
     │       │       │
     │       │       └─ Return:
     │       │           predicted_price_1d=2878.23
     │       │           expected_change_pct=0.09%
     │       │           direction_signal="↑ Increase"
     │       │           model_confidence_r2=0.87
     │       │
     │       └─ Update Stock fields:
     │           • predicted_price_1d
     │           • expected_change_pct
     │           • direction_signal
     │           • model_confidence_r2
     │           • prediction_status
     │           • recommended_action
     │           • prediction_updated_at
     │
     └─► Return Stock (serialized) to frontend
```

---

### PortfolioStockViewSet Read Flow

**Endpoint**: `GET /portfolio-stocks/?portfolio={id}`

**Code Path**: `api/views.py:PortfolioStockViewSet.list():389-528`

**Process**:
1. Get user's PortfolioStock entries for the portfolio
2. Extract all tickers
3. Batch fetch from multiple sources:
   ```
   ├─ SilverCleanedPrice (latest price + indicators)
   ├─ BronzeStockFundamentals (PE ratio, etc.)
   ├─ GoldStockSignal (BUY/SELL/HOLD signals)
   ├─ GoldForecastResult (predictions)
   └─ StockAnalytics (opportunity scores)
   ```
4. Join data in Python (no database joins)
5. Return enriched array to frontend

**SQL queries executed**:
```sql
-- 1. Get portfolio_stocks for user
SELECT * FROM portfolio_portfoliostock WHERE portfolio_id=? AND portfolio__user_id=?

-- 2. Get latest Silver prices for all tickers
SELECT ticker, MAX(date) as max_date
FROM pipeline_silvercleanedprice
WHERE ticker IN ('RELIANCE.NS', 'TCS.NS', ...)
GROUP BY ticker

-- 3. Get those latest rows
SELECT * FROM pipeline_silvercleanedprice
WHERE ticker=? AND date=?

-- 4. Get fundamentals
SELECT * FROM pipeline_bronzestockfundamentals
WHERE ticker IN (...)

-- 5. Get signals
SELECT * FROM pipeline_goldstocksignal
WHERE ticker IN (...) AND date=(SELECT MAX(date) FROM ...)

-- 6. Get forecasts
SELECT * FROM pipeline_goldforecastresult
WHERE ticker IN (...) AND forecast_date=?

-- 7. Get analytics
SELECT * FROM analytics_stockanalytics
WHERE stock_id IN (SELECT id FROM portfolio_stock WHERE symbol IN (...))
```

---

## API Endpoints

### Authentication & Setup

| Endpoint | Method | Purpose |
|----------|--------|---------|
| `/api/register/` | POST | Register user + auto-create 25 default portfolios |
| `/api/login/` | POST | Login user + create default portfolios if missing |

---

### Portfolio Management

| Endpoint | Method | Purpose |
|----------|--------|---------|
| `/portfolio/` | GET | List user's portfolios |
| `/portfolio/` | POST | Create custom portfolio |
| `/portfolio/{id}/` | GET | Retrieve portfolio details |
| `/portfolio/{id}/add-stock` | POST | Add stock to portfolio (creates Stock row) |
| `/portfolio/{id}/remove-stock` | DELETE | Remove stock from portfolio |
| `/portfolio/{id}/clusters` | GET | Get portfolio clustering analysis |

---

### Stock Data

| Endpoint | Method | Purpose |
|----------|--------|---------|
| `/portfolio-stocks/` | GET | List all stocks in user's portfolios (enriched with predictions) |
| `/portfolio-stocks/?portfolio={id}` | GET | List stocks for specific portfolio |
| `/stocks/` | GET | List all stocks (legacy) |
| `/stocks/search?q={query}` | GET | Search stocks by symbol/company |
| `/stocks/live-search?q={query}&limit={n}` | GET | Live search from StockMaster |
| `/stocks/live-detail?symbol={sym}&period={p}&interval={i}` | GET | Live stock details from Yahoo |
| `/stocks/clusters` | GET | Global clustering analysis |

---

### Predictions

| Endpoint | Method | Purpose |
|----------|--------|---------|
| `/prediction/` | GET | List prediction options (model types, frequencies) |
| `/prediction/run/` | POST | Run custom prediction with parameters |

---

## Prediction & Analytics Integration

### Prediction System

**On-Demand Prediction Flow** (`analytics/services/prediction.py`):

```python
def get_stock_prediction(symbol: str) -> dict:
    """
    Main entry point for stock predictions.
    Uses caching (24h TTL) with freshness checks (6h).
    """
    # 1. Check cache
    cache_key = f"stock_prediction:{symbol}"
    cached = cache.get(cache_key)
    if cached and is_fresh(cached["last_data_date"]):
        return cached

    # 2. Compute fresh prediction
    result = _compute_prediction(symbol)

    # 3. Cache and return
    cache.set(cache_key, result, 24h)
    return result

def _compute_prediction(symbol: str) -> dict:
    """
    Linear Regression prediction using Bronze data.
    """
    # Load history from BronzeStockPrice
    df = get_stock_history(symbol, days=365)
    if len(df) < 60:
        return {"status": "insufficient_data"}

    # Features: Day number (0, 1, 2, ...)
    X = df[["Day"]]
    y = df["Adj Close"]

    # Train
    model = LinearRegression()
    model.fit(X, y)

    # Predict next day
    future_day = [[df["Day"].iloc[-1] + 1]]
    predicted_price = model.predict(future_day)[0]
    confidence = model.score(X, y)

    # Calculate metrics
    current_price = df["Adj Close"].iloc[-1]
    expected_change_pct = ((predicted_price - current_price) / current_price) * 100

    return {
        "status": "ok",
        "predicted_price_1d": round(predicted_price, 2),
        "expected_change_pct": round(expected_change_pct, 2),
        "direction_signal": "↑ Increase" if predicted_price > current_price else "↓ Decrease",
        "model_confidence_r2": round(confidence, 2),
        "last_data_date": df["Date"].iloc[-1].strftime("%Y-%m-%d"),
    }
```

**When predictions are generated**:
1. **On-demand** when user adds a stock via `add-stock` endpoint
2. **On-demand** when `refresh_stock_prediction(stock)` is called
3. **Batch mode** via `python manage.py run_analytics` (separate command)
4. **Cached** for 24 hours with 6-hour freshness checks

---

### Analytics Integration

**StockAnalytics Model** (`analytics/models.py`):
```python
class StockAnalytics(models.Model):
    stock = models.OneToOneField(Stock, on_delete=models.CASCADE, related_name='analytics')
    pe_ratio = models.FloatField(null=True)
    discount_level = models.CharField(max_length=50)  # "premium", "discount", "par"
    opportunity_score = models.IntegerField(null=True)  # 1-100
    graph_data = models.JSONField()  # price history, moving averages, etc.
    last_updated = models.DateTimeField(auto_now=True)
```

**Generation** (`analytics/services/pipeline.py:generate_and_persist_stock_analytics`):
- Called automatically when a stock is added to a portfolio
- PE ratio comparison with sector average
- Discount level calculation
- Opportunity scoring (relative value)
- Graph data for charts (price + MA50 + MA200)

---

## Important Notes

### Model Inconsistencies

The system has **two different ways** to represent portfolio holdings:

1. **PortfolioStock** (normalized, recommended by code comments)
   - Proper many-to-many relationship
   - Denormalized fields for performance
   - Used by: `populate_portfolio_stocks` command, bulk operations

2. **Stock** (denormalized, legacy?)
   - Has `portfolio` FK (one-to-many, not many-to-many)
   - `symbol` is globally unique (breaks multi-portfolio scenario)
   - Contains predictions and analytics
   - Used by: `add_stock` API, frontend display via `StockViewSet`

**Why both?** Likely historical reasons. The `PortfolioStockViewSet.list()` method (used by frontend portfolio pages) reads from `PortfolioStock` and enriches with predictions from Gold layer. The `StockViewSet` reads from `Stock` model directly.

**Recommendation**: Consider consolidating to just `PortfolioStock` with cached prediction fields, or fix `Stock` to be truly per-portfolio (remove unique constraint on `symbol`).

---

### Data Synchronization

Predictions flow from **Gold layer** → **Portfolio Stock Display**:

```
GoldForecastResult (pipeline)
     │
     ├─► On-demand via Stock model:
     │       refresh_stock_prediction() queries GoldForecastResult
     │       ↓
     │   Stock.predicted_price_1d, etc.
     │
     └─► Enriched read via PortfolioStockViewSet:
             GET /portfolio-stocks/ joins with GoldForecastResult at query time
```

**Two paths**:
1. **Stock model**: Stale cache (24h), updated on-demand
2. **PortfolioStockViewSet**: Always fresh, queries GoldForecastResult on every request

---

### StockMaster vs Stock

- **StockMaster**: Read-only catalog of approved tickers (400 stocks). Admin-managed.
- **Stock**: Denormalized per-portfolio entries with predictions. User-created via `add-stock`.
- **Relation**: Stock should ideally reference StockMaster, but currently Stock uses its own `symbol` field.

---

### Default Portfolio Configuration

Default portfolios are defined in `portfolio/services.py`:

```python
INDIAN_SECTOR_PORTFOLIOS = [
    {"name": "Nifty Auto", "sectors": ["Automobile and Auto Components"], "geography": "IN"},
    {"name": "Nifty Bank", "sectors": ["Financial Services"], "geography": "IN"},
    {"name": "Nifty FMCG", "sectors": ["Fast Moving Consumer Goods"], "geography": "IN"},
    {"name": "Nifty IT", "sectors": ["Information Technology"], "geography": "IN"},
    # ... 14 total
]

US_SECTOR_PORTFOLIOS = [
    {"name": "US Technology", "sectors": ["Technology"], "geography": "US"},
    {"name": "US Healthcare", "sectors": ["Healthcare"], "geography": "US"},
    # ... 11 total
]
```

The sector mappings in `populate_portfolio_stocks.py` (`PORTFOLIO_SECTOR_MAP`) are more granular and map portfolio names to potentially multiple sectors.

---

## Usage Examples

### As a Developer

#### Add a stock programmatically (recommended way):

```python
from portfolio.models import Portfolio, PortfolioStock, StockMaster

# Get user's portfolio
portfolio = Portfolio.objects.get(user=user, name="Nifty IT")

# Get stock from master catalog
stock_master = StockMaster.objects.get(ticker="TCS.NS")

# Create join entry
PortfolioStock.objects.create(
    portfolio=portfolio,
    stock_master=stock_master,
    ticker=stock_master.ticker,
    company_name=stock_master.name,
    sector=stock_master.sector,
    geography=stock_master.geography,
)
```

#### Trigger a prediction refresh:

```python
from portfolio.models import Stock

stock = Stock.objects.get(symbol="RELIANCE.NS")
from analytics.services.prediction import refresh_stock_prediction
refresh_stock_prediction(stock)  # Updates predicted_price_1d, etc.
```

---

### As an Admin

#### Seed StockMaster catalog:

```bash
python manage.py seed_stock_master
```

#### Bootstrap a new user (or all users):

```bash
# Create all users' default portfolios with stocks
python manage.py seed_default_portfolios

# Populate PortfolioStock entries
python manage.py populate_portfolio_stocks

# Or one-shot for specific user
python manage.py populate_portfolio_stocks --user=johndoe --clear
```

#### Full system bootstrap:

```bash
python manage.py bootstrap_data
# Steps:
# 1. Migrate
# 2. seed_stock_master
# 3. seed_default_portfolios
# 4. populate_portfolio_stocks
# 5. fetch_fundamentals
# 6. run_pipeline --mode=all
```

---

### As an API Consumer (Frontend)

#### Add stock to portfolio:

```http
POST /portfolio/3/add-stock/
Content-Type: application/json
Authorization: Token abc123...

{
  "symbol": "RELIANCE.NS"
}

Response:
{
  "id": 456,
  "symbol": "RELIANCE.NS",
  "company_name": "Reliance Industries Ltd.",
  "sector": "Oil Gas & Consumable Fuels",
  "current_price": 2875.50,
  "predicted_price_1d": 2878.23,
  "expected_change_pct": 0.09,
  "direction_signal": "↑ Increase",
  "model_confidence_r2": 0.87,
  "recommended_action": "Buy Bias",
  "prediction_status": "ready"
}
```

#### Get portfolio holdings:

```http
GET /portfolio-stocks/?portfolio=1
Authorization: Token abc123...

Response: [Array of enriched stock objects with live prices, indicators, predictions]
```

---

## Future Improvements

1. **Consolidate Stock and PortfolioStock models**
   - Remove Stock model's global unique constraint on symbol
   - Use PortfolioStock as the single source of truth
   - Add cached prediction fields to PortfolioStock

2. **Fix prediction synchronization**
   - Ensure GoldForecastResult updates trigger cascade updates to portfolio holdings
   - Consider materialized views or triggers

3. **Better documentation on model purpose**
   - Current code comments recommend PortfolioStock but API creates Stock
   - This confusion should be resolved

4. **Add test coverage**
   - Especially for the add-stock flow and prediction refresh logic

5. **Consider async prediction updates**
   - Currently on-demand predictions block the request
   - Could use Celery queues for background computation

---

## Key Files Reference

| Component | File |
|-----------|------|
| StockMaster model | `portfolio/models.py:106-127` |
| Portfolio model | `portfolio/models.py:6-34` |
| PortfolioStock model | `portfolio/models.py:73-103` |
| Stock model | `portfolio/models.py:37-70` |
| Default portfolio creation | `portfolio/services.py:48-104` |
| API add-stock endpoint | `api/views.py:118-159` |
| Prediction service | `analytics/services/prediction.py` |
| Bulk population command | `portfolio/management/commands/populate_portfolio_stocks.py` |
| Default portfolio seeding | `portfolio/management/commands/seed_default_portfolios.py` |
| StockMaster seeding | `portfolio/management/commands/seed_stock_master.py` |
| Stock catalog (400 tickers) | `scripts/nifty500_top200.py` |

---

## Related Documentation

- `SEQUENCE_DIAGRAM.md` - Detailed sequence diagrams for portfolio operations
- `pipeline/` - Medallion Architecture data pipeline
- `analytics/` - Prediction and analytics services

---

**Last Updated**: 2026-03-24

**Maintained By**: Portfolio Team (see git history for contributors)
