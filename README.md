# CE SDM Summarizer – Backend (Django + DRF)

This backend powers a simple CE workflow:

**raw email threads → NLP draft summary → human edit → approval → usable output for associates**,  
with light CRM context and audit logs. It’s built to run locally in minutes and be easy to demo.

---

## 1) Stack (what and why)

- **Python 3.11**, **Django 5**, **Django REST Framework (DRF)** – quick to scaffold REST APIs and model simple workflow states.
- **SQLite** (dev) – zero setup; switch to Postgres later if needed.
- **Rules‑based NLP (no external model by default)** in `core/summarizer.py` – deterministic and easy to audit.
- **CORS** via `django-cors-headers` – allow the React frontend to call the API.
- **JSONL audit files** in `output/` – approved notes and “posted to CRM” notes for easy inspection.

Project highlights:
```
core/
  models.py          # Thread, Summary
  serializers.py     # DRF serializers
  views.py           # API endpoints
  summarizer.py      # rules-based summarizer + CRM enrichment
  crm_context.py     # mock CRM lookups (orders/customers)
  io_utils.py        # append/truncate JSONL files
  management/commands/ingest_threads.py  # dataset ingest
data/
  ce_exercise_threads.json     # provided dataset (you place it here)
  customers.json, orders.json  # mock CRM context
output/
  approved_summaries.jsonl
  crm_notes.jsonl
```

---

## 2) NLP choice (current) and upgrade options

**Current approach (default):**
- Rules over the conversation to detect common intents (refund/return/photos/address/tracking, etc.), classify `issue_type`, and compose a **concise draft**.
- Enrich with **CRM context** (policy, order status, stock flags).
- Keeps faithfulness high: the draft only reflects thread text + CRM fields.

**If you want better fluency:**
- **Hybrid (recommended):** keep rules for structure, then **rewrite the paragraph** with a small LLM (OpenAI/Azure/Bedrock or an OSS model like BART/T5). Gate it with an env flag (e.g., `USE_LLM=1`) and fall back to rules if the flag/key isn’t present.
- **Policy retrieval (RAG‑lite):** select 1–2 policy bullets and include them in the prompt.
- **Faithfulness checks:** flag dates or money not present in sources; surface warnings to the UI before approval.

These upgrades are easy to add without changing the API shape.

---

## 3) Scaling plan (short and practical)

- **Quality**
  - Constrain summarization to selected snippets + CRM snapshot.
  - Ask models for **JSON‑constrained fields** and validate server‑side.
  - Unit tests for “no unsupported claims.”
- **Latency & cost**
  - Cache summaries per `thread_id` + message hash.
  - Batch/offline workers for bulk threads.
  - Distill to a smaller model for common intents; keep API fallback.
- **Ops**
  - Move to Postgres, add audit tables.
  - Role‑based access on approval endpoint.
  - Track outcomes (agent handle‑time reduction, CSAT), and error rates.
- **Security**
  - Redact PII if using external APIs.
  - Protect admin/reset endpoints with a token in hosted environments.

---

## 4) Local setup

Requirements: **Python 3.11+**

```bash
# clone and enter this backend folder
python -m venv .venv
source .venv/bin/activate        # Windows: .venv\Scripts\activate
pip install --upgrade pip
pip install -r requirements.txt  # or: pip install django djangorestframework django-cors-headers

# Prepare folders and data
mkdir -p data output

# Place your dataset here:
#   data/ce_exercise_threads.json
# Add mock CRM context (edit as needed):
#   data/orders.json
#   data/customers.json

# Initialize DB and ingest dataset
python manage.py migrate
python manage.py ingest_threads --file data/ce_exercise_threads.json

# Run the API
python manage.py runserver
# → http://localhost:8000
```

**CORS (dev):**
```python
# config/settings.py
CORS_ALLOW_ALL_ORIGINS = True  # tighten later with CORS_ALLOWED_ORIGINS
```

---

## 5) API endpoints

**Base URL (dev):** `http://localhost:8000`

### Threads
- **GET `/api/threads/`**  
  List thread cards (id, subject/topic, order, product).

- **GET `/api/threads/<thread_id>/`**  
  Full thread with `messages: [{id, sender, timestamp, body}]`.

### Summarization workflow
- **POST `/api/summarize`**  
  Body: `{"thread_id":"CE-405467-683"}`  
  Runs rules summarizer and creates/refreshes a **DRAFT**.  
  Returns the `Summary` object.

- **GET `/api/summary/<thread_id>`**  
  Returns the current summary (Draft/Edited/Approved).

- **POST `/api/summary/<thread_id>/save-edit`**  
  Body:
  ```json
  {
    "edited_summary": "text...",
    "edited_fields": { "current_status": "Waiting for customer photos", "...": "..." }
  }
  ```
  Moves state to **EDITED**.

- **POST `/api/summary/<thread_id>/approve`**  
  Body: `{"approver":"your.name"}`  
  Finalizes; moves state to **APPROVED** and appends a record to  
  `output/approved_summaries.jsonl`.

### CRM integration (simulated)
- **POST `/api/crm/post-note`**  
  Body:
  ```json
  { "thread_id":"...", "note":"Posted approved summary to CRM case ..." }
  ```
  Appends to `output/crm_notes.jsonl`.

### Admin / Demo helpers
- **POST `/api/admin/reset`**  
  - With body `{ "thread_id":"..." }`: delete that thread’s `Summary` only.  
  - With empty body `{}`: delete **all** `Summary` rows and truncate `output/*.jsonl`.

- **GET `/health`** → `{ "status": "ok" }`

---

## 6) Example cURL

> Add `-H "Accept: application/json"` if you kept DRF’s browsable renderer.

**List threads**
```bash
curl -s http://localhost:8000/api/threads/
```

**Get one thread**
```bash
curl -s http://localhost:8000/api/threads/CE-405467-683/
```

**Create/refresh Draft**
```bash
curl -s -X POST http://localhost:8000/api/summarize \
  -H "Content-Type: application/json" \
  -d '{"thread_id":"CE-405467-683"}'
```

**Get current summary**
```bash
curl -s http://localhost:8000/api/summary/CE-405467-683
```

**Save Edit**
```bash
curl -s -X POST http://localhost:8000/api/summary/CE-405467-683/save-edit \
  -H "Content-Type: application/json" \
  -d '{
    "edited_summary": "Customer reports damaged LED Monitor. We requested photos and created RMA-1427. Refund on first carrier scan per policy.",
    "edited_fields": {
      "current_status": "Waiting for customer photos",
      "recommended_disposition": "Refund",
      "next_actions": [
        "Customer uploads photos",
        "Agent verifies photos",
        "Refund on carrier scan",
        "Close case"
      ],
      "rma_id": "RMA-1427"
    }
  }'
```

**Approve (and export)**
```bash
curl -s -X POST http://localhost:8000/api/summary/CE-405467-683/approve \
  -H "Content-Type: application/json" \
  -d '{"approver":"santosh.b"}'

# Check the export
tail -n 1 output/approved_summaries.jsonl
```

**Post to CRM (simulated)**
```bash
curl -s -X POST http://localhost:8000/api/crm/post-note \
  -H "Content-Type: application/json" \
  -d '{"thread_id":"CE-405467-683","note":"Posted approved summary to CRM case 405467-683"}'

tail -n 1 output/crm_notes.jsonl
```

**Reset**
```bash
# Reset only this thread
curl -s -X POST http://localhost:8000/api/admin/reset \
  -H "Content-Type: application/json" \
  -d '{"thread_id":"CE-405467-683"}'

# Reset ALL and truncate output files
curl -s -X POST http://localhost:8000/api/admin/reset \
  -H "Content-Type: application/json" \
  -d '{}'
```

---

### TL;DR

- Deterministic **rules + CRM enrichment** now.  
- Easy switch to **hybrid LLM rewrite** later.  
- Human **edit/approve** in the loop.  
- **Usable output** + **audit logs** for reviewers.
