from django.contrib import admin
from django.urls import include, path
from django.conf import settings
from django.conf.urls.static import static

urlpatterns = [
    path('admin/', admin.site.urls),
    path('api/', include('api.urls')),
    path('accounts/', include('accounts.urls')),
    path('portfolio/', include('portfolio.urls')),
    path('analytics/', include('analytics.urls')),
    path('api/autosignal/', include('autosignal.urls')),
]

if settings.DEBUG:
    urlpatterns += static(
        settings.PREDICTIONS_URL.lstrip("/"),
        document_root=settings.PREDICTIONS_ROOT,
    )
