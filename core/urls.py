from django.urls import path
from rest_framework.routers import DefaultRouter
from . import views

router = DefaultRouter()
router.register(r'threads', views.ThreadViewSet, basename='thread')

urlpatterns = [
    path('summarize/', views.summarize, name='summarize'),
    path('threads/<str:thread_id>/summary/', views.get_summary, name='get_summary'),
    path('threads/<str:thread_id>/save-edit/', views.save_edit, name='save_edit'),
    path('threads/<str:thread_id>/approve/', views.approve, name='approve'),
    path('crm-note/', views.post_crm_note, name='post_crm_note'),
    path('admin-reset/', views.admin_reset, name='admin_reset'),
    path('admin/ingest/', views.ingest_data_endpoint, name='ingest_data'),
]

urlpatterns += router.urls