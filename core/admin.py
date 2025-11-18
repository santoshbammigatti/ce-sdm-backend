from django.contrib import admin
from .models import Thread, Summary

@admin.register(Thread)
class ThreadAdmin(admin.ModelAdmin):
    list_display = ("thread_id", "topic", "subject", "order_id", "product", "initiated_by")
    search_fields = ("thread_id", "order_id", "product", "subject", "topic")

@admin.register(Summary)
class SummaryAdmin(admin.ModelAdmin):
    list_display = ("thread", "state", "approver", "approved_at")
    search_fields = ("thread__thread_id", "approver")