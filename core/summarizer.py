# core/summarizer.py
import re
from typing import Dict, Any, List, Optional
from .crm_context import get_order, get_customer

KEYWORDS = {
    "refund": ["refund", "credit"],
    "replacement": ["replace", "replacement"],
    "return": ["return", "rma"],
    "photos": ["photo", "photos", "picture", "pictures", "image"],
    "address": ["address"],
    "tracking": ["tracking", "carrier"],
    "damaged": ["damage", "damaged", "broken", "defective"],
    "delay": ["late", "delayed", "delay"],
    "wrong_variant": ["wrong", "size", "color", "variant"],
}

def _contains_any(text: str, tokens: List[str]) -> bool:
    t = text.lower()
    return any(tok in t for tok in tokens)

def summarize_thread(thread: Dict[str, Any]) -> Dict[str, Any]:
    """
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

    # 1) Issue classification (simple rules)
    if _contains_any(all_text, KEYWORDS["damaged"]):
        issue_type = "Damaged item on arrival"
    elif _contains_any(all_text, KEYWORDS["delay"]):
        issue_type = "Late delivery"
    elif _contains_any(all_text, KEYWORDS["wrong_variant"]):
        issue_type = "Wrong variant received"
    else:
        issue_type = "General inquiry"

    # 2) Customer ask signals
    customer_ask = []
    for k in ["refund", "replacement", "return", "photos", "address", "tracking"]:
        if _contains_any(all_text, KEYWORDS[k]):
            customer_ask.append(k.capitalize())

    # 3) Next actions & recommendation
    next_actions: List[str] = []
    if "Photos" in customer_ask or issue_type == "Damaged item on arrival":
        next_actions.append("Request photos of the issue")
    if "Return" in customer_ask or issue_type in ["Damaged item on arrival", "Wrong variant received"]:
        next_actions.append("Generate RMA & return label")
    if "Refund" in customer_ask:
        next_actions.append("Process refund on carrier scan")
    if "Replacement" in customer_ask:
        # We'll refine with stock availability after we load CRM
        next_actions.append("Offer replacement if stock available")

    recommended = (
        "Refund" if "Refund" in customer_ask
        else ("Replacement" if "Replacement" in customer_ask
              else "Agent to confirm with customer")
    )

    # 4) CRM enrichment (ALWAYS initialize variables first)
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

        # Optional: refine actions text if stock is known
        if stock_available is True:
            # normalize wording
            next_actions = [
                "Offer replacement (stock available)" if a == "Offer replacement if stock available" else a
                for a in next_actions
            ]
        elif stock_available is False:
            next_actions = [
                "Offer replacement (backorder or OOS)" if a == "Offer replacement if stock available" else a
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
        f"Issue appears to be **{issue_type}** for order **{order_id}** ({product}). "
        f"Initiated by **{initiated_by}**. Customer mentions: {', '.join(customer_ask) or 'N/A'}. "
        f"Recommend: {recommended}. Next actions: {', '.join(next_actions) or 'Confirm details with customer'}.{crm_tail}"
    )

    # 6) Structured fields (include a safe crm_snapshot)
    draft_fields: Dict[str, Any] = {
        "thread_id": thread.get("thread_id"),
        "order_id": order_id,
        "product": product,
        "initiated_by": initiated_by,
        "issue_type": issue_type,
        "customer_ask": customer_ask,
        "attachments_needed": ["Damage photos"] if issue_type == "Damaged item on arrival" else [],
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