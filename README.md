# Auto Invest AI

Auto Invest AI is a full-stack stock portfolio analytics platform with:
- user portfolios and default sector portfolios
- a 400-stock `StockMaster` catalogue
- Bronze/Silver/Gold data pipeline
- precomputed linear-regression forecasts
- fundamentals/news enrichment for table views

## Tech Stack

| Layer | Technology |
|---|---|
| Backend | Django, Django REST Framework |
| Frontend | React (Vite), Tailwind CSS, Recharts |
| Database | SQLite (local dev), PostgreSQL-ready |
| Data Sources | yfinance, Economic Times RSS |
| ML | pandas, scikit-learn (Linear Regression) |

## Repository Structure

```text
Project-10/
+-- backend/
¦   +-- api/
¦   +-- analytics/
¦   +-- pipeline/
¦   +-- portfolio/
¦   +-- manage.py
+-- frontend/
¦   +-- src/
¦   +-- package.json
+-- docs/
```

## Quick Start

### 1) Backend

```powershell
cd backend
conda run -n autosignal pip install -r requirements.txt
conda run -n autosignal python manage.py migrate
conda run -n autosignal python manage.py runserver
```

### 2) Frontend

```powershell
cd frontend
npm install
npm run dev
```

### 3) Mandatory data bootstrap (after fresh clone/pull)

```powershell
cd backend
conda run -n autosignal python manage.py run_pipeline --mode=all
```

Without this step, portfolio stocks may show `Low Data` because Gold forecasts and other pipeline outputs are not populated yet.

## Current Data Model Notes

- `StockMaster` is the master stock catalogue.
- `PortfolioStock` is the through/link table used by portfolio tables.
- Removing a stock from a portfolio removes only the link row from `PortfolioStock`.
- `StockMaster` is not deleted when a user removes from portfolio.

## Key API Endpoints

### Auth
- `POST /api/register/`
- `POST /api/login/`

### Portfolio
- `GET /api/portfolio/`
- `POST /api/portfolio/`
- `POST /api/portfolio/{id}/add-stock/`
- `DELETE /api/portfolio/{id}/remove-stock/?symbol=TICKER`

### Stocks
- `GET /api/portfolio-stocks/?portfolio={id}`
- `GET /api/stocks/{id}/`

## Teammate Onboarding Checklist

After cloning or pulling from GitHub:

1. Install backend dependencies.
2. Run migrations.
3. Run the pipeline once (`--mode=all`).
4. Start backend + frontend.

If pipeline is not run, DB-backed analytics/predictions will appear empty.

## Dedicated Pipeline Guide

See: [backend/README_PIPELINE.md](backend/README_PIPELINE.md)

## Sequence Diagrams

See: [docs/SEQUENCE_DIAGRAM.md](docs/SEQUENCE_DIAGRAM.md)
