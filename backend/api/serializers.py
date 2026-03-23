from django.contrib.auth.models import User
from rest_framework import serializers

from analytics.models import StockAnalytics
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


class StockAnalyticsSerializer(serializers.ModelSerializer):
    class Meta:
        model = StockAnalytics
        fields = (
            "pe_ratio",
            "discount_level",
            "opportunity_score",
            "graph_data",
            "last_updated",
        )


class StockListSerializer(serializers.ModelSerializer):
    pe_ratio = serializers.FloatField(source="analytics.pe_ratio", read_only=True)
    discount_level = serializers.CharField(
        source="analytics.discount_level",
        read_only=True,
    )
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
            "pe_ratio",
            "discount_level",
        )

    def _price_series(self, obj):
        analytics = getattr(obj, "analytics", None)
        if not analytics:
            return []
        prices = analytics.graph_data.get("price", [])
        return [float(value) for value in prices if isinstance(value, (int, float))]

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

class StockDetailSerializer(serializers.ModelSerializer):
    analytics = StockAnalyticsSerializer(read_only=True)
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
            "analytics",
        )

    def _price_series(self, obj):
        analytics = getattr(obj, "analytics", None)
        if not analytics:
            return []
        prices = analytics.graph_data.get("price", [])
        return [float(value) for value in prices if isinstance(value, (int, float))]

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
