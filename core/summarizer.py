import os
import json
import re
import requests
from typing import Dict, Any, List, Optional
from django.conf import settings
from .crm_context import get_order, get_customer

# LLM Configuration
USE_LLM = os.getenv('USE_LLM', 'True').lower() == 'true'
GROQ_API_KEY = os.getenv('GROQ_API_KEY', '')

# Keywords for rule-based classification
KEYWORDS = {
    "refund": ["refund", "credit", "money back"],
    "replacement": ["replace", "replacement", "send another"],
    "return": ["return", "rma", "send back"],
    "photos": ["photo", "photos", "picture", "pictures", "image"],
    "address": ["address", "delivery address"],
    "tracking": ["tracking", "carrier", "shipment status"],
    "damaged": ["damage", "damaged", "broken", "defective"],
    "delay": ["late", "delayed", "delay", "not arrived"],
    "wrong_variant": ["wrong", "size", "color", "variant"],
}

def _contains_any(text: str, tokens: List[str]) -> bool:
    """Check if any token is in text (case-insensitive)"""
    t = text.lower()
    return any(tok in t for tok in tokens)

def _get_llm_summary(thread: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """Use LLM to analyze entire thread and generate structured summary"""
    if not GROQ_API_KEY:
        print("GROQ_API_KEY not set, skipping LLM analysis")
        return None
    
    messages = thread.get("messages", [])
    conversation = "\n".join([f"**{m.get('sender', 'Unknown')}**: {m.get('body', '')}" for m in messages])
    
    API_URL = "https://api.groq.com/openai/v1/chat/completions"
    headers = {
        "Authorization": f"Bearer {GROQ_API_KEY}",
        "Content-Type": "application/json"
    }
    
    prompt = f"""You are an expert customer service analyst. Analyze this support thread and generate a comprehensive, professional summary.

Thread Details:
- Product: {thread.get('product', 'N/A')}
- Order ID: {thread.get('order_id', 'N/A')}
- Initiated by: {thread.get('initiated_by', 'N/A')}

Conversation:
{conversation}

Generate a response in VALID JSON format (no markdown code blocks, no escaped quotes inside strings). Use single-line strings with \\n for line breaks:

{{
    "draft_summary": "**Case Summary: [Issue Type] (Order [ORDER_ID])**\\n\\n[Detailed description paragraph explaining the customer's issue, what they requested, and why they need help]. To resolve this issue, we recommend [recommended action]. Next steps include:\\n\\n* [Specific action 1]\\n* [Specific action 2]\\n* [Specific action 3]\\n\\n[Additional relevant information like policy details or order status].",
    "issue_type": "One of: Damaged item on arrival, Late delivery, Wrong variant received, Return request, Refund request, General inquiry",
    "customer_ask": ["lowercase", "requests", "like", "refund", "return", "photos"],
    "recommended_disposition": "One of: Refund, Replacement, RMA + Refund, Agent to confirm with customer",
    "next_actions": ["Specific actionable step 1", "Specific actionable step 2", "Specific actionable step 3"]
}}

CRITICAL REQUIREMENTS:
1. The draft_summary must be VERY DESCRIPTIVE and professional
2. Include the order ID and product name in the case summary header
3. Explain the customer's problem clearly
4. List specific, actionable next steps with bullet points
5. Use \\n for line breaks (not actual newlines)
6. Return ONLY valid JSON - no markdown, no code blocks
7. Make sure all string values are single lines
8. Be comprehensive and helpful"""
    
    payload = {
        "model": "llama-3.3-70b-versatile",
        "messages": [
            {
                "role": "system",
                "content": "You are a professional customer service analyst. Generate comprehensive, well-structured support summaries. Always return valid JSON with no markdown formatting."
            },
            {
                "role": "user",
                "content": prompt
            }
        ],
        "temperature": 0.3,
        "max_tokens": 1200
    }
    
    try:
        response = requests.post(
            API_URL, 
            headers=headers, 
            json=payload, 
            timeout=30,
            verify=True
        )
        
        if response.status_code == 200:
            result = response.json()
            if "choices" in result and len(result["choices"]) > 0:
                content = result["choices"][0]["message"]["content"].strip()
                
                # Strip markdown code blocks if present
                if content.startswith("```"):
                    content = content.split("```")[1]
                    if content.startswith("json"):
                        content = content[4:].lstrip()
                    content = content.rsplit("```", 1)[0]
                
                content = content.strip()
                
                try:
                    return json.loads(content)
                except json.JSONDecodeError as e:
                    print(f"Failed to parse LLM response as JSON")
                    print(f"Content preview: {content[:300]}...")
                    print(f"JSON Error: {e}")
                    
                    # Try to fix newlines in string values
                    try:
                        # Replace actual newlines with escaped newlines
                        fixed_content = re.sub(r'(?<!\\)\n(?=(?:[^"]*"[^"]*")*[^"]*$)', '\\n', content)
                        print("Attempting to parse with fixed newlines...")
                        return json.loads(fixed_content)
                    except json.JSONDecodeError as e2:
                        print(f"Still failed after fixing newlines: {e2}")
                        return None
            return None
        else:
            print(f"Groq API returned status {response.status_code}: {response.text}")
            return None
            
    except requests.exceptions.Timeout:
        print("Groq API request timed out")
        return None
    except Exception as e:
        print(f"LLM analysis failed: {e}")
        return None

def summarize_thread_nonLLM(thread: Dict[str, Any]) -> Dict[str, Any]:
    """
    Rule-based summarization without LLM.
    Uses keyword matching to detect intents and classify issues.
    
    Returns:
      {
        "draft_summary": "...",
        "draft_fields": {...}
      }
    """
    messages = thread.get("messages", [])
    all_text = " ".join(m.get("body", "") for m in messages)
    product = thread.get("product") or ""
    order_id = thread.get("order_id") or ""
    initiated_by = thread.get("initiated_by") or ""
    
    # 1) Issue classification (rule-based)
    if _contains_any(all_text, KEYWORDS["damaged"]):
        issue_type = "Damaged item on arrival"
    elif _contains_any(all_text, KEYWORDS["delay"]):
        issue_type = "Late delivery"
    elif _contains_any(all_text, KEYWORDS["wrong_variant"]):
        issue_type = "Wrong variant received"
    elif _contains_any(all_text, KEYWORDS["return"]):
        issue_type = "Return request"
    elif _contains_any(all_text, KEYWORDS["refund"]):
        issue_type = "Refund request"
    else:
        issue_type = "General inquiry"
    
    # 2) Customer ask signals
    customer_ask = []
    for k in ["refund", "replacement", "return", "photos", "address", "tracking"]:
        if _contains_any(all_text, KEYWORDS[k]):
            customer_ask.append(k)
    
    # 3) Next actions & recommendation
    next_actions: List[str] = []
    
    if "photos" in customer_ask or issue_type == "Damaged item on arrival":
        next_actions.append("Request photographic evidence of the issue from the customer")
    
    if "return" in customer_ask or issue_type in ["Damaged item on arrival", "Wrong variant received"]:
        next_actions.append("Generate Return Merchandise Authorization (RMA) and return shipping label")
    
    if "refund" in customer_ask or issue_type == "Damaged item on arrival":
        next_actions.append("Process refund upon receipt of returned item")
    
    if "replacement" in customer_ask:
        next_actions.append("Offer replacement if stock available")
    
    if "address" in customer_ask:
        next_actions.append("Confirm delivery address with customer")
    
    if "tracking" in customer_ask:
        next_actions.append("Provide tracking information to customer")
    
    # Default action if nothing matched
    if not next_actions:
        next_actions.append("Confirm details with customer and determine next steps")
    
    # Recommendation based on customer ask
    if "refund" in customer_ask:
        recommended = "Refund"
    elif "replacement" in customer_ask:
        recommended = "Replacement"
    elif "return" in customer_ask:
        recommended = "RMA + Refund"
    else:
        recommended = "Agent to confirm with customer"
    
    # 4) CRM enrichment
    policy: Optional[str] = None
    stock_available: Optional[bool] = None
    order_status: Optional[str] = None
    customer_snapshot: Optional[Dict[str, Any]] = None
    
    order = get_order(order_id) if order_id else None
    if order:
        policy = order.get("policy")
        stock_available = order.get("stock_available")
        order_status = order.get("status")
        cust_id = order.get("customer_id")
        if cust_id:
            cust = get_customer(cust_id)
            if cust:
                customer_snapshot = {
                    "customer_id": cust.get("customer_id"),
                    "name": cust.get("name"),
                    "email": cust.get("email"),
                }
        
        # Refine actions based on stock availability
        if stock_available is True:
            next_actions = [
                "Offer replacement (stock available)" if a == "Offer replacement if stock available" else a
                for a in next_actions
            ]
        elif stock_available is False:
            next_actions = [
                "Offer replacement (backorder or out of stock)" if a == "Offer replacement if stock available" else a
                for a in next_actions
            ]
    
    # 5) Human-readable draft summary
    crm_bits = []
    if policy:
        crm_bits.append(f"Policy: {policy}.")
    if order_status:
        crm_bits.append(f"Order status: {order_status}.")
    crm_tail = (" " + " ".join(crm_bits)) if crm_bits else ""
    
    draft_summary = (
        f"**Case Summary: {issue_type} (Order {order_id})**\n\n"
        f"The customer has reported a {issue_type.lower()} for order {order_id} ({product}). "
        f"Initiated by {initiated_by}. Customer is requesting: {', '.join(customer_ask) or 'assistance'}. "
        f"Recommended disposition: {recommended}.\n\n"
        f"Next steps:\n"
    )
    
    for action in next_actions:
        draft_summary += f"\n* {action}"
    
    if crm_bits:
        draft_summary += f"\n\n{' '.join(crm_bits)}"
    
    # 6) Structured fields
    draft_fields: Dict[str, Any] = {
        "thread_id": thread.get("thread_id"),
        "order_id": order_id,
        "product": product,
        "initiated_by": initiated_by,
        "issue_type": issue_type,
        "customer_ask": customer_ask,
        "attachments_needed": ["Photos"] if "photos" in customer_ask else [],
        "current_status": "Unresolved",
        "recommended_disposition": recommended,
        "next_actions": next_actions,
        "sla_risk": False,
        "crm_snapshot": {
            "policy": policy,
            "order_status": order_status,
            "stock_available": stock_available,
            "customer": customer_snapshot
        }
    }
    
    return {"draft_summary": draft_summary, "draft_fields": draft_fields}

def summarize_thread(thread: Dict[str, Any]) -> Dict[str, Any]:
    """
    Main summarization function. Uses LLM if available and configured, falls back to rule-based.
    
    Returns:
      {
        "draft_summary": "...",
        "draft_fields": {...}
      }
    """
    order_id = thread.get("order_id") or ""
    product = thread.get("product") or ""
    initiated_by = thread.get("initiated_by") or ""
    
    # Get LLM analysis if enabled and API key is available
    llm_analysis = None
    if USE_LLM and GROQ_API_KEY:
        print("Using LLM for summarization...")
        llm_analysis = _get_llm_summary(thread)
    
    # Fallback to rule-based if LLM not available or failed
    if not llm_analysis:
        print("Using rule-based summarization...")
        return summarize_thread_nonLLM(thread)
    
    # CRM enrichment for LLM results
    policy: Optional[str] = None
    stock_available: Optional[bool] = None
    order_status: Optional[str] = None
    customer_snapshot: Optional[Dict[str, Any]] = None

    order = get_order(order_id) if order_id else None
    if order:
        policy = order.get("policy")
        stock_available = order.get("stock_available")
        order_status = order.get("status")
        cust_id = order.get("customer_id")
        if cust_id:
            cust = get_customer(cust_id)
            if cust:
                customer_snapshot = {
                    "customer_id": cust.get("customer_id"),
                    "name": cust.get("name"),
                    "email": cust.get("email"),
                }

    # Enrich summary with CRM data
    draft_summary = llm_analysis.get("draft_summary", "")
    
    # Convert \\n to actual newlines for display
    draft_summary = draft_summary.replace("\\n", "\n")
    
    # Add CRM info
    crm_bits = []
    if order_status:
        crm_bits.append(f"Order status is currently listed as \"{order_status}\".")
    if policy:
        crm_bits.append(f"Policy: {policy}")
    
    if crm_bits:
        draft_summary += "\n\n" + " ".join(crm_bits)

    # Structured fields
    draft_fields: Dict[str, Any] = {
        "thread_id": thread.get("thread_id"),
        "order_id": order_id,
        "product": product,
        "initiated_by": initiated_by,
        "issue_type": llm_analysis.get("issue_type", "General inquiry"),
        "customer_ask": llm_analysis.get("customer_ask", []),
        "attachments_needed": ["Photos"] if "photos" in llm_analysis.get("customer_ask", []) else [],
        "current_status": "Unresolved",
        "recommended_disposition": llm_analysis.get("recommended_disposition", "Agent to confirm"),
        "next_actions": llm_analysis.get("next_actions", []),
        "sla_risk": False,
        "crm_snapshot": {
            "policy": policy,
            "order_status": order_status,
            "stock_available": stock_available,
            "customer": customer_snapshot
        }
    }

    return {"draft_summary": draft_summary, "draft_fields": draft_fields}