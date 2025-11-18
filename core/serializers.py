from rest_framework import serializers
from .models import Thread, Summary

class MessageSerializer(serializers.Serializer):
    id = serializers.CharField()
    sender = serializers.CharField()
    timestamp = serializers.CharField()
    body = serializers.CharField()

class ThreadListSerializer(serializers.ModelSerializer):
    class Meta:
        model = Thread
        fields = ("thread_id", "subject", "topic", "initiated_by", "order_id", "product")

class ThreadDetailSerializer(serializers.ModelSerializer):
    messages = MessageSerializer(many=True)

    class Meta:
        model = Thread
        fields = ("thread_id", "subject", "topic", "initiated_by", "order_id", "product", "messages")

class SummarySerializer(serializers.ModelSerializer):
    thread = ThreadListSerializer(read_only=True)

    class Meta:
        model = Summary
        fields = (
            "thread", "draft_summary", "draft_fields",
            "edited_summary", "edited_fields",
            "approved_summary", "approved_fields",
            "state", "approver", "approved_at",
            "created_at", "updated_at",
        )