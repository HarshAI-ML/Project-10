from datetime import date, timedelta
import threading
import logging
import os
from django.contrib.auth import authenticate
from django.contrib.auth.models import User
from django.db.models import Max, Min, Q
from rest_framework import mixins, status, viewsets
from rest_framework.authtoken.models import Token
from rest_framework.decorators import action
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.views import APIView

from api.serializers import (
    AddStockToPortfolioSerializer,
    ForgotPasswordSerializer,
    LoginSerializer,
    PortfolioSerializer,
    PredictionRunSerializer,
    RegisterSerializer,
    ResetPasswordSerializer,
    ChatMessageSerializer,
    StockDetailSerializer,
    StockListSerializer,
    TelegramOTPVerifySerializer,
    TelegramQRGenerateSerializer,
)
from accounts.models import TelegramOTP
from accounts.telegram_utils import (
    generate_qr_code_with_ref,
    send_otp_via_telegram,
    send_password_reset_message,
    send_telegram_update_response,
)
from analytics.data_access import (
    get_fundamentals_bulk,
    get_latest_forecasts_bulk,
    get_latest_insights_bulk,
    get_latest_price,
    get_latest_signals_bulk,
    get_sector_sentiment,
    get_stocks_sentiment_bulk,
    get_stock_info,
    search_stocks,
)
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
from api.chatbot_service import generate_chat_response

logger = logging.getLogger(__name__)


class AuthViewSet(viewsets.GenericViewSet):
    """Authentication endpoints for user registration and login."""

    permission_classes = [AllowAny]
    serializer_class = RegisterSerializer

    def _create_portfolios_safe(self, user):
        """Create default portfolios in background without breaking auth flow."""
        try:
            create_default_portfolios_for_user(user)
        except Exception as e:
            logger.error(f"Failed to create default portfolios for user_id={user.id}: {str(e)}")

    def get_serializer_class(self):
        if self.action == "login":
            return LoginSerializer
        elif self.action == "telegram_generate_qr":
            return TelegramQRGenerateSerializer
        elif self.action == "telegram_verify_otp":
            return TelegramOTPVerifySerializer
        elif self.action == "forgot_password":
            return ForgotPasswordSerializer
        elif self.action == "reset_password":
            return ResetPasswordSerializer
        return RegisterSerializer

    @action(detail=False, methods=["post"], url_path="register")
    def register(self, request):
        # Registration MUST be performed through Telegram OTP flow.
        # The `/telegram-otp/generate-qr/` and `/telegram-otp/verify/` endpoints
        # enforce OTP verification before user creation.
        return Response(
            {
                "detail": "Registration requires Telegram OTP verification. Use /telegram-register flow." 
            },
            status=status.HTTP_403_FORBIDDEN,
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
        
        # Create default portfolios asynchronously if missing
        if not user_has_default_portfolios(user):
            thread = threading.Thread(target=self._create_portfolios_safe, args=(user,), daemon=True)
            thread.start()
            
        return Response(
            {
                "id": user.id,
                "username": user.username,
                "email": user.email,
                "token": token.key,
            }
        )

    # ─── Telegram OTP Endpoints ───────────────────────────────────────

    def telegram_generate_qr(self, request):
        """Generate QR code for Telegram OTP verification."""
        serializer = TelegramQRGenerateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        
        purpose = serializer.validated_data["purpose"]
        email = serializer.validated_data.get("email")
        
        try:
            # Generate reference ID and OTP
            ref_id = TelegramOTP.generate_ref_id()
            otp_code = TelegramOTP.generate_otp()
            expires_at = TelegramOTP.generate_expiry()
            
            # Create OTP record
            otp_obj = TelegramOTP.objects.create(
                ref_id=ref_id,
                otp_code=otp_code,
                expires_at=expires_at,
                purpose=purpose,
                email=email,
            )
            
            # Generate QR code
            qr_data = generate_qr_code_with_ref(ref_id)
            
            return Response(
                {
                    "ref_id": ref_id,
                    "qr_code_base64": qr_data["qr_code_base64"],
                    "telegram_url": qr_data["telegram_url"],
                    "expires_in_seconds": 600,
                },
                status=status.HTTP_201_CREATED,
            )
        except Exception as e:
            logger.error(f"Failed to generate QR code: {str(e)}")
            return Response(
                {"detail": "Failed to generate QR code. Please try again."},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )

    def telegram_verify_otp(self, request):
        """Verify OTP and complete registration/password reset."""
        serializer = TelegramOTPVerifySerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        
        ref_id = serializer.validated_data["ref_id"]
        otp_code = serializer.validated_data["otp_code"]
        username = serializer.validated_data.get("username", "").strip()
        password = serializer.validated_data.get("password", "").strip()
        email = serializer.validated_data.get("email", "").strip()
        
        try:
            # Get OTP record
            otp_obj = TelegramOTP.objects.get(ref_id=ref_id)

            # Handle different purposes
            if otp_obj.purpose == "registration":
                has_details = all([username, password, email])

                # If OTP was not verified earlier, validate it now.
                if not otp_obj.is_verified:
                    if not otp_obj.is_valid(otp_code):
                        return Response(
                            {"detail": "Invalid or expired OTP."},
                            status=status.HTTP_400_BAD_REQUEST,
                        )

                    # Phase 1: OTP-only verification (unlock account details step).
                    if not has_details:
                        otp_obj.mark_verified()
                        return Response(
                            {
                                "message": "OTP verified. Continue to enter account details.",
                                "ref_id": ref_id,
                            },
                            status=status.HTTP_200_OK,
                        )
                else:
                    # Already verified from phase 1.
                    if not has_details:
                        return Response(
                            {
                                "message": "OTP already verified. Continue to enter account details.",
                                "ref_id": ref_id,
                            },
                            status=status.HTTP_200_OK,
                        )

                if otp_obj.user_id:
                    return Response(
                        {"detail": "This OTP session is already used for registration."},
                        status=status.HTTP_400_BAD_REQUEST,
                    )

                # Validate required fields for registration
                if not has_details:
                    return Response(
                        {"detail": "Username, password, and email are required."},
                        status=status.HTTP_400_BAD_REQUEST,
                    )
                
                # Check if user already exists
                if User.objects.filter(username=username).exists():
                    return Response(
                        {"detail": "Username already exists."},
                        status=status.HTTP_400_BAD_REQUEST,
                    )
                
                # Create user
                user = User.objects.create_user(
                    username=username,
                    email=email,
                    password=password,
                )
                
                # Mark OTP as verified/consumed
                otp_obj.user = user
                otp_obj.mark_verified()
                
                # Get/create token
                token, _ = Token.objects.get_or_create(user=user)
                
                # Create default portfolios asynchronously
                thread = threading.Thread(target=self._create_portfolios_safe, args=(user,), daemon=True)
                thread.start()
                
                return Response(
                    {
                        "id": user.id,
                        "username": user.username,
                        "email": user.email,
                        "token": token.key,
                    },
                    status=status.HTTP_201_CREATED,
                )
            
            elif otp_obj.purpose == "reset_password":
                # Validate OTP
                if not otp_obj.is_valid(otp_code):
                    return Response(
                        {"detail": "Invalid or expired OTP."},
                        status=status.HTTP_400_BAD_REQUEST,
                    )
                # For password reset - OTP is verified, password will be set in next step
                otp_obj.mark_verified()
                
                return Response(
                    {
                        "message": "OTP verified. Proceed to set new password.",
                        "ref_id": ref_id,
                    },
                    status=status.HTTP_200_OK,
                )
            
            else:
                return Response(
                    {"detail": "Invalid purpose."},
                    status=status.HTTP_400_BAD_REQUEST,
                )
        
        except TelegramOTP.DoesNotExist:
            return Response(
                {"detail": "Invalid reference ID."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        except Exception as e:
            logger.error(f"OTP verification failed: {str(e)}")
            return Response(
                {"detail": "OTP verification failed. Please try again."},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )

    @action(detail=False, methods=["post"], url_path="telegram-webhook", permission_classes=[AllowAny])
    def telegram_webhook(self, request):
        """Handle incoming Telegram bot webhook updates for /start flow."""
        print("WEBHOOK HIT:", request.data)
        data = request.data
        message = data.get("message") or data.get("edited_message")

        if not message:
            # A non-message update (inline query / callback query) is ignored.
            return Response({"status": "ignored"}, status=status.HTTP_200_OK)

        text = (message.get("text") or "").strip()
        chat = message.get("chat", {})
        from_user = message.get("from", {})
        chat_id = chat.get("id")

        if not text.startswith("/start") or not chat_id:
            return Response({"status": "no-action"}, status=status.HTTP_200_OK)

        ref_id = text.replace("/start", "", 1).strip().split()[0] if len(text.split()) > 1 else ""
        if not ref_id:
            send_telegram_update_response(chat_id, "Please use the QR code from AUTO INVEST to start registration.")
            return Response({"status": "missing_ref"}, status=status.HTTP_200_OK)

        try:
            otp_obj = TelegramOTP.objects.filter(ref_id=ref_id, is_verified=False).last()
            if not otp_obj:
                send_telegram_update_response(chat_id, "This code is invalid or has expired. Please try again.")
                return Response({"status": "invalid_ref"}, status=status.HTTP_200_OK)

            if otp_obj.is_expired():
                send_telegram_update_response(chat_id, "The OTP session has expired. Please request a new QR code.")
                return Response({"status": "expired"}, status=status.HTTP_200_OK)

            otp_obj.telegram_user_id = str(chat_id)
            otp_obj.telegram_username = from_user.get("username") or from_user.get("first_name")
            otp_obj.save()

            sent = send_otp_via_telegram(chat_id, otp_obj.otp_code, ref_id=ref_id)
            if not sent:
                logger.error(f"Failed to send OTP via Telegram for ref_id={ref_id} chat_id={chat_id}")
                return Response({"status": "otp_send_failed"}, status=status.HTTP_200_OK)
            return Response({"status": "otp_sent"}, status=status.HTTP_200_OK)

        except Exception as e:
            logger.error(f"Telegram webhook processing failed: {str(e)}")
            return Response({"status": "error", "detail": str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

    def forgot_password(self, request):
        """Initiate forgot password flow."""
        serializer = ForgotPasswordSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        
        email = serializer.validated_data["email"]
        
        try:
            # Check if user exists
            user = User.objects.filter(email=email).first()
            
            if not user:
                # Don't reveal if email exists for security
                return Response(
                    {"message": "If an account exists, you will receive instructions."},
                    status=status.HTTP_200_OK,
                )
            
            # Create OTP for password reset
            ref_id = TelegramOTP.generate_ref_id()
            otp_code = TelegramOTP.generate_otp()
            expires_at = TelegramOTP.generate_expiry()
            
            otp_obj = TelegramOTP.objects.create(
                ref_id=ref_id,
                otp_code=otp_code,
                expires_at=expires_at,
                purpose='reset_password',
                email=email,
                user=user,
            )
            
            # Generate QR code for Telegram
            qr_data = generate_qr_code_with_ref(ref_id)
            
            return Response(
                {
                    "ref_id": ref_id,
                    "qr_code_base64": qr_data["qr_code_base64"],
                    "telegram_url": qr_data["telegram_url"],
                    "message": "Scan the QR code with Telegram to verify your identity.",
                    "expires_in_seconds": 600,
                },
                status=status.HTTP_200_OK,
            )
        
        except Exception as e:
            logger.error(f"Forgot password failed: {str(e)}")
            return Response(
                {"detail": "Failed to initiate password reset. Please try again."},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )

    def reset_password(self, request):
        """Reset password after OTP verification."""
        serializer = ResetPasswordSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        
        ref_id = serializer.validated_data["ref_id"]
        otp_code = serializer.validated_data["otp_code"]
        new_password = serializer.validated_data["new_password"]
        
        try:
            otp_obj = TelegramOTP.objects.get(ref_id=ref_id)

            # Enforce two-step flow:
            # 1) OTP must be verified on the OTP step (`telegram_verify_otp`)
            # 2) The same OTP code must be provided again for reset confirmation
            if not otp_obj.is_verified:
                return Response(
                    {"detail": "OTP not verified. Please verify OTP first."},
                    status=status.HTTP_400_BAD_REQUEST,
                )

            if otp_obj.is_expired() or otp_obj.otp_code != otp_code:
                return Response(
                    {"detail": "Invalid or expired OTP."},
                    status=status.HTTP_400_BAD_REQUEST,
                )
            
            # Get user and reset password
            user = otp_obj.user
            if not user:
                return Response(
                    {"detail": "User not found."},
                    status=status.HTTP_404_NOT_FOUND,
                )
            
            user.set_password(new_password)
            user.save()

            # Send confirmation via Telegram
            send_password_reset_message(otp_obj.telegram_user_id)
            
            return Response(
                {"message": "Password reset successful. You can now login with your new password."},
                status=status.HTTP_200_OK,
            )
        
        except TelegramOTP.DoesNotExist:
            return Response(
                {"detail": "Invalid reference ID."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        except Exception as e:
            logger.error(f"Password reset failed: {str(e)}")
            return Response(
                {"detail": "Password reset failed. Please try again."},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
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

    def list(self, request, *args, **kwargs):
        queryset = self.get_queryset()
        serializer = self.get_serializer(queryset, many=True)
        payload = list(serializer.data)

        if not payload:
            return Response(payload)

        try:
            portfolio_ids = [portfolio.id for portfolio in queryset]
            rows = list(
                PortfolioStock.objects
                .filter(portfolio_id__in=portfolio_ids)
                .values("portfolio_id", "ticker", "sector")
            )

            tickers = sorted({row["ticker"] for row in rows if row.get("ticker")})
            sentiment_map = get_stocks_sentiment_bulk(tickers) if tickers else {}
            sector_rows = get_sector_sentiment()

            sector_geo_map = {}
            sector_any_map = {}
            sector_acc = {}
            for row in sector_rows:
                sector = row.get("sector")
                geo = row.get("geography")
                score = row.get("sentiment_score")
                if sector is None or score is None:
                    continue
                sector_geo_map[(sector, geo)] = score
                sector_acc.setdefault(sector, []).append(score)
            for sector, scores in sector_acc.items():
                if scores:
                    sector_any_map[sector] = round(sum(scores) / len(scores), 4)

            portfolio_tickers = {}
            portfolio_sectors = {}
            for row in rows:
                pid = row["portfolio_id"]
                portfolio_tickers.setdefault(pid, []).append(row.get("ticker"))
                sector = row.get("sector")
                if sector:
                    portfolio_sectors.setdefault(pid, set()).add(sector)

            for item in payload:
                pid = item["id"]
                geo = item.get("geography") or "ALL"
                ptickers = [ticker for ticker in portfolio_tickers.get(pid, []) if ticker]
                scores = [
                    sentiment_map.get(ticker, {}).get("sentiment_score")
                    for ticker in ptickers
                    if sentiment_map.get(ticker, {}).get("sentiment_score") is not None
                ]

                if scores:
                    portfolio_score = round(sum(scores) / len(scores), 4)
                    if portfolio_score >= 6.5:
                        label = "Positive"
                    elif portfolio_score >= 4.0:
                        label = "Neutral"
                    else:
                        label = "Negative"
                    coverage = round((len(scores) / max(len(ptickers), 1)) * 100, 2)
                else:
                    portfolio_score = None
                    label = "No Data"
                    coverage = 0.0

                s_scores = []
                for sector in portfolio_sectors.get(pid, set()):
                    if geo != "ALL" and (sector, geo) in sector_geo_map:
                        s_scores.append(sector_geo_map[(sector, geo)])
                    elif sector in sector_any_map:
                        s_scores.append(sector_any_map[sector])
                sector_score = round(sum(s_scores) / len(s_scores), 4) if s_scores else None

                item["sentiment_score"] = portfolio_score
                item["sentiment_label"] = label
                item["sentiment_coverage_pct"] = coverage
                item["sentiment_stock_count"] = len(scores)
                item["sector_sentiment_score"] = sector_score
        except Exception:
            logger.exception("[portfolio.list] Sentiment enrichment failed; returning base payload.")
            for item in payload:
                item.setdefault("sentiment_score", None)
                item.setdefault("sentiment_label", "No Data")
                item.setdefault("sentiment_coverage_pct", 0.0)
                item.setdefault("sentiment_stock_count", 0)
                item.setdefault("sector_sentiment_score", None)

        return Response(payload)

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

    queryset = Stock.objects.all().select_related("portfolio").order_by("id")

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
    DIFF_SORT_ALIASES = {
        "diff": "price_diff",
        "price_diff": "price_diff",
        "diff_pct": "expected_change_pct",
        "expected_change_pct": "expected_change_pct",
    }

    def get_queryset(self):
        portfolio_id = self.request.query_params.get("portfolio")
        qs = PortfolioStock.objects.filter(portfolio__user=self.request.user)
        if portfolio_id:
            qs = qs.filter(portfolio_id=portfolio_id)
        return qs.order_by("sector", "ticker")

    @staticmethod
    def _to_float(raw_value):
        if raw_value in (None, ""):
            return None
        try:
            return float(raw_value)
        except (TypeError, ValueError):
            return None

    def _apply_diff_filters(self, rows):
        qp = self.request.query_params
        diff_sign = (qp.get("diff_sign") or "").strip().lower()
        diff_min = self._to_float(qp.get("diff_min"))
        diff_max = self._to_float(qp.get("diff_max"))
        diff_pct_min = self._to_float(qp.get("diff_pct_min") or qp.get("expected_change_pct_min"))
        diff_pct_max = self._to_float(qp.get("diff_pct_max") or qp.get("expected_change_pct_max"))

        def _matches(row):
            price_diff = row.get("price_diff")
            diff_pct = row.get("expected_change_pct")

            if diff_sign == "positive":
                if price_diff is None or price_diff <= 0:
                    return False
            elif diff_sign == "negative":
                if price_diff is None or price_diff >= 0:
                    return False

            if diff_min is not None and (price_diff is None or price_diff < diff_min):
                return False
            if diff_max is not None and (price_diff is None or price_diff > diff_max):
                return False
            if diff_pct_min is not None and (diff_pct is None or diff_pct < diff_pct_min):
                return False
            if diff_pct_max is not None and (diff_pct is None or diff_pct > diff_pct_max):
                return False

            return True

        return [row for row in rows if _matches(row)]

    def _apply_diff_sort(self, rows):
        sort_by_raw = (self.request.query_params.get("sort_by") or "").strip().lower()
        sort_by = self.DIFF_SORT_ALIASES.get(sort_by_raw)
        if not sort_by:
            return rows

        sort_order = (self.request.query_params.get("sort_order") or "desc").strip().lower()
        reverse = sort_order != "asc"

        rows_with_value = [row for row in rows if row.get(sort_by) is not None]
        rows_without_value = [row for row in rows if row.get(sort_by) is None]
        rows_with_value.sort(key=lambda row: row.get(sort_by), reverse=reverse)
        return rows_with_value + rows_without_value

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
        sentiment_map = get_stocks_sentiment_bulk(tickers)

        old_stocks = Stock.objects.filter(symbol__in=tickers)
        old_stock_map = {s.symbol: s for s in old_stocks}

        try:
            insight_map = get_latest_insights_bulk(tickers)
        except Exception:
            insight_map = {}

        results = []
        for ps in qs:
            try:
                ticker = ps.ticker
                silver = silver_map.get(ticker, {})
                rng = range_map.get(ticker, {})
                old = old_stock_map.get(ticker)
                insight = insight_map.get(ticker, {})
                fund = fund_map.get(ticker, {})
                signal_data = signal_map.get(ticker, {})
                forecast_data = forecast_map.get(ticker, {})
                sent = sentiment_map.get(ticker, {})

                daily_ret = silver.get("daily_return")
                direction = forecast_data.get("direction")
                if not direction:
                    direction = "Increase" if daily_ret is not None and daily_ret >= 0 else "Decrease" if daily_ret is not None else ""
                exp_change = forecast_data.get("expected_change_pct")
                if exp_change is None:
                    exp_change = round(daily_ret * 100, 2) if daily_ret is not None else None
                predicted_price = forecast_data.get("predicted_price")
                current_price = silver.get("close")
                price_diff = (
                    round(predicted_price - current_price, 4)
                    if predicted_price is not None and current_price is not None
                    else None
                )

                results.append(
                    {
                        "id": old.id if old else None,
                        "symbol": ticker,
                        "ticker": ticker,
                        "company_name": ps.company_name,
                        "sector": ps.sector,
                        "geography": ps.geography,
                        "current_price": current_price,
                        "min_price": rng.get("week_low"),
                        "max_price": rng.get("week_high"),
                        "predicted_price_1d": predicted_price,
                        "price_diff": price_diff,
                        "expected_change_pct": exp_change,
                        "direction_signal": direction,
                        "model_confidence_r2": forecast_data.get("confidence_r2"),
                        "recommended_action": signal_data.get("signal", ""),
                        "prediction_status": "ready" if forecast_data else "insufficient_data",
                        "signal": signal_data.get("signal", ""),
                        "signal_confidence": signal_data.get("confidence"),
                        "sentiment_score": sent.get("sentiment_score"),
                        "sentiment_label": sent.get("sentiment_label"),
                        "sentiment_source": sent.get("model_used"),
                        "pe_ratio": fund.get("trailing_pe"),
                        "forward_pe": fund.get("forward_pe"),
                        "profit_margin": fund.get("profit_margin"),
                        "revenue_growth": fund.get("revenue_growth"),
                        "market_cap": fund.get("market_cap"),
                        "beta": fund.get("beta"),
                        "eps_trailing": fund.get("eps_trailing"),
                        "return_on_equity": fund.get("return_on_equity"),
                        "discount_level": insight.get("discount_level"),
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
                        "price_diff": None,
                        "expected_change_pct": None,
                        "direction_signal": "",
                        "model_confidence_r2": None,
                        "recommended_action": None,
                        "prediction_status": "insufficient_data",
                        "signal": "",
                        "signal_confidence": None,
                        "sentiment_score": None,
                        "sentiment_label": None,
                        "sentiment_source": None,
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

        results = self._apply_diff_filters(results)
        results = self._apply_diff_sort(results)
        return Response(results)


class ChatbotAPIView(APIView):
    permission_classes = [AllowAny]

    def post(self, request):
        serializer = ChatMessageSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        message = serializer.validated_data["message"]
        history = serializer.validated_data.get("history", [])

        payload = generate_chat_response(
            user=request.user,
            message=message,
            history=history,
        )
        return Response(payload, status=status.HTTP_200_OK)
