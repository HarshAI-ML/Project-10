from django.urls import path
from . import views

urlpatterns = [
    path('report/',    views.sector_report,    name='autosignal-report'),
    path('sentiment/', views.company_sentiment, name='autosignal-sentiment'),
    path('heatmap/',   views.sector_heatmap,   name='autosignal-heatmap'),
    path('events/',    views.event_detection,  name='autosignal-events'),
    path('company/<slug:slug>/', views.company_detail, name='autosignal-company'),
    path('search/', views.semantic_search_view, name='autosignal-search'),
    path('insights/', views.sector_insights, name='autosignal-insights'),
    path('run-sentiment/', views.run_sentiment, name='autosignal-run-sentiment'),
    path('run-report/',    views.run_report,    name='autosignal-run-report'),
]