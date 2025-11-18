import json
from django.core.management.base import BaseCommand
from core.models import Thread

class Command(BaseCommand):
    help = "Ingest CE exercise threads from a JSON file."

    def add_arguments(self, parser):
        parser.add_argument("--file", type=str, default="data/ce_exercise_threads.json")

    def handle(self, *args, **options):
        path = options["file"]
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
            threads = data.get("threads", data)

        created, updated = 0, 0
        for t in threads:
            thread_id = t.get("thread_id")
            defaults = {
                "subject": t.get("subject", ""),
                "topic": t.get("topic", ""),
                "initiated_by": t.get("initiated_by", ""),
                "order_id": t.get("order_id", ""),
                "product": t.get("product", ""),
                "messages": t.get("messages", []),
            }
            obj, is_created = Thread.objects.update_or_create(
                thread_id=thread_id, defaults=defaults
            )
            if is_created:
                created += 1
            else:
                updated += 1

        self.stdout.write(self.style.SUCCESS(
            f"Ingested threads. Created: {created}, Updated: {updated}"
        ))