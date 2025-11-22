# CE SDM Summarizer – Backend (Django + DRF)

This backend powers a customer service workflow:

**raw email threads → intelligent draft summary (LLM or rules-based) → human edit → approval → usable output**,  
with CRM enrichment and audit logs. It runs locally and supports both AI-powered and deterministic summarization.

---

## 1) Stack (what and why)

- **Python 3.11**, **Django 5**, **Django REST Framework (DRF)** – quick to scaffold REST APIs and manage workflow states.
- **SQLite** (dev) – zero setup; switch to Postgres for production.
- **Hybrid summarization** in `core/summarizer.py`:
  - **LLM-powered** (Groq API) – comprehensive, fluent summaries when API key provided
  - **Rules-based fallback** – deterministic keyword matching if LLM unavailable
- **CORS** via `django-cors-headers` – seamless frontend integration.
- **JSONL audit files** in `output/` – approved summaries and CRM notes for compliance.

Project structure:
```
core/
  models.py          # Thread, Summary
  serializers.py     # DRF serializers
  views.py           # API endpoints
  summarizer.py      # LLM + rule-based summarizer with CRM enrichment
  crm_context.py     # mock CRM lookups (orders/customers)
  io_utils.py        # append/truncate JSONL files
  management/commands/ingest_threads.py  # dataset ingest
data/
  ce_exercise_threads.json     # provided dataset
  customers.json, orders.json  # mock CRM context
output/
  approved_summaries.jsonl     # approved summaries (audit trail)
  crm_notes.jsonl              # CRM integration log
```

---

## 2) Summarization approaches

### LLM-Powered (Recommended for quality)
- **Provider:** Groq API (free tier available)
- **Model:** Llama 3.3 70B Versatile
- **Features:**
  - Comprehensive, fluent case summaries
  - Intelligent issue classification
  - Contextual next-step recommendations
  - CRM data enrichment
- **Cost:** Free tier with rate limits; paid plans available
- **Fallback:** Automatically switches to rule-based if API fails

### Rule-Based (Default/Fallback)
- **Detection:** Keyword matching for intents (refund, return, damaged, delay, etc.)
- **Classification:** Deterministic issue type detection
- **Faithfulness:** Only uses information present in thread + CRM fields
- **Performance:** Instant, no external API calls
- **Use case:** When LLM unavailable or for high-volume batch processing

---

## 3) Getting started with Groq API (LLM)

### Step 1: Create a Groq Account
1. Visit [console.groq.com](https://console.groq.com)
2. Sign up with email or Google/GitHub
3. Verify your email

### Step 2: Generate an API Key
1. Go to **API Keys** in the dashboard
2. Click **Create New API Key**
3. Give it a name (e.g., "CE Summarizer")
4. Copy the key (you won't see it again!)
5. Store securely (use `.env` file for local development)

### Step 3: Configure the Backend (Optional)
```bash
# .env file - for default configuration
USE_LLM=True
GROQ_API_KEY=gsk_your_api_key_here
```

### Step 4: Pass API Key from Frontend
Send the API key in the summarize request:
```json
{
  "thread_id": "CE-405467-683",
  "llm_token": "gsk_your_api_key_here"
}
```

The backend will:
- Test the API key validity
- Use LLM if key is valid
- Fall back to rules if key is invalid/missing
- Tag summaries with generation method

---

## 4) Scaling and extensibility

- **Quality**
  - Constrain summarization to selected snippets + CRM snapshot
  - JSON-constrained field validation
  - Unit tests for faithfulness
- **Latency & cost**
  - Cache summaries per `thread_id` + message hash
  - Batch workers for bulk processing
  - Distill to smaller models for common patterns
- **Ops**
  - Move to Postgres for production
  - Role-based access control
  - Track outcomes: handle-time reduction, CSAT, error rates
- **Security**
  - Redact PII before sending to external APIs
  - Protect admin endpoints with authentication tokens
  - Use HTTPS in production

---

## 5) Local setup

Requirements: **Python 3.11+**

```bash
# Clone and enter the backend folder
python -m venv .venv
source .venv/bin/activate        # Windows: .venv\Scripts\activate
pip install --upgrade pip
pip install -r requirements.txt

# Initialize database and ingest dataset
python manage.py migrate
python manage.py ingest_threads --file data/ce_exercise_threads.json

# Run the development server
python manage.py runserver
# → http://localhost:8000
```

**CORS (development):**
```python
# config/settings.py
CORS_ALLOW_ALL_ORIGINS = True  # tighten later with CORS_ALLOWED_ORIGINS
```

---

## 6) API endpoints

**Base URL (dev):** `http://localhost:8000`

### Threads
- **GET `/api/threads/`**  
  List thread cards (id, subject/topic, order, product).

- **GET `/api/threads/<thread_id>/`**  
  Full thread with `messages: [{id, sender, timestamp, body}]`.

### Summarization workflow
- **POST `/api/summarize`**  
  Body:
  ```json
  {
    "thread_id": "CE-405467-683",
    "llm_token": "gsk_optional_groq_api_key"
  }
  ```
  Generates a draft summary. If `llm_token` provided, uses LLM; otherwise uses rules.  
  Returns the `Summary` object with generation method noted.

- **GET `/api/summary/<thread_id>`**  
  Returns the current summary (Draft/Edited/Approved state).

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
  Finalizes and moves state to **APPROVED**. Appends record to `output/approved_summaries.jsonl`.

### CRM integration (simulated)
- **POST `/api/crm/post-note`**  
  Body:
  ```json
  { "thread_id":"...", "note":"Posted approved summary to CRM case ..." }
  ```
  Appends to `output/crm_notes.jsonl`.

### Admin / Demo helpers
- **POST `/api/admin/reset`**  
  - With body `{ "thread_id":"..." }`: delete that thread's `Summary` only.  
  - With empty body `{}`: delete **all** summaries and truncate `output/*.jsonl`.

---

## 7) Example requests

**List threads**
```bash
curl -s http://localhost:8000/api/threads/
```

**Get one thread**
```bash
curl -s http://localhost:8000/api/threads/CE-405467-683/
```

**Create/refresh Draft (with LLM)**
```bash
curl -s -X POST http://localhost:8000/api/summarize \
  -H "Content-Type: application/json" \
  -d '{
    "thread_id":"CE-405467-683",
    "llm_token":"gsk_your_api_key_here"
  }'
```

**Create/refresh Draft (rules-based, no LLM)**
```bash
curl -s -X POST http://localhost:8000/api/summarize \
  -H "Content-Type: application/json" \
  -d '{
    "thread_id":"CE-405467-683"
  }'
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

**Reset a single thread**
```bash
curl -s -X POST http://localhost:8000/api/admin/reset \
  -H "Content-Type: application/json" \
  -d '{"thread_id":"CE-405467-683"}'
```

**Reset everything**
```bash
curl -s -X POST http://localhost:8000/api/admin/reset \
  -H "Content-Type: application/json" \
  -d '{}'
```

---

## 8) Output format

### Summary response
Every summary includes a note indicating the generation method:

**LLM-generated:**
```
---
*This response was generated via LLM.*
```

**Rule-based:**
```
---
*This response was generated via built-in rule-based generation.*
```

This makes it easy to track which approach was used for each summary.

---

## 9) Troubleshooting

### "LLM API key is invalid"
- Check your Groq API key at [console.groq.com/keys](https://console.groq.com/keys)
- Ensure key is not expired
- Backend will automatically fall back to rule-based

### "Groq API request timed out"
- Network latency; try again
- Falls back to rule-based automatically

### "No LLM API key provided"
- Not an error; using rule-based method (default)
- Pass `llm_token` in request to enable LLM

---

## TL;DR

- **Two summarization modes:** LLM (fluent, requires API key) or rules-based (instant, no dependencies)
- **Zero friction:** If LLM fails, automatically falls back to rules
- **Hybrid approach:** Get the best of both – human judgment + machine assistance
- **Audit trail:** Every summary tagged with generation method
- **Production-ready:** Built for easy scaling and compliance

