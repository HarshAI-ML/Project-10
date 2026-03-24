from django.db import models


class BronzeStockPrice(models.Model):
    """
    Raw OHLCV data from yfinance. Append-only — never update or delete rows.
    One row per ticker per date per fetch_run.
    """
    ticker        = models.CharField(max_length=30, db_index=True)
    company       = models.CharField(max_length=200)
    date          = models.DateField(db_index=True)
    open          = models.FloatField(null=True)
    high          = models.FloatField(null=True)
    low           = models.FloatField(null=True)
    close         = models.FloatField(null=True)
    volume        = models.BigIntegerField(null=True)
    source        = models.CharField(max_length=50, default='yfinance')
    ingested_at   = models.DateTimeField(auto_now_add=True)
    fetch_run_id  = models.CharField(max_length=50)  # UUID per pipeline run

    class Meta:
        indexes = [
            models.Index(fields=['ticker', 'date']),
        ]
        ordering = ['-date']

    def __str__(self):
        return f"{self.ticker} | {self.date} | close={self.close}"


class BronzeNewsArticle(models.Model):
    """
    Raw news headlines. Append-only.
    """
    article_id    = models.CharField(max_length=64, unique=True)
    title         = models.TextField()
    url           = models.URLField(max_length=500)
    description   = models.TextField(blank=True)
    published_at  = models.CharField(max_length=100)
    company_tags  = models.CharField(max_length=500, blank=True)
    source        = models.CharField(max_length=100, default='economic_times')
    source_quality = models.FloatField(default=0.8)
    ingested_at   = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-ingested_at']

    def __str__(self):
        return f"{self.title[:60]} | {self.source}"


class PipelineRun(models.Model):
    """
    Tracks each pipeline execution for monitoring and debugging.
    """
    STATUS_CHOICES = [
        ('running',  'Running'),
        ('success',  'Success'),
        ('partial',  'Partial'),
        ('failed',   'Failed'),
    ]
    run_id          = models.CharField(max_length=50, unique=True)
    run_type        = models.CharField(max_length=50)  # 'hourly_prices', 'daily_news', 'full'
    status          = models.CharField(max_length=20, choices=STATUS_CHOICES, default='running')
    started_at      = models.DateTimeField(auto_now_add=True)
    completed_at    = models.DateTimeField(null=True, blank=True)
    stocks_total    = models.IntegerField(default=0)
    stocks_success  = models.IntegerField(default=0)
    stocks_failed   = models.IntegerField(default=0)
    error_log       = models.TextField(blank=True)
    notes           = models.TextField(blank=True)

    class Meta:
        ordering = ['-started_at']

    def __str__(self):
        return f"{self.run_type} | {self.status} | {self.started_at}"

class SilverCleanedPrice(models.Model):
    """
    Cleaned and enriched price data computed from BronzeStockPrice.
    One row per ticker per date. Recomputed on each Silver run.
    """
    ticker          = models.CharField(max_length=30, db_index=True)
    company         = models.CharField(max_length=200, blank=True)
    sector          = models.CharField(max_length=100, blank=True)
    geography       = models.CharField(max_length=5, blank=True)
    date            = models.DateField(db_index=True)

    # Raw OHLCV (copied from Bronze)
    open            = models.FloatField(null=True)
    high            = models.FloatField(null=True)
    low             = models.FloatField(null=True)
    close           = models.FloatField(null=True)
    volume          = models.BigIntegerField(null=True)

    # Returns
    daily_return    = models.FloatField(null=True)   # (close - prev_close) / prev_close
    log_return      = models.FloatField(null=True)   # log(close / prev_close)

    # Moving averages
    ma_5            = models.FloatField(null=True)
    ma_20           = models.FloatField(null=True)
    ma_50           = models.FloatField(null=True)
    ma_200          = models.FloatField(null=True)

    # Volatility
    volatility_20   = models.FloatField(null=True)   # 20-day rolling std of daily_return

    # RSI
    rsi_14          = models.FloatField(null=True)   # 14-day RSI

    # MACD
    macd            = models.FloatField(null=True)   # MACD line (EMA12 - EMA26)
    macd_signal     = models.FloatField(null=True)   # 9-day EMA of MACD
    macd_hist       = models.FloatField(null=True)   # MACD - signal

    # Bollinger Bands
    bb_upper        = models.FloatField(null=True)   # MA20 + 2*std
    bb_lower        = models.FloatField(null=True)   # MA20 - 2*std
    bb_width        = models.FloatField(null=True)   # (upper - lower) / MA20

    # Price vs MA signals
    price_vs_ma20   = models.FloatField(null=True)   # (close - ma_20) / ma_20 * 100
    price_vs_ma50   = models.FloatField(null=True)   # (close - ma_50) / ma_50 * 100

    # Processing metadata
    processed_at    = models.DateTimeField(auto_now=True)
    source_run_id   = models.CharField(max_length=50, blank=True)

    class Meta:
        indexes = [
            models.Index(fields=['ticker', 'date']),
        ]
        ordering = ['-date']
        unique_together = [['ticker', 'date']]

    def __str__(self):
        return f"{self.ticker} | {self.date} | close={self.close} | rsi={self.rsi_14}"


class BronzeStockFundamentals(models.Model):
    """
    Raw fundamentals fetched from yfinance once per stock.
    Refresh by rerunning: python manage.py fetch_fundamentals
    Append-only - new fetch creates new row, old rows preserved.
    """
    ticker = models.CharField(max_length=30, db_index=True)
    company = models.CharField(max_length=200, blank=True)
    sector = models.CharField(max_length=100, blank=True)
    geography = models.CharField(max_length=5, blank=True)

    # Valuation
    trailing_pe = models.FloatField(null=True)
    forward_pe = models.FloatField(null=True)
    price_to_book = models.FloatField(null=True)
    price_to_sales = models.FloatField(null=True)
    enterprise_value = models.FloatField(null=True)
    ev_to_ebitda = models.FloatField(null=True)

    # Profitability
    profit_margin = models.FloatField(null=True)
    operating_margin = models.FloatField(null=True)
    gross_margin = models.FloatField(null=True)
    return_on_equity = models.FloatField(null=True)
    return_on_assets = models.FloatField(null=True)

    # Growth
    revenue_growth = models.FloatField(null=True)
    earnings_growth = models.FloatField(null=True)
    eps_trailing = models.FloatField(null=True)
    eps_forward = models.FloatField(null=True)

    # Size
    market_cap = models.FloatField(null=True)
    total_revenue = models.FloatField(null=True)
    free_cashflow = models.FloatField(null=True)

    # Risk
    debt_to_equity = models.FloatField(null=True)
    current_ratio = models.FloatField(null=True)
    beta = models.FloatField(null=True)

    # Price range
    week52_high = models.FloatField(null=True)
    week52_low = models.FloatField(null=True)
    dividend_yield = models.FloatField(null=True)

    # Metadata
    fetched_at = models.DateTimeField(auto_now_add=True)
    source = models.CharField(max_length=50, default="yfinance")

    class Meta:
        ordering = ["-fetched_at"]
        indexes = [models.Index(fields=["ticker"])]

    def __str__(self):
        return f"{self.ticker} | PE={self.trailing_pe} | fetched={self.fetched_at.date()}"


class GoldStockSignal(models.Model):
    """
    Pre-computed Buy/Sell/Hold signals from Silver indicators.
    Recomputed daily by run_pipeline --mode=gold
    """

    SIGNAL_CHOICES = [
        ("BUY", "Buy"),
        ("SELL", "Sell"),
        ("HOLD", "Hold"),
        ("NEUTRAL", "Neutral"),
    ]
    ticker = models.CharField(max_length=30, db_index=True)
    date = models.DateField(db_index=True)

    # Final signal
    signal = models.CharField(max_length=10, choices=SIGNAL_CHOICES, default="NEUTRAL")
    confidence = models.FloatField(default=0.0)

    # Component signals
    rsi_signal = models.CharField(max_length=10, blank=True)
    macd_signal = models.CharField(max_length=10, blank=True)
    ma_signal = models.CharField(max_length=10, blank=True)

    # Price snapshot at signal time
    close = models.FloatField(null=True)
    rsi_14 = models.FloatField(null=True)
    macd = models.FloatField(null=True)
    macd_signal_line = models.FloatField(null=True)
    ma_50 = models.FloatField(null=True)
    price_vs_ma20 = models.FloatField(null=True)

    computed_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = [["ticker", "date"]]
        ordering = ["-date"]
        indexes = [models.Index(fields=["ticker", "date"])]

    def __str__(self):
        return f"{self.ticker} | {self.date} | {self.signal} ({self.confidence:.0%})"


class GoldForecastResult(models.Model):
    """
    Pre-computed price forecasts from Linear Regression.
    Updated daily by run_pipeline --mode=gold
    """

    ticker = models.CharField(max_length=30, db_index=True)
    forecast_date = models.DateField()
    predicted_price = models.FloatField()
    current_price = models.FloatField(null=True)
    expected_change_pct = models.FloatField(null=True)
    direction = models.CharField(max_length=20, blank=True)
    model_type = models.CharField(max_length=30, default="linear_regression")
    confidence_r2 = models.FloatField(null=True)
    horizon_days = models.IntegerField(default=1)
    computed_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = [["ticker", "forecast_date", "model_type"]]
        ordering = ["-forecast_date"]
        indexes = [models.Index(fields=["ticker", "forecast_date"])]

    def __str__(self):
        return f"{self.ticker} | {self.forecast_date} | {self.predicted_price:.2f} ({self.model_type})"


class GoldStockInsight(models.Model):
    """
    High-level analytics insights for a stock.
    Produced by analytics pipeline and stored in Gold for serving/UI.
    """

    ticker = models.CharField(max_length=30, db_index=True)
    date = models.DateField(db_index=True)
    pe_ratio = models.FloatField(default=0.0)
    discount_level = models.CharField(max_length=50, default="UNKNOWN")
    opportunity_score = models.FloatField(default=0.0)
    graph_data = models.JSONField(default=dict)
    computed_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        unique_together = [["ticker", "date"]]
        ordering = ["-date"]
        indexes = [models.Index(fields=["ticker", "date"])]

    def __str__(self):
        return f"{self.ticker} | {self.date} | {self.discount_level} | {self.opportunity_score}"


class SilverSentimentScore(models.Model):
    ticker = models.CharField(max_length=30, db_index=True)
    date = models.DateField(db_index=True)
    sentiment_score = models.FloatField()
    sentiment_label = models.CharField(max_length=20)
    article_count = models.IntegerField(default=0)
    finbert_score = models.FloatField(null=True)
    momentum_score = models.FloatField(null=True)
    technical_score = models.FloatField(null=True)
    model_used = models.CharField(max_length=50, default="finbert+price")
    text_mode = models.CharField(max_length=10, default="both")
    computed_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = [["ticker", "date"]]
        ordering = ["-date"]
        indexes = [models.Index(fields=["ticker", "date"])]

    def __str__(self):
        return f"{self.ticker} | {self.date} | {self.sentiment_score:.2f} ({self.sentiment_label})"


class GoldSectorSentiment(models.Model):
    sector = models.CharField(max_length=100, db_index=True)
    geography = models.CharField(max_length=5, blank=True, db_index=True)
    date = models.DateField(db_index=True)
    sentiment_score = models.FloatField()
    sentiment_label = models.CharField(max_length=20)
    stock_count = models.IntegerField(default=0)
    computed_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = [["sector", "geography", "date"]]
        ordering = ["-date", "sector"]
        indexes = [models.Index(fields=["sector", "geography", "date"])]

    def __str__(self):
        return f"{self.sector} ({self.geography}) | {self.date} | {self.sentiment_score:.2f}"
