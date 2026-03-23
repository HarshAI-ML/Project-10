"""
Portfolio services - business logic for portfolio creation and management.
"""
import logging

from django.contrib.auth import get_user_model

from portfolio.models import Portfolio, PortfolioStock, StockMaster

logger = logging.getLogger(__name__)

User = get_user_model()

INDIAN_SECTOR_PORTFOLIOS = [
    {"name": "Nifty Auto",        "description": "Automobile and auto components sector stocks",          "sectors": ["Automobile and Auto Components"],                    "geography": "IN"},
    {"name": "Nifty Bank",        "description": "Banking and financial services sector stocks",          "sectors": ["Financial Services"],                                "geography": "IN"},
    {"name": "Nifty Commodities", "description": "Commodities including metals, mining and materials",   "sectors": ["Metals & Mining", "Chemicals"],                      "geography": "IN"},
    {"name": "Nifty CPSE",        "description": "Central Public Sector Enterprises",                    "sectors": ["Oil Gas & Consumable Fuels", "Power", "Construction"],"geography": "IN"},
    {"name": "Nifty Energy",      "description": "Energy sector including oil, gas and power",           "sectors": ["Oil Gas & Consumable Fuels", "Power"],               "geography": "IN"},
    {"name": "Nifty FMCG",        "description": "Fast moving consumer goods sector",                    "sectors": ["Fast Moving Consumer Goods"],                        "geography": "IN"},
    {"name": "Nifty IT",          "description": "Information technology sector",                        "sectors": ["Information Technology"],                            "geography": "IN"},
    {"name": "Nifty Media",       "description": "Media and entertainment sector",                       "sectors": ["Consumer Services"],                                 "geography": "IN"},
    {"name": "Nifty Metal",       "description": "Metals and mining sector",                             "sectors": ["Metals & Mining"],                                   "geography": "IN"},
    {"name": "Nifty MNC",         "description": "Multinational companies listed in India",              "sectors": ["Consumer Durables", "Capital Goods"],                "geography": "IN"},
    {"name": "Nifty Pharma",      "description": "Pharmaceutical and healthcare sector",                 "sectors": ["Healthcare"],                                        "geography": "IN"},
    {"name": "Nifty PSE",         "description": "Public sector enterprises",                            "sectors": ["Services", "Telecommunication"],                     "geography": "IN"},
    {"name": "Nifty PSU Bank",    "description": "Public sector bank stocks",                            "sectors": ["Financial Services"],                                "geography": "IN"},
    {"name": "Nifty Realty",      "description": "Real estate sector stocks",                            "sectors": ["Realty", "Construction Materials"],                  "geography": "IN"},
]

US_SECTOR_PORTFOLIOS = [
    {"name": "US Basic Materials",       "description": "Basic materials including chemicals and mining",      "sectors": ["Materials"],               "geography": "US"},
    {"name": "US Communication Services","description": "Communication services and media",                   "sectors": ["Communication Services"],  "geography": "US"},
    {"name": "US Consumer Cyclical",     "description": "Consumer discretionary and cyclical stocks",         "sectors": ["Consumer Discretionary"],  "geography": "US"},
    {"name": "US Consumer Defensive",    "description": "Consumer staples and defensive stocks",              "sectors": ["Consumer Staples"],        "geography": "US"},
    {"name": "US Energy",                "description": "Energy sector including oil, gas and renewables",    "sectors": ["Energy"],                  "geography": "US"},
    {"name": "US Financial",             "description": "Financial services, banking and insurance",          "sectors": ["Financial Services"],      "geography": "US"},
    {"name": "US Healthcare",            "description": "Healthcare, pharma and biotech",                     "sectors": ["Healthcare"],              "geography": "US"},
    {"name": "US Industrials",           "description": "Industrial and manufacturing companies",             "sectors": ["Industrials"],             "geography": "US"},
    {"name": "US Real Estate",           "description": "Real estate investment trusts and property",         "sectors": ["Real Estate"],             "geography": "US"},
    {"name": "US Technology",            "description": "Technology hardware, software and semiconductors",   "sectors": ["Technology"],              "geography": "US"},
    {"name": "US Utilities",             "description": "Utilities including electric, gas and water",        "sectors": ["Utilities"],               "geography": "US"},
]

ALL_DEFAULT_PORTFOLIOS = INDIAN_SECTOR_PORTFOLIOS + US_SECTOR_PORTFOLIOS


def create_default_portfolios_for_user(user) -> dict:
    """
    Create all 25 default sector portfolios for a user if they don't exist yet.
    Uses PortfolioStock through table - never modifies the Stock master table.
    Idempotent - safe to call multiple times.
    """
    created_count = 0
    skipped_count = 0
    total_stocks = 0

    for config in ALL_DEFAULT_PORTFOLIOS:
        portfolio, was_created = Portfolio.objects.get_or_create(
            user=user,
            name=config['name'],
            is_default=True,
            defaults={
                'description': config['description'],
                'portfolio_type': 'default',
                'geography': config['geography'],
            },
        )

        if not was_created:
            skipped_count += 1
            continue

        stocks = StockMaster.objects.filter(
            sector__in=config['sectors'],
            geography=config['geography'],
            is_active=True,
        )

        entries = []
        for stock in stocks:
            entries.append(
                PortfolioStock(
                    portfolio=portfolio,
                    stock_master=stock,
                    ticker=stock.ticker,
                    company_name=stock.name,
                    sector=stock.sector,
                    geography=stock.geography,
                )
            )

        if entries:
            PortfolioStock.objects.bulk_create(entries, ignore_conflicts=True)

        total_stocks += len(entries)
        created_count += 1
        logger.info("Portfolio '%s': %s stocks for user %s", portfolio.name, len(entries), user.username)

    return {
        'created': created_count,
        'skipped': skipped_count,
        'total_stocks': total_stocks,
    }


def user_has_default_portfolios(user) -> bool:
    """Check if user already has default portfolios."""
    return Portfolio.objects.filter(user=user, is_default=True).exists()
