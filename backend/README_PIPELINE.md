# Data Pipeline README

This document describes how to run and verify the local Bronze/Silver/Gold pipeline in `Project-10/backend`.

## Purpose

Pipeline output powers the frontend portfolio table fields:
- predicted price (1D)
- expected change %
- direction signal
- model confidence (R2)
- PE/fundamental fields
- news ingestion summaries

If pipeline is not run after clone/pull, these fields can appear as `Low Data`.

## Prerequisites

- Conda env: `autosignal`
- Backend dependencies installed:

```powershell
cd backend
conda run -n autosignal pip install -r requirements.txt
```

- DB migrated:

```powershell
conda run -n autosignal python manage.py migrate
```

## Pipeline Modes

Command:

```powershell
conda run -n autosignal python manage.py run_pipeline --mode=<mode>
```

Available modes:
- `prices`: fetches price data (Bronze prices)
- `news`: fetches Economic Times RSS into `BronzeNewsArticle`
- `silver`: computes indicators into `SilverCleanedPrice`
- `gold`: computes `GoldStockSignal` + `GoldForecastResult`
- `all`: runs all major steps in sequence

Recommended first run on fresh setup:

```powershell
conda run -n autosignal python manage.py run_pipeline --mode=all
```

## News Fetcher

News source is RSS-based and deduplicated by URL hash (`article_id`):
- multiple feeds are fetched
- one feed failing does not stop the run
- duplicates are skipped
- `ignore_conflicts=True` keeps reruns safe

Example:

```powershell
conda run -n autosignal python manage.py run_pipeline --mode=news
```

## Gold Forecasts

Gold layer currently uses linear regression for speed and stores results in:
- `GoldForecastResult`
- `GoldStockSignal`

Run only gold:

```powershell
conda run -n autosignal python manage.py run_pipeline --mode=gold
```

## Verification Commands

### 1) Check Gold row counts

```powershell
conda run -n autosignal python manage.py shell -c "from pipeline.models import GoldStockSignal, GoldForecastResult; print('GoldStockSignal:', GoldStockSignal.objects.count()); print('GoldForecastResult:', GoldForecastResult.objects.count())"
```

### 2) Check news row count

```powershell
conda run -n autosignal python manage.py shell -c "from pipeline.models import BronzeNewsArticle; print('BronzeNewsArticle:', BronzeNewsArticle.objects.count())"
```

### 3) Check enriched portfolio API response

```powershell
conda run -n autosignal python manage.py shell -c "from django.contrib.auth import get_user_model; from rest_framework.authtoken.models import Token; from rest_framework.test import APIClient; from portfolio.models import Portfolio; from django.conf import settings; settings.ALLOWED_HOSTS=list(settings.ALLOWED_HOSTS)+['testserver']; u=get_user_model().objects.first(); t,_=Token.objects.get_or_create(user=u); p=Portfolio.objects.filter(user=u,is_default=True).first(); c=APIClient(); c.credentials(HTTP_AUTHORIZATION=f'Token {t.key}'); r=c.get(f'/api/portfolio-stocks/?portfolio={p.id}'); print(r.status_code, len(r.json()))"
```

## Teammate Workflow (after git pull)

Always do:

1. `python manage.py migrate`
2. `python manage.py run_pipeline --mode=all`
3. Start backend/frontend

This ensures local DB has the required analytics/prediction/news state.

## Troubleshooting

### `Low Data` in Stocks table

- Ensure frontend is running from the correct repository path.
- Ensure backend and frontend both point to the same local server.
- Run `run_pipeline --mode=gold`.
- Verify `GET /api/portfolio-stocks/?portfolio=<id>` returns `prediction_status: "ready"` rows.

### News count lower than number of stocks

Expected. News article count is feed-item based, not one-per-stock.

### RSS feed 404 for one source

Expected occasionally; fetcher logs and continues.
