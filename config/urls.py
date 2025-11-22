from django.contrib import admin
from django.http import JsonResponse
from django.urls import path, include
from core.views import health_check  # ensure import


def root_check(request):
    return JsonResponse({
        "message": "CE SDM Backend API", 
        "status": "running",
        "endpoints": {
            "health": "/api/health/",
            "threads": "/api/threads/",
            "admin": "/admin/",
            "ingest": "/api/admin/ingest/"
        }
    })

# Simple health check function directly in urls.py for testing
def health_check_simple(request):
    return JsonResponse({"status": "ok", "service": "ce-sdm-backend"})

urlpatterns = [
    path('', root_check),  # Add root handler
    path('admin/', admin.site.urls),
    path('api/health/', health_check_simple),  # Use simple version first
    path('api/', include('core.urls')),
]