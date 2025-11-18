from django.db import models

class Thread(models.Model):
    thread_id = models.CharField(max_length=64, unique=True)
    subject = models.CharField(max_length=256, blank=True)
    topic = models.CharField(max_length=128, blank=True)
    initiated_by = models.CharField(max_length=32, blank=True) 
    order_id = models.CharField(max_length=64, blank=True)
    product = models.CharField(max_length=128, blank=True)
    # JSON RAW Messages (list of {id, sender, timestamp, body})
    messages = models.JSONField(default=list)

    def __str__(self):
        return f"{self.thread_id} - {self.subject or self.topic}"

class Summary(models.Model):
    STATE_CHOICES = [
        ("DRAFTED", "Drafted"),
        ("EDITED", "Edited"),
        ("APPROVED", "Approved"),
    ]

    thread = models.OneToOneField(Thread, on_delete=models.CASCADE, related_name="summary")
    draft_summary = models.TextField(blank=True)
    draft_fields = models.JSONField(default=dict, blank=True)

    edited_summary = models.TextField(blank=True)
    edited_fields = models.JSONField(default=dict, blank=True)

    approved_summary = models.TextField(blank=True)
    approved_fields = models.JSONField(default=dict, blank=True)

    state = models.CharField(max_length=16, choices=STATE_CHOICES, default="DRAFTED")
    approver = models.CharField(max_length=128, blank=True)
    approved_at = models.DateTimeField(null=True, blank=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)