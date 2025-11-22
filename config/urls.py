from django.contrib import admin
from django.urls import path, include
from core.views import health_check  # ensure import

urlpatterns = [
    path('admin/', admin.site.urls),
    path('api/health/', health_check),          # explicit health path
    path('api/', include('core.urls')),
    path('diagnostic/', lambda r: __import__("django.http").http.JsonResponse({"ok": True})),
]