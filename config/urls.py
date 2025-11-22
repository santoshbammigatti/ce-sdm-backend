from django.contrib import admin
from django.http import JsonResponse
from django.urls import path, include
from core.views import health_check  # ensure import

# Simple health check function directly in urls.py for testing
def health_check_simple(request):
    return JsonResponse({"status": "ok", "service": "ce-sdm-backend"})

urlpatterns = [
    path('admin/', admin.site.urls),
    path('api/health/', health_check_simple),  # Use simple version first
    path('api/', include('core.urls')),
]