from django.urls import include, path
from rest_framework.routers import DefaultRouter

from api.views import AuthViewSet, PortfolioViewSet, PredictionViewSet, StockViewSet, PortfolioStockViewSet

router = DefaultRouter()
router.register("portfolio", PortfolioViewSet, basename="portfolio")
router.register("portfolio-stocks", PortfolioStockViewSet, basename="portfolio-stocks")
router.register("stocks", StockViewSet, basename="stocks")

urlpatterns = [
    path(
        "register/",
        AuthViewSet.as_view({"post": "register"}),
        name="register",
    ),
    path(
        "login/",
        AuthViewSet.as_view({"post": "login"}),
        name="login",
    ),
    # Telegram OTP endpoints
    path(
        "telegram-otp/generate-qr/",
        AuthViewSet.as_view({"post": "telegram_generate_qr"}),
        name="telegram-generate-qr",
    ),
    path(
        "telegram-otp/verify/",
        AuthViewSet.as_view({"post": "telegram_verify_otp"}),
        name="telegram-verify-otp",
    ),
    path(
        "telegram-webhook/",
        AuthViewSet.as_view({"post": "telegram_webhook"}),
        name="telegram-webhook",
    ),
    path(
        "forgot-password/",
        AuthViewSet.as_view({"post": "forgot_password"}),
        name="forgot-password",
    ),
    path(
        "reset-password/",
        AuthViewSet.as_view({"post": "reset_password"}),
        name="reset-password",
    ),
    path(
        "prediction/",
        PredictionViewSet.as_view({"get": "list"}),
        name="prediction-options",
    ),
    path(
        "prediction/run/",
        PredictionViewSet.as_view({"post": "run"}),
        name="prediction-run",
    ),
    path("", include(router.urls)),
]
