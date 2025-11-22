import logging
from django.utils import timezone
from rest_framework import viewsets
from django.db import transaction
from rest_framework.decorators import api_view
from rest_framework.response import Response
from .io_utils import append_jsonl, truncate_output_files
from django.shortcuts import get_object_or_404
from django.http import JsonResponse
from django.views.decorators.http import require_http_methods
from .models import Thread, Summary
from .serializers import ThreadListSerializer, ThreadDetailSerializer, SummarySerializer
from .summarizer import summarize_thread
from django.http import JsonResponse
from django.views.decorators.http import require_http_methods
from django.core.management import call_command
from django.views.decorators.csrf import csrf_exempt



logger = logging.getLogger(__name__)

@require_http_methods(["GET"])
def health_check(request):
    """Health check endpoint for deployment monitoring."""
    return JsonResponse({
        "status": "healthy",
        "service": "ce-sdm-backend"
    })

@csrf_exempt 
@require_http_methods(["POST"])
def ingest_data_endpoint(request):
    """Admin endpoint to ingest sample data into Railway database"""
    try:
        call_command('ingest_threads')
        from core.models import Thread
        count = Thread.objects.count()
        return JsonResponse({
            "status": "success",
            "message": f"Sample data ingested successfully. {count} threads in database."
        })
    except Exception as e:
        return JsonResponse({
            "status": "error",
            "message": str(e)
        }, status=500)

class ThreadViewSet(viewsets.ReadOnlyModelViewSet):
    lookup_field = "thread_id"
    queryset = Thread.objects.all().order_by("thread_id")
    serializer_class = ThreadListSerializer

    def retrieve(self, request, *args, **kwargs):
        thread = get_object_or_404(Thread, thread_id=kwargs.get("thread_id"))
        serializer = ThreadDetailSerializer(thread)
        return Response(serializer.data)
    

@api_view(["POST"])
def summarize(request):
    """
    Body: { 
      "thread_id": "CE-405467-683",
      "llm_token": "optional-groq-api-key"
    }
    Generates/refreshes a DRAFT summary for the thread.
    If llm_token is provided and valid, uses LLM. Otherwise uses rule-based approach.
    """
    thread_id = request.data.get("thread_id")
    llm_token = request.data.get("llm_token")
    
    if not thread_id:
        return Response({"detail": "thread_id is required"}, status=400)

    thread = get_object_or_404(Thread, thread_id=thread_id)

    # Produce draft using LLM (if token provided) or rules
    payload = {
        "thread_id": thread.thread_id,
        "order_id": thread.order_id,
        "product": thread.product,
        "initiated_by": thread.initiated_by,
        "messages": thread.messages,
    }
    result = summarize_thread(payload, llm_api_key=llm_token)

    # Upsert Summary
    summary, _ = Summary.objects.get_or_create(thread=thread)
    summary.draft_summary = result["draft_summary"]
    summary.draft_fields = result["draft_fields"]
    summary.state = "DRAFTED"
    summary.save()

    return Response(SummarySerializer(summary).data, status=200)

@api_view(["POST"])
def save_edit(request, thread_id: str):
    """
    Body: {
      "edited_summary": "...",
      "edited_fields": {...}
    }
    Sets state to EDITED.
    """
    thread = get_object_or_404(Thread, thread_id=thread_id)
    summary = get_object_or_404(Summary, thread=thread)

    summary.edited_summary = request.data.get("edited_summary", "") or ""
    summary.edited_fields = request.data.get("edited_fields", {}) or {}
    summary.state = "EDITED"
    summary.save()

    return Response(SummarySerializer(summary).data, status=200)

@api_view(["POST"])
def approve(request, thread_id: str):
    """
    Body: { "approver": "santosh.b" }
    Copies edited -> approved, sets state=APPROVED and approved_at.
    """
    thread = get_object_or_404(Thread, thread_id=thread_id)
    summary = get_object_or_404(Summary, thread=thread)

    approver = request.data.get("approver", "")
    summary.approver = approver
    summary.approved_at = timezone.now()

    # If user has never edited, approve from draft
    summary.approved_summary = summary.edited_summary or summary.draft_summary
    summary.approved_fields = summary.edited_fields or summary.draft_fields

    summary.state = "APPROVED"
    summary.save()

    
    export_record = {
        "thread_id": thread.thread_id,
        "subject": thread.subject,
        "topic": thread.topic,
        "order_id": thread.order_id,
        "product": thread.product,
        "approved_summary": summary.approved_summary,
        "approved_fields": summary.approved_fields,
        "approver": summary.approver,
        "approved_at": summary.approved_at.isoformat(),
    }
    append_jsonl("approved_summaries.jsonl", export_record)

    return Response(SummarySerializer(summary).data, status=200)



@api_view(["POST"])
def post_crm_note(request):
    """
    Body: {
      "thread_id": "CE-405467-683",
      "note": "Approved summary or agent note",
      "metadata": { ... optional ... }
    }
    -> writes to output/crm_notes.jsonl
    """
    thread_id = request.data.get("thread_id")
    note = request.data.get("note", "")
    metadata = request.data.get("metadata", {}) or {}

    if not thread_id or not note:
        return Response({"detail": "thread_id and note are required"}, status=400)

    record = {
        "thread_id": thread_id,
        "note": note,
        "metadata": metadata,
    }
    append_jsonl("crm_notes.jsonl", record)
    return Response({"status": "posted", "thread_id": thread_id}, status=200)


@api_view(["GET"])
def get_summary(request, thread_id: str):
    """
    Returns the current Summary state for a thread_id.
    If no Summary exists yet, 404 is returned (front end can then call /api/summarize).
    """
    thread = get_object_or_404(Thread, thread_id=thread_id)
    summary = get_object_or_404(Summary, thread=thread)
    return Response(SummarySerializer(summary).data, status=200)


@api_view(["POST"])
def admin_reset(request):
    """
    Resets summaries to a clean state so the demo can be replayed.
    - If "thread_id" provided: delete Summary for that thread only.
    - Else: delete all Summaries and truncate output JSONL files.
    Body (optional): { "thread_id": "CE-405467-683" }
    """
    # ⚠️ Optional: simple guard for production — a shared secret/token.
    # token = request.headers.get("X-Admin-Token")
    # if token != os.getenv("ADMIN_TOKEN"):
    #     return Response({"detail": "Forbidden"}, status=403)

    thread_id = request.data.get("thread_id")

    with transaction.atomic():
        if thread_id:
            thread = get_object_or_404(Thread, thread_id=thread_id)
            Summary.objects.filter(thread=thread).delete()
            # Keep output files untouched for single-thread reset
            return Response({"status": "ok", "scope": "single", "thread_id": thread_id}, status=200)
        else:
            Summary.objects.all().delete()
            truncate_output_files()
            return Response({"status": "ok", "scope": "all"}, status=200)
