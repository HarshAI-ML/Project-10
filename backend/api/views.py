from datetime import date, timedelta

from django.contrib.auth import authenticate
from django.db.models import Max, Min, Q
from rest_framework import mixins, status, viewsets
from rest_framework.authtoken.models import Token
from rest_framework.decorators import action
from rest_framework.permissions import AllowAny
from rest_framework.response import Response

from api.serializers import (
    AddStockToPortfolioSerializer,
    LoginSerializer,
    PortfolioSerializer,
    PredictionRunSerializer,
    RegisterSerializer,
    StockDetailSerializer,
    StockListSerializer,
)
from analytics.data_access import (
    get_fundamentals_bulk,
    get_latest_forecasts_bulk,
    get_latest_price,
    get_latest_signals_bulk,
    get_stock_info,
    search_stocks,
)
from analytics.models import StockAnalytics
from analytics.services.pipeline import generate_and_persist_stock_analytics
from analytics.services.cluster import build_portfolio_clusters, build_global_clusters
from analytics.services.price_prediction import get_prediction_options, run_prediction
from analytics.services.prediction import refresh_stock_prediction
from analytics.services.yahoo_search import (
    fetch_live_stock_comparison,
    fetch_live_stock_detail,
    search_live_stocks,
)
from pipeline.models import SilverCleanedPrice
from portfolio.models import Portfolio, PortfolioStock, Stock
from portfolio.services import create_default_portfolios_for_user, user_has_default_portfolios


class AuthViewSet(viewsets.GenericViewSet):
    """Authentication endpoints for user registration and login."""

    permission_classes = [AllowAny]
    serializer_class = RegisterSerializer

    def get_serializer_class(self):
        if self.action == "login":
            return LoginSerializer
        return RegisterSerializer

    @action(detail=False, methods=["post"], url_path="register")
    def register(self, request):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        user = serializer.save()
        token, _ = Token.objects.get_or_create(user=user)
        
        # Create default portfolios for new user
        create_default_portfolios_for_user(user)
        
        return Response(
            {
                "id": user.id,
                "username": user.username,
                "email": user.email,
                "token": token.key,
            },
            status=status.HTTP_201_CREATED,
        )

    @action(detail=False, methods=["post"], url_path="login")
    def login(self, request):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        user = authenticate(
            username=serializer.validated_data["username"],
            password=serializer.validated_data["password"],
        )
        if not user:
            return Response(
                {"detail": "Invalid credentials."},
                status=status.HTTP_401_UNAUTHORIZED,
            )
        token, _ = Token.objects.get_or_create(user=user)
        
        # Create default portfolios on first login if missing
        if not user_has_default_portfolios(user):
            create_default_portfolios_for_user(user)
            
        return Response(
            {
                "id": user.id,
                "username": user.username,
                "email": user.email,
                "token": token.key,
            }
        )


class PortfolioViewSet(
    mixins.CreateModelMixin,
    mixins.ListModelMixin,
    viewsets.GenericViewSet,
):
    """List/create portfolios and add stocks."""

    serializer_class = PortfolioSerializer

    def get_queryset(self):
        return Portfolio.objects.filter(user=self.request.user).order_by('-is_default', 'name')

    def perform_create(self, serializer):
        serializer.save(user=self.request.user)

    @action(detail=True, methods=["post"], url_path="add-stock")
    def add_stock(self, request, pk=None):
        portfolio = self.get_object()
        serializer = AddStockToPortfolioSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        symbol = serializer.validated_data["symbol"].strip().upper()

        # Look up stock info from the DB catalogue (no yfinance)
        info = get_stock_info(symbol)
        if not info:
            # Try with .NS suffix for Indian stocks entered without it
            if "." not in symbol and "-" not in symbol:
                info = get_stock_info(f"{symbol}.NS")
                if info:
                    symbol = f"{symbol}.NS"

        if not info:
            return Response(
                {"detail": f"Stock '{symbol}' not found in our catalogue (400 supported stocks)."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        latest = get_latest_price(symbol) or {}
        current_price = float(latest.get("close") or 0.0)

        stock, _ = Stock.objects.update_or_create(
            symbol=symbol,
            defaults={
                "portfolio":    portfolio,
                "company_name": info["name"],
                "sector":       info.get("sector") or portfolio.name,
                "current_price": current_price,
            },
        )
        generate_and_persist_stock_analytics(stock)
        refresh_stock_prediction(stock)

        return Response(
            StockListSerializer(stock).data,
            status=status.HTTP_201_CREATED,
        )

    @action(detail=True, methods=["delete"], url_path="remove-stock")
    def remove_stock(self, request, pk=None):
        """
        Remove a stock from a portfolio without touching the StockMaster table.
        Expected query param: ?symbol=RELIANCE.NS
        """
        portfolio = self.get_object()
        symbol = request.query_params.get("symbol", "").strip().upper()

        if not symbol:
            return Response(
                {"detail": "Query param 'symbol' is required."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        deleted_count, _ = PortfolioStock.objects.filter(
            portfolio=portfolio,
            ticker=symbol,
        ).delete()

        # Legacy cleanup only for this user's portfolio row.
        Stock.objects.filter(portfolio=portfolio, symbol=symbol).delete()

        if deleted_count == 0:
            return Response(
                {"detail": f"Stock '{symbol}' not found in portfolio '{portfolio.name}'."},
                status=status.HTTP_404_NOT_FOUND,
            )

        return Response(
            {"deleted": deleted_count, "symbol": symbol},
            status=status.HTTP_200_OK,
        )

    @action(detail=True, methods=["get"], url_path="clusters")
    def clusters(self, request, pk=None):
        portfolio = self.get_object()
        n_clusters_param = request.query_params.get("n_clusters")
        n_clusters = None
        if n_clusters_param:
            try:
                n_clusters = int(n_clusters_param)
            except ValueError:
                pass
        try:
            payload = build_portfolio_clusters(portfolio_id=portfolio.id, n_clusters=n_clusters)
            if payload["status"] != "ok":
                return Response(payload, status=status.HTTP_200_OK)
            return Response(payload)
        except Exception:
            return Response(
                {
                    "portfolio_id": portfolio.id,
                    "status": "error",
                    "detail": "Failed to generate clustering analysis.",
                    "rows": [],
                    "cluster_summary": [],
                    "centroids": [],
                },
                status=status.HTTP_502_BAD_GATEWAY,
            )


class StockViewSet(viewsets.ReadOnlyModelViewSet):
    """Stock list, detail and search endpoints."""

    queryset = Stock.objects.all().select_related("analytics", "portfolio").order_by("id")

    def get_serializer_class(self):
        if self.action == "retrieve":
            return StockDetailSerializer
        return StockListSerializer

    def get_queryset(self):
        queryset = super().get_queryset()
        portfolio_id = self.request.query_params.get("portfolio")
        if portfolio_id:
            queryset = queryset.filter(portfolio_id=portfolio_id)
        return queryset

    @action(detail=False, methods=["get"], url_path="search")
    def search(self, request):
        query = request.query_params.get("q", "").strip()
        queryset = self.get_queryset()
        if query:
            queryset = queryset.filter(
                Q(symbol__icontains=query) | Q(company_name__icontains=query)
            )
        serializer = StockListSerializer(queryset, many=True)
        return Response(serializer.data)

    @action(detail=False, methods=["get"], url_path="live-search")
    def live_search(self, request):
        query = request.query_params.get("q", "").strip()
        limit_param = request.query_params.get("limit", "10")
        try:
            limit = min(max(int(limit_param), 1), 20)
        except ValueError:
            limit = 10

        rows = search_live_stocks(query=query, limit=limit)
        return Response(rows)

    @action(detail=False, methods=["get"], url_path="live-detail")
    def live_detail(self, request):
        symbol = request.query_params.get("symbol", "").strip()
        period = request.query_params.get("period", "1y").strip().lower()
        interval = request.query_params.get("interval", "1d").strip().lower()

        payload = fetch_live_stock_detail(symbol, period=period, interval=interval)
        if not payload:
            return Response(
                {"detail": "Live stock not found."},
                status=status.HTTP_404_NOT_FOUND,
            )
        return Response(payload)

    @action(detail=False, methods=["get"], url_path="live-compare")
    def live_compare(self, request):
        symbol_a = request.query_params.get("symbol_a", "").strip()
        symbol_b = request.query_params.get("symbol_b", "").strip()
        period = request.query_params.get("period", "5y").strip().lower()
        interval = request.query_params.get("interval", "1d").strip().lower()

        if not symbol_a or not symbol_b:
            return Response(
                {"detail": "Both stock symbols are required."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        try:
            payload = fetch_live_stock_comparison(
                symbol_a=symbol_a,
                symbol_b=symbol_b,
                period=period,
                interval=interval,
            )
            return Response(payload)
        except ValueError as exc:
            return Response(
                {"detail": str(exc)},
                status=status.HTTP_400_BAD_REQUEST,
            )
        except Exception:
            return Response(
                {"detail": "Failed to fetch comparison data from Yahoo Finance."},
                status=status.HTTP_502_BAD_GATEWAY,
            )

    @action(detail=True, methods=["delete"], url_path="remove")
    def remove(self, request, pk=None):
        stock = self.get_object()
        stock.delete()
        return Response(status=status.HTTP_204_NO_CONTENT)

    @action(detail=False, methods=["get"], url_path="clusters")
    def clusters(self, request):
        """Global clustering of all stocks across all portfolios."""
        n_clusters_param = request.query_params.get("n_clusters")
        n_clusters = None
        if n_clusters_param:
            try:
                n_clusters = int(n_clusters_param)
            except ValueError:
                pass
        try:
            payload = build_global_clusters(n_clusters=n_clusters)
            if payload["status"] != "ok":
                return Response(payload, status=status.HTTP_200_OK)
            return Response(payload)
        except Exception:
            return Response(
                {
                    "portfolio_id": "global",
                    "status": "error",
                    "detail": "Failed to generate global clustering analysis.",
                    "rows": [],
                    "cluster_summary": [],
                    "centroids": [],
                },
                status=status.HTTP_502_BAD_GATEWAY,
            )


class PredictionViewSet(viewsets.GenericViewSet):
    """Price prediction endpoints."""

    def list(self, request):
        payload = get_prediction_options()
        return Response(payload, status=status.HTTP_200_OK)

    @action(detail=False, methods=["post"], url_path="run")
    def run(self, request):
        serializer = PredictionRunSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        try:
            payload = run_prediction(
                stock_symbol=serializer.validated_data["stock_symbol"],
                model_type=serializer.validated_data["model_type"],
                prediction_frequency=serializer.validated_data["prediction_frequency"],
                historical_period=serializer.validated_data["historical_period"],
                request=request,
            )
            return Response(payload, status=status.HTTP_200_OK)
        except ValueError as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_400_BAD_REQUEST)
        except RuntimeError as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_422_UNPROCESSABLE_ENTITY)
        except Exception:
            return Response(
                {"detail": "Failed to generate prediction. Please try again."},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )

from rest_framework.permissions import IsAuthenticated
from api.serializers import PortfolioStockSerializer

class PortfolioStockViewSet(viewsets.ReadOnlyModelViewSet):
    serializer_class   = PortfolioStockSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        portfolio_id = self.request.query_params.get("portfolio")
        qs = PortfolioStock.objects.filter(portfolio__user=self.request.user)
        if portfolio_id:
            qs = qs.filter(portfolio_id=portfolio_id)
        return qs.order_by("sector", "ticker")

    def list(self, request, *args, **kwargs):
        qs = self.get_queryset()
        tickers = list(qs.values_list("ticker", flat=True))

        latest_dates = (
            SilverCleanedPrice.objects.filter(ticker__in=tickers)
            .values("ticker")
            .annotate(max_date=Max("date"))
        )
        silver_map = {}
        for entry in latest_dates:
            row = (
                SilverCleanedPrice.objects.filter(
                    ticker=entry["ticker"],
                    date=entry["max_date"],
                )
                .values(
                    "close",
                    "ma_20",
                    "rsi_14",
                    "macd",
                    "daily_return",
                    "volatility_20",
                    "bb_upper",
                    "bb_lower",
                )
                .first()
            )
            if row:
                silver_map[entry["ticker"]] = row

        cutoff = date.today() - timedelta(days=365)
        ranges = (
            SilverCleanedPrice.objects.filter(ticker__in=tickers, date__gte=cutoff)
            .values("ticker")
            .annotate(week_high=Max("high"), week_low=Min("low"))
        )
        range_map = {r["ticker"]: r for r in ranges}
        fund_map = get_fundamentals_bulk(tickers)
        signal_map = get_latest_signals_bulk(tickers)
        forecast_map = get_latest_forecasts_bulk(tickers)

        old_stocks = Stock.objects.filter(symbol__in=tickers)
        old_stock_map = {s.symbol: s for s in old_stocks}

        try:
            analytics = StockAnalytics.objects.filter(stock__symbol__in=tickers).select_related("stock")
            analytics_map = {a.stock.symbol: a for a in analytics}
        except Exception:
            analytics_map = {}

        results = []
        for ps in qs:
            try:
                ticker = ps.ticker
                silver = silver_map.get(ticker, {})
                rng = range_map.get(ticker, {})
                old = old_stock_map.get(ticker)
                ana = analytics_map.get(ticker)
                fund = fund_map.get(ticker, {})
                signal_data = signal_map.get(ticker, {})
                forecast_data = forecast_map.get(ticker, {})

                daily_ret = silver.get("daily_return")
                direction = forecast_data.get("direction")
                if not direction:
                    direction = "Increase" if daily_ret is not None and daily_ret >= 0 else "Decrease" if daily_ret is not None else ""
                exp_change = forecast_data.get("expected_change_pct")
                if exp_change is None:
                    exp_change = round(daily_ret * 100, 2) if daily_ret is not None else None

                results.append(
                    {
                        "id": old.id if old else None,
                        "symbol": ticker,
                        "ticker": ticker,
                        "company_name": ps.company_name,
                        "sector": ps.sector,
                        "geography": ps.geography,
                        "current_price": silver.get("close"),
                        "min_price": rng.get("week_low"),
                        "max_price": rng.get("week_high"),
                        "predicted_price_1d": forecast_data.get("predicted_price"),
                        "expected_change_pct": exp_change,
                        "direction_signal": direction,
                        "model_confidence_r2": forecast_data.get("confidence_r2"),
                        "recommended_action": signal_data.get("signal", ""),
                        "prediction_status": "ready" if forecast_data else "insufficient_data",
                        "signal": signal_data.get("signal", ""),
                        "signal_confidence": signal_data.get("confidence"),
                        "pe_ratio": fund.get("trailing_pe"),
                        "forward_pe": fund.get("forward_pe"),
                        "profit_margin": fund.get("profit_margin"),
                        "revenue_growth": fund.get("revenue_growth"),
                        "market_cap": fund.get("market_cap"),
                        "beta": fund.get("beta"),
                        "eps_trailing": fund.get("eps_trailing"),
                        "return_on_equity": fund.get("return_on_equity"),
                        "discount_level": ana.discount_level if ana else None,
                        "rsi_14": signal_data.get("rsi_14") or silver.get("rsi_14"),
                        "ma_20": silver.get("ma_20"),
                        "macd": silver.get("macd"),
                    }
                )
            except Exception:
                results.append(
                    {
                        "id": None,
                        "symbol": ps.ticker,
                        "ticker": ps.ticker,
                        "company_name": ps.company_name,
                        "sector": ps.sector,
                        "geography": ps.geography,
                        "current_price": None,
                        "min_price": None,
                        "max_price": None,
                        "predicted_price_1d": None,
                        "expected_change_pct": None,
                        "direction_signal": "",
                        "model_confidence_r2": None,
                        "recommended_action": None,
                        "prediction_status": "insufficient_data",
                        "signal": "",
                        "signal_confidence": None,
                        "pe_ratio": None,
                        "forward_pe": None,
                        "profit_margin": None,
                        "revenue_growth": None,
                        "market_cap": None,
                        "beta": None,
                        "eps_trailing": None,
                        "return_on_equity": None,
                        "discount_level": None,
                        "rsi_14": None,
                        "ma_20": None,
                        "macd": None,
                    }
                )

        return Response(results)
