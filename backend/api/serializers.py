from datetime import date, timedelta

from django.contrib.auth.models import User
from rest_framework import serializers

from analytics.data_access import (
    get_fundamentals_bulk,
    get_latest_insights_bulk,
    get_stocks_sentiment_bulk,
)
from portfolio.models import Portfolio, Stock, PortfolioStock


def _infer_currency_from_symbol(symbol: str) -> str:
    value = str(symbol or "").upper()
    if value.endswith(".NS") or value.endswith(".BO"):
        return "INR"
    return "USD"


class RegisterSerializer(serializers.ModelSerializer):
    password = serializers.CharField(write_only=True, min_length=8)

    class Meta:
        model = User
        fields = ("id", "username", "email", "password")

    def create(self, validated_data):
        return User.objects.create_user(**validated_data)


class LoginSerializer(serializers.Serializer):
    username = serializers.CharField()
    password = serializers.CharField(write_only=True)


class AddStockToPortfolioSerializer(serializers.Serializer):
    symbol = serializers.CharField(max_length=30)


class StockAnalyticsSerializer(serializers.Serializer):
    pe_ratio = serializers.FloatField(required=False, allow_null=True)
    discount_level = serializers.CharField(required=False, allow_blank=True, allow_null=True)
    opportunity_score = serializers.FloatField(required=False, allow_null=True)
    graph_data = serializers.JSONField(required=False)
    sentiment_graph_data = serializers.JSONField(required=False)
    last_updated = serializers.DateTimeField(required=False, allow_null=True)


class GoldInsightMixin:
    def _insight_map(self):
        if hasattr(self, "_cached_insight_map"):
            return self._cached_insight_map

        instance = getattr(self, "instance", None)
        tickers = set()

        if instance is None:
            self._cached_insight_map = {}
            return self._cached_insight_map

        if isinstance(instance, (list, tuple)):
            tickers = {obj.symbol for obj in instance if getattr(obj, "symbol", None)}
        elif hasattr(instance, "__iter__") and not isinstance(instance, Stock):
            tickers = {obj.symbol for obj in instance if getattr(obj, "symbol", None)}
        else:
            symbol = getattr(instance, "symbol", None)
            if symbol:
                tickers = {symbol}

        self._cached_insight_map = get_latest_insights_bulk(list(tickers)) if tickers else {}
        return self._cached_insight_map

    def _insight(self, obj):
        return self._insight_map().get(obj.symbol, {})

    def _fundamentals_map(self):
        if hasattr(self, "_cached_fundamentals_map"):
            return self._cached_fundamentals_map

        instance = getattr(self, "instance", None)
        tickers = set()

        if instance is None:
            self._cached_fundamentals_map = {}
            return self._cached_fundamentals_map

        if isinstance(instance, (list, tuple)):
            tickers = {obj.symbol for obj in instance if getattr(obj, "symbol", None)}
        elif hasattr(instance, "__iter__") and not isinstance(instance, Stock):
            tickers = {obj.symbol for obj in instance if getattr(obj, "symbol", None)}
        else:
            symbol = getattr(instance, "symbol", None)
            if symbol:
                tickers = {symbol}

        self._cached_fundamentals_map = get_fundamentals_bulk(list(tickers)) if tickers else {}
        return self._cached_fundamentals_map

    def _fundamentals(self, obj):
        return self._fundamentals_map().get(obj.symbol, {})

    def _sentiment_map(self):
        if hasattr(self, "_cached_sentiment_map"):
            return self._cached_sentiment_map

        instance = getattr(self, "instance", None)
        tickers = set()

        if instance is None:
            self._cached_sentiment_map = {}
            return self._cached_sentiment_map

        if isinstance(instance, (list, tuple)):
            tickers = {obj.symbol for obj in instance if getattr(obj, "symbol", None)}
        elif hasattr(instance, "__iter__") and not isinstance(instance, Stock):
            tickers = {obj.symbol for obj in instance if getattr(obj, "symbol", None)}
        else:
            symbol = getattr(instance, "symbol", None)
            if symbol:
                tickers = {symbol}

        self._cached_sentiment_map = get_stocks_sentiment_bulk(list(tickers)) if tickers else {}
        return self._cached_sentiment_map

    def _sentiment(self, obj):
        return self._sentiment_map().get(obj.symbol, {})


class StockListSerializer(GoldInsightMixin, serializers.ModelSerializer):
    pe_ratio = serializers.SerializerMethodField()
    discount_level = serializers.SerializerMethodField()
    min_price = serializers.SerializerMethodField()
    max_price = serializers.SerializerMethodField()
    closing_price = serializers.SerializerMethodField()
    currency = serializers.SerializerMethodField()
    predicted_price_1d = serializers.FloatField(read_only=True)
    expected_change_pct = serializers.FloatField(read_only=True)
    direction_signal = serializers.CharField(read_only=True)
    model_confidence_r2 = serializers.FloatField(read_only=True)
    prediction_status = serializers.CharField(read_only=True)
    recommended_action = serializers.CharField(read_only=True)
    sentiment_score = serializers.SerializerMethodField()
    sentiment_label = serializers.SerializerMethodField()
    sentiment_source = serializers.SerializerMethodField()

    class Meta:
        model = Stock
        fields = (
            "id",
            "symbol",
            "company_name",
            "current_price",
            "min_price",
            "max_price",
            "closing_price",
            "currency",
            "predicted_price_1d",
            "expected_change_pct",
            "direction_signal",
            "model_confidence_r2",
            "prediction_status",
            "recommended_action",
            "sentiment_score",
            "sentiment_label",
            "sentiment_source",
            "pe_ratio",
            "discount_level",
        )

    def _price_series(self, obj):
        insight = self._insight(obj)
        prices = (insight.get("graph_data") or {}).get("price", [])
        return [float(value) for value in prices if isinstance(value, (int, float))]

    def get_pe_ratio(self, obj):
        fund = self._fundamentals(obj)
        return fund.get("trailing_pe") if fund.get("trailing_pe") is not None else self._insight(obj).get("pe_ratio")

    def get_discount_level(self, obj):
        return self._insight(obj).get("discount_level")

    def get_sentiment_score(self, obj):
        return self._sentiment(obj).get("sentiment_score")

    def get_sentiment_label(self, obj):
        return self._sentiment(obj).get("sentiment_label")

    def get_sentiment_source(self, obj):
        return self._sentiment(obj).get("model_used")

    def get_min_price(self, obj):
        prices = self._price_series(obj)
        if not prices:
            return None
        return round(min(prices), 2)

    def get_max_price(self, obj):
        prices = self._price_series(obj)
        if not prices:
            return None
        return round(max(prices), 2)

    def get_closing_price(self, obj):
        prices = self._price_series(obj)
        if not prices:
            return None
        return round(prices[-1], 2)

    def get_currency(self, obj):
        return _infer_currency_from_symbol(obj.symbol)

class StockDetailSerializer(GoldInsightMixin, serializers.ModelSerializer):
    analytics = serializers.SerializerMethodField()
    portfolio_name = serializers.CharField(source="portfolio.name", read_only=True)
    min_price = serializers.SerializerMethodField()
    max_price = serializers.SerializerMethodField()
    today_price = serializers.SerializerMethodField()
    currency = serializers.SerializerMethodField()
    predicted_price_1d = serializers.FloatField(read_only=True)
    expected_change_pct = serializers.FloatField(read_only=True)
    direction_signal = serializers.CharField(read_only=True)
    model_confidence_r2 = serializers.FloatField(read_only=True)
    prediction_status = serializers.CharField(read_only=True)
    recommended_action = serializers.CharField(read_only=True)
    sentiment_score = serializers.SerializerMethodField()
    sentiment_label = serializers.SerializerMethodField()
    sentiment_source = serializers.SerializerMethodField()

    class Meta:
        model = Stock
        fields = (
            "id",
            "portfolio",
            "portfolio_name",
            "symbol",
            "company_name",
            "sector",
            "current_price",
            "min_price",
            "max_price",
            "today_price",
            "currency",
            "predicted_price_1d",
            "expected_change_pct",
            "direction_signal",
            "model_confidence_r2",
            "prediction_status",
            "recommended_action",
            "sentiment_score",
            "sentiment_label",
            "sentiment_source",
            "analytics",
        )

    def _price_series(self, obj):
        insight = self._insight(obj)
        prices = (insight.get("graph_data") or {}).get("price", [])
        return [float(value) for value in prices if isinstance(value, (int, float))]

    def get_analytics(self, obj):
        from pipeline.models import SilverSentimentScore

        insight = self._insight(obj)
        fund = self._fundamentals(obj)
        pe_ratio = fund.get("trailing_pe")
        if pe_ratio is None:
            pe_ratio = insight.get("pe_ratio")

        cutoff = date.today() - timedelta(days=180)
        sentiment_rows = list(
            SilverSentimentScore.objects
            .filter(ticker=obj.symbol, date__gte=cutoff)
            .order_by("date")
            .values("date", "sentiment_score")
        )
        sentiment_graph_data = {
            "dates": [row["date"].isoformat() for row in sentiment_rows if row.get("date")],
            "scores": [float(row["sentiment_score"]) for row in sentiment_rows if row.get("sentiment_score") is not None],
        }

        if not insight:
            return {
                "pe_ratio": pe_ratio,
                "forward_pe": fund.get("forward_pe"),
                "discount_level": None,
                "opportunity_score": None,
                "graph_data": {},
                "sentiment_graph_data": sentiment_graph_data,
                "last_updated": None,
            }
        return {
            "pe_ratio": pe_ratio,
            "forward_pe": fund.get("forward_pe"),
            "discount_level": insight.get("discount_level"),
            "opportunity_score": insight.get("opportunity_score"),
            "graph_data": insight.get("graph_data") or {},
            "sentiment_graph_data": sentiment_graph_data,
            "last_updated": insight.get("updated_at") or insight.get("date"),
        }

    def get_min_price(self, obj):
        prices = self._price_series(obj)
        if not prices:
            return None
        return round(min(prices), 2)

    def get_max_price(self, obj):
        prices = self._price_series(obj)
        if not prices:
            return None
        return round(max(prices), 2)

    def get_today_price(self, obj):
        prices = self._price_series(obj)
        if not prices:
            return None
        return round(prices[-1], 2)

    def get_currency(self, obj):
        return _infer_currency_from_symbol(obj.symbol)

    def get_sentiment_score(self, obj):
        return self._sentiment(obj).get("sentiment_score")

    def get_sentiment_label(self, obj):
        return self._sentiment(obj).get("sentiment_label")

    def get_sentiment_source(self, obj):
        return self._sentiment(obj).get("model_used")


class PortfolioSerializer(serializers.ModelSerializer):
    is_default = serializers.BooleanField(read_only=True)
    portfolio_type = serializers.CharField(read_only=True)
    geography = serializers.ChoiceField(
        choices=[("IN", "India"), ("US", "US"), ("ALL", "All")],
        required=False,
        default="ALL",
    )
    stock_count = serializers.SerializerMethodField()

    class Meta:
        model = Portfolio
        fields = ("id", "name", "description", "is_default", "portfolio_type", "geography", "stock_count")

    def get_stock_count(self, obj):
        return obj.portfolio_stocks.count()


class PortfolioStockSerializer(serializers.ModelSerializer):
    class Meta:
        model  = PortfolioStock
        fields = ['id', 'ticker', 'company_name', 'sector', 'geography', 'added_at']


class PredictionRunSerializer(serializers.Serializer):
    stock_symbol = serializers.CharField(max_length=30)
    model_type = serializers.ChoiceField(choices=["xgboost", "lstm"])
    prediction_frequency = serializers.ChoiceField(choices=["hourly", "daily", "weekly", "monthly"])
    historical_period = serializers.ChoiceField(choices=["6mo", "1y", "2y", "5y"])


# ─── Telegram OTP Serializers ─────────────────────────────────────

class TelegramQRGenerateSerializer(serializers.Serializer):
    """Generate QR code for Telegram OTP verification."""
    purpose = serializers.ChoiceField(choices=['registration', 'forgot_password', 'reset_password'])
    email = serializers.EmailField(required=False, allow_blank=True)  # For forgot password
    
    def validate(self, data):
        if data['purpose'] in ['forgot_password', 'reset_password'] and not data.get('email'):
            raise serializers.ValidationError("Email is required for password recovery.")
        return data


class TelegramOTPVerifySerializer(serializers.Serializer):
    """Verify OTP and complete authentication flow."""
    ref_id = serializers.CharField(max_length=50)
    otp_code = serializers.CharField(max_length=6, min_length=6)
    username = serializers.CharField(max_length=150, required=False, allow_blank=True)
    password = serializers.CharField(write_only=True, min_length=8, required=False, allow_blank=True)
    email = serializers.EmailField(required=False, allow_blank=True)
    
    def validate_otp_code(self, value):
        if not value.isdigit():
            raise serializers.ValidationError("OTP must contain only digits.")
        return value


class ForgotPasswordSerializer(serializers.Serializer):
    """Request password reset via OTP."""
    email = serializers.EmailField()


class ResetPasswordSerializer(serializers.Serializer):
    """Verify OTP and set new password."""
    ref_id = serializers.CharField(max_length=50)
    otp_code = serializers.CharField(max_length=6, min_length=6)
    new_password = serializers.CharField(write_only=True, min_length=8)
    confirm_password = serializers.CharField(write_only=True, min_length=8)
    
    def validate(self, data):
        if data['new_password'] != data['confirm_password']:
            raise serializers.ValidationError({"confirm_password": "Passwords do not match."})
        return data


class ChatMessageSerializer(serializers.Serializer):
    message = serializers.CharField(max_length=2000)
    session_id = serializers.CharField(max_length=120, required=False, allow_blank=True)
    history = serializers.ListField(
        child=serializers.DictField(),
        required=False,
        default=list,
    )
