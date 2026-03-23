from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from . import services


@api_view(["GET"])
@permission_classes([AllowAny])
def sector_report(request):
    """
    GET /api/autosignal/report/
    Returns latest sector intelligence report.
    """
    data = services.get_latest_report()
    return Response(data)


@api_view(["GET"])
@permission_classes([AllowAny])
def company_sentiment(request):
    """
    GET /api/autosignal/sentiment/?company=Bajaj Auto&granularity=weekly
    Returns sentiment scores for one or all companies.
    """
    company     = request.GET.get("company", None)
    granularity = request.GET.get("granularity", "daily")
    data        = services.get_company_sentiment(company, granularity)
    return Response(data)


@api_view(["GET"])
@permission_classes([AllowAny])
def sector_heatmap(request):
    """
    GET /api/autosignal/heatmap/
    Returns all 5 companies sentiment for heatmap display.
    """
    data = services.get_sector_heatmap()
    return Response(data)


@api_view(["GET"])
@permission_classes([AllowAny])
def event_detection(request):
    """
    GET /api/autosignal/events/?company=Tata Motors
    Returns detected corporate events.
    """
    company = request.GET.get("company", None)
    data    = services.get_events(company)
    return Response(data)

@api_view(["GET"])
@permission_classes([AllowAny])
def company_detail(request, slug):
    """
    GET /api/autosignal/company/tata-motors/
    Returns full company intelligence data.
    """
    data = services.get_company_detail(slug)
    return Response(data)



@api_view(["GET"])
@permission_classes([AllowAny])
def semantic_search_view(request):
    """
    GET /api/autosignal/search/?q=EV+strategy&collection=transcripts&company=Tata+Motors
    """
    query      = request.GET.get("q", "")
    collection = request.GET.get("collection", "transcripts")
    company    = request.GET.get("company", None)
    n          = int(request.GET.get("n", 5))

    if not query:
        return Response({"error": "q parameter required"})

    data = services.semantic_search(query, collection, company, n)
    return Response(data)

@api_view(["GET"])
@permission_classes([AllowAny])
def sector_insights(request):
    """
    GET /api/autosignal/insights/
    Returns sector-level insights panel data.
    """
    data = services.get_sector_insights()
    return Response(data)

@api_view(["POST"])
@permission_classes([AllowAny])
def run_sentiment(request):
    """
    POST /api/autosignal/run-sentiment/
    Triggers FinBERT inference on Databricks data.
    Warning: takes 2-3 minutes.
    """
    from .finbert import run_sentiment_analysis
    result = run_sentiment_analysis()
    return Response(result)


@api_view(["POST"])
@permission_classes([AllowAny])
def run_report(request):
    """
    POST /api/autosignal/run-report/
    Generates fresh Groq report from Databricks data.
    """
    from .reports import generate_sector_report
    result = generate_sector_report()
    return Response(result)