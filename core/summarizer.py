import json
import logging
import re
from typing import Dict, Any, List, Optional

import requests

from .crm_context import get_customer, get_order

logger = logging.getLogger(__name__)

# Configuration Constants
GROQ_API_ENDPOINT = "https://api.groq.com/openai/v1/chat/completions"
GROQ_MODEL = "llama-3.3-70b-versatile"
LLM_API_TEST_TIMEOUT = 10
LLM_API_REQUEST_TIMEOUT = 30
LLM_TEMPERATURE = 0.3
LLM_MAX_TOKENS = 1200
LLM_TEST_MAX_TOKENS = 10

# Intent Detection Keywords
INTENT_KEYWORDS = {
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

# Issue Type Classification
ISSUE_TYPES = {
    "damaged": "Damaged item on arrival",
    "delay": "Late delivery",
    "wrong_variant": "Wrong variant received",
    "return": "Return request",
    "refund": "Refund request",
    "default": "General inquiry",
}


class TextProcessor:
    """Utility class for text analysis operations."""

    @staticmethod
    def contains_any_keyword(text: str, keywords: List[str]) -> bool:
        """
        Check if any keyword is present in text (case-insensitive).

        Args:
            text: Text to search in
            keywords: List of keywords to match

        Returns:
            True if any keyword is found, False otherwise
        """
        text_lower = text.lower()
        return any(keyword in text_lower for keyword in keywords)

    @staticmethod
    def extract_conversation_text(messages: List[Dict[str, str]]) -> str:
        """
        Extract and format conversation from messages.

        Args:
            messages: List of message dictionaries with 'sender' and 'body'

        Returns:
            Formatted conversation string
        """
        formatted_messages = [
            f"**{msg.get('sender', 'Unknown')}**: {msg.get('body', '')}"
            for msg in messages
        ]
        return "\n".join(formatted_messages)

    @staticmethod
    def clean_json_response(content: str) -> str:
        """
        Clean LLM response by removing markdown code blocks.

        Args:
            content: Raw LLM response content

        Returns:
            Cleaned JSON string
        """
        if content.startswith("```"):
            content = content.split("```")[1]
            if content.startswith("json"):
                content = content[4:].lstrip()
            content = content.rsplit("```", 1)[0]

        return content.strip()

    @staticmethod
    def repair_json_newlines(content: str) -> str:
        """
        Fix unescaped newlines in JSON strings.

        Args:
            content: JSON string with potential newline issues

        Returns:
            Repaired JSON string
        """
        return re.sub(
            r'(?<!\\)\n(?=(?:[^"]*"[^"]*")*[^"]*$)',
            '\\n',
            content
        )

class LLMSummarizer:
    """Handles LLM-powered summarization via Groq API."""

    @staticmethod
    def validate_api_key(api_key: str) -> bool:
        """
        Validate Groq API key with test request.

        Args:
            api_key: Groq API key to validate

        Returns:
            True if valid, False otherwise
        """
        if not api_key or not api_key.strip():
            logger.warning("API key is empty or None")
            return False

        try:
            headers = {
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json",
            }
            data = {
                "model": GROQ_MODEL,
                "messages": [{"role": "user", "content": "test"}],
                "temperature": LLM_TEMPERATURE,
                "max_tokens": LLM_TEST_MAX_TOKENS,
            }

            response = requests.post(
                GROQ_API_ENDPOINT,
                json=data,
                headers=headers,
                timeout=LLM_API_TEST_TIMEOUT,
            )

            if response.status_code == 401:
                logger.warning("API key validation failed: Unauthorized")
                return False

            return response.status_code == 200

        except requests.exceptions.RequestException as e:
            logger.error(f"API key validation request failed: {str(e)}")
            return False

    @staticmethod
    def generate_summary(thread: Dict[str, Any], api_key: str) -> Optional[Dict[str, Any]]:
        """
        Generate summary using Groq LLM.

        Args:
            thread: Thread data dictionary
            api_key: Groq API key

        Returns:
            Dictionary with draft_summary and draft_fields, or None on failure
        """
        try:
            conversation = TextProcessor.extract_conversation_text(
                thread.get("messages", [])
            )

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

            headers = {
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json",
            }
            data = {
                "model": GROQ_MODEL,
                "messages": [
                    {
                        "role": "system",
                        "content": "You are a professional customer service analyst. Generate comprehensive, well-structured support summaries. Always return valid JSON with no markdown formatting."
                    },
                    {"role": "user", "content": prompt}
                ],
                "temperature": LLM_TEMPERATURE,
                "max_tokens": LLM_MAX_TOKENS,
            }

            response = requests.post(
                GROQ_API_ENDPOINT,
                json=data,
                headers=headers,
                timeout=LLM_API_REQUEST_TIMEOUT,
            )

            if response.status_code != 200:
                logger.error(f"LLM API error: {response.status_code} - {response.text}")
                return None

            response_data = response.json()
            content = response_data.get("choices", [{}])[0].get("message", {}).get("content", "")

            if not content:
                logger.error("Empty response from LLM")
                return None

            # Clean and repair JSON
            content = TextProcessor.clean_json_response(content)
            content = TextProcessor.repair_json_newlines(content)

            parsed = json.loads(content)

            return {
                "draft_summary": parsed.get("draft_summary", ""),
                "draft_fields": {
                    "issue_type": parsed.get("issue_type", ""),
                    "customer_ask": parsed.get("customer_ask", []),
                    "recommended_disposition": parsed.get("recommended_disposition", ""),
                    "next_actions": parsed.get("next_actions", []),
                },
            }

        except json.JSONDecodeError as e:
            logger.error(f"Failed to parse LLM JSON response: {str(e)}")
            return None
        except requests.exceptions.RequestException as e:
            logger.error(f"LLM API request failed: {str(e)}")
            return None
        except Exception as e:
            logger.error(f"Unexpected error in LLM summarization: {str(e)}")
            return None

class RuleBasedSummarizer:
    """Handles rule-based summarization using keyword classification."""

    @staticmethod
    def classify_issue_type(text: str) -> str:
        """
        Classify issue type based on keyword matching.

        Args:
            text: Concatenated message text

        Returns:
            Issue type string
        """
        if TextProcessor.contains_any_keyword(text, INTENT_KEYWORDS["damaged"]):
            return "Damaged item on arrival"
        elif TextProcessor.contains_any_keyword(text, INTENT_KEYWORDS["delay"]):
            return "Late delivery"
        elif TextProcessor.contains_any_keyword(text, INTENT_KEYWORDS["wrong_variant"]):
            return "Wrong variant received"
        elif TextProcessor.contains_any_keyword(text, INTENT_KEYWORDS["return"]):
            return "Return request"
        elif TextProcessor.contains_any_keyword(text, INTENT_KEYWORDS["refund"]):
            return "Refund request"
        else:
            return "General inquiry"

    @staticmethod
    def detect_customer_asks(text: str) -> List[str]:
        """
        Detect customer requests from text.

        Args:
            text: Concatenated message text

        Returns:
            List of detected customer request types
        """
        requests = []
        for request_type in ["refund", "replacement", "return", "photos", "address", "tracking"]:
            if TextProcessor.contains_any_keyword(text, INTENT_KEYWORDS[request_type]):
                requests.append(request_type)
        return requests

    @staticmethod
    def build_next_actions(issue_type: str, customer_asks: List[str]) -> List[str]:
        """
        Build next action list based on issue and customer requests.

        Args:
            issue_type: Classified issue type
            customer_asks: List of customer request types

        Returns:
            List of next actions
        """
        actions = []

        if "photos" in customer_asks or issue_type == "Damaged item on arrival":
            actions.append("Request photographic evidence of the issue from the customer")

        if "return" in customer_asks or issue_type in ["Damaged item on arrival", "Wrong variant received"]:
            actions.append("Generate Return Merchandise Authorization (RMA) and return shipping label")

        if "refund" in customer_asks or issue_type == "Damaged item on arrival":
            actions.append("Process refund upon receipt of returned item")

        if "replacement" in customer_asks:
            actions.append("Offer replacement if stock available")

        if "address" in customer_asks:
            actions.append("Confirm delivery address with customer")

        if "tracking" in customer_asks:
            actions.append("Provide tracking information to customer")

        if not actions:
            actions.append("Confirm details with customer and determine next steps")

        return actions

    @staticmethod
    def determine_disposition(customer_asks: List[str]) -> str:
        """
        Determine recommended disposition based on customer requests.

        Args:
            customer_asks: List of customer request types

        Returns:
            Recommended disposition string
        """
        if "refund" in customer_asks:
            return "Refund"
        elif "replacement" in customer_asks:
            return "Replacement"
        elif "return" in customer_asks:
            return "RMA + Refund"
        else:
            return "Agent to confirm with customer"

    @staticmethod
    def fetch_crm_context(
        order_id: str,
    ) -> tuple[Optional[str], Optional[bool], Optional[str], Optional[Dict[str, Any]]]:
        """
        Fetch CRM context for enrichment.

        Args:
            order_id: Order ID to fetch context for

        Returns:
            Tuple of (policy, stock_available, order_status, customer_snapshot)
        """
        policy = None
        stock_available = None
        order_status = None
        customer_snapshot = None

        if not order_id:
            return policy, stock_available, order_status, customer_snapshot

        order = get_order(order_id)
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

        return policy, stock_available, order_status, customer_snapshot

    @staticmethod
    def build_summary_text(
        issue_type: str,
        order_id: str,
        product: str,
        initiated_by: str,
        disposition: str,
        customer_asks: List[str],
        next_actions: List[str],
        policy: Optional[str] = None,
        order_status: Optional[str] = None,
    ) -> str:
        """
        Build human-readable summary text.

        Args:
            issue_type: Classified issue type
            order_id: Order ID
            product: Product name
            initiated_by: Thread initiator
            disposition: Recommended disposition
            customer_asks: List of customer requests
            next_actions: List of next actions
            policy: Optional policy information
            order_status: Optional order status

        Returns:
            Formatted summary text
        """
        summary = (
            f"**Case Summary: {issue_type} (Order {order_id})**\n\n"
            f"The customer has reported a {issue_type.lower()} for order {order_id} ({product}). "
            f"Initiated by {initiated_by}. Customer is requesting: {', '.join(customer_asks) or 'assistance'}. "
            f"Recommended disposition: {disposition}.\n\n"
            f"Next steps:\n"
        )

        for action in next_actions:
            summary += f"\n* {action}"

        crm_bits = []
        if order_status:
            crm_bits.append(f"Order status: {order_status}.")
        if policy:
            crm_bits.append(f"Policy: {policy}.")

        if crm_bits:
            summary += f"\n\n{' '.join(crm_bits)}"

        return summary

    @staticmethod
    def summarize(thread: Dict[str, Any]) -> Dict[str, Any]:
        """
        Generate rule-based summary.

        Args:
            thread: Thread data dictionary

        Returns:
            Dictionary with draft_summary and draft_fields
        """
        messages = thread.get("messages", [])
        all_text = " ".join(msg.get("body", "") for msg in messages)
        product = thread.get("product") or ""
        order_id = thread.get("order_id") or ""
        initiated_by = thread.get("initiated_by") or ""

        # Classification and detection
        issue_type = RuleBasedSummarizer.classify_issue_type(all_text)
        customer_asks = RuleBasedSummarizer.detect_customer_asks(all_text)
        next_actions = RuleBasedSummarizer.build_next_actions(issue_type, customer_asks)
        disposition = RuleBasedSummarizer.determine_disposition(customer_asks)

        # CRM enrichment
        policy, stock_available, order_status, customer_snapshot = (
            RuleBasedSummarizer.fetch_crm_context(order_id)
        )

        # Refine actions based on stock availability
        if stock_available is not None:
            next_actions = [
                "Offer replacement (stock available)"
                if a == "Offer replacement if stock available" and stock_available
                else (
                    "Offer replacement (backorder or out of stock)"
                    if a == "Offer replacement if stock available" and not stock_available
                    else a
                )
                for a in next_actions
            ]

        # Build summary
        draft_summary = RuleBasedSummarizer.build_summary_text(
            issue_type=issue_type,
            order_id=order_id,
            product=product,
            initiated_by=initiated_by,
            disposition=disposition,
            customer_asks=customer_asks,
            next_actions=next_actions,
            policy=policy,
            order_status=order_status,
        )

        # Structured fields
        draft_fields: Dict[str, Any] = {
            "thread_id": thread.get("thread_id"),
            "order_id": order_id,
            "product": product,
            "initiated_by": initiated_by,
            "issue_type": issue_type,
            "customer_ask": customer_asks,
            "attachments_needed": ["Photos"] if "photos" in customer_asks else [],
            "current_status": "Unresolved",
            "recommended_disposition": disposition,
            "next_actions": next_actions,
            "sla_risk": False,
            "crm_snapshot": {
                "policy": policy,
                "order_status": order_status,
                "stock_available": stock_available,
                "customer": customer_snapshot,
            },
        }

        return {"draft_summary": draft_summary, "draft_fields": draft_fields}

class ThreadSummarizer:
    """Orchestrates thread summarization with LLM and fallback to rule-based."""

    @staticmethod
    def summarize(thread: Dict[str, Any], llm_api_key: Optional[str] = None) -> Dict[str, Any]:
        """
        Generate summary using LLM if available, otherwise use rule-based approach.

        Args:
            thread: Thread data dictionary
            llm_api_key: Optional Groq API key

        Returns:
            Dictionary with draft_summary and draft_fields
        """
        order_id = thread.get("order_id") or ""
        product = thread.get("product") or ""
        initiated_by = thread.get("initiated_by") or ""

        # Try LLM approach if API key provided
        llm_analysis = None
        if llm_api_key:
            logger.info("Testing LLM API key")
            if LLMSummarizer.validate_api_key(llm_api_key):
                logger.info("Using LLM for summarization")
                llm_analysis = LLMSummarizer.generate_summary(thread, llm_api_key)
            else:
                logger.warning("LLM API key invalid, falling back to rule-based")

        # Fallback to rule-based if LLM unavailable
        if not llm_analysis:
            logger.info("Using rule-based summarization")
            result = RuleBasedSummarizer.summarize(thread)
            result["draft_summary"] += (
                "\n\n---\n*This response was generated via built-in rule-based generation.*"
            )
            return result

        # Enrich LLM analysis with CRM data
        policy, stock_available, order_status, customer_snapshot = (
            RuleBasedSummarizer.fetch_crm_context(order_id)
        )

        # Process summary
        draft_summary = llm_analysis.get("draft_summary", "")
        draft_summary = draft_summary.replace("\\n", "\n")

        # Add CRM enrichment
        crm_bits = []
        if order_status:
            crm_bits.append(f'Order status is currently listed as "{order_status}".')
        if policy:
            crm_bits.append(f"Policy: {policy}")

        if crm_bits:
            draft_summary += "\n\n" + " ".join(crm_bits)

        # Add generation method tag
        draft_summary += "\n\n---\n*This response was generated via LLM.*"

        # Build structured fields
        draft_fields: Dict[str, Any] = {
            "thread_id": thread.get("thread_id"),
            "order_id": order_id,
            "product": product,
            "initiated_by": initiated_by,
            "issue_type": llm_analysis.get("draft_fields", {}).get("issue_type", "General inquiry"),
            "customer_ask": llm_analysis.get("draft_fields", {}).get("customer_ask", []),
            "attachments_needed": (
                ["Photos"]
                if "photos" in llm_analysis.get("draft_fields", {}).get("customer_ask", [])
                else []
            ),
            "current_status": "Unresolved",
            "recommended_disposition": llm_analysis.get("draft_fields", {}).get(
                "recommended_disposition", "Agent to confirm"
            ),
            "next_actions": llm_analysis.get("draft_fields", {}).get("next_actions", []),
            "sla_risk": False,
            "crm_snapshot": {
                "policy": policy,
                "order_status": order_status,
                "stock_available": stock_available,
                "customer": customer_snapshot,
            },
        }

        return {"draft_summary": draft_summary, "draft_fields": draft_fields}


# Public API - Main entry point for backward compatibility
def summarize_thread(thread: Dict[str, Any], llm_api_key: Optional[str] = None) -> Dict[str, Any]:
    """
    Main summarization function with LLM fallback to rule-based approach.

    
    Args:
        thread: Thread data dictionary containing messages, order_id, product, initiated_by
        llm_api_key: Optional Groq API key for LLM-powered summarization

    Returns:
        Dictionary with:
            - draft_summary: Human-readable summary text
            - draft_fields: Structured summary fields including issue type, customer requests, actions, etc.

    Example:
        >>> thread_data = {
        ...     "thread_id": "CE-405467-683",
        ...     "order_id": "ORD-123",
        ...     "product": "Widget Pro",
        ...     "initiated_by": "customer@example.com",
        ...     "messages": [
        ...         {"sender": "Customer", "body": "Item arrived damaged"},
        ...         {"sender": "Agent", "body": "We'll help you!"}
        ...     ]
        ... }
        >>> result = summarize_thread(thread_data, llm_api_key="gsk_...")
        >>> print(result["draft_summary"])
    """
    return ThreadSummarizer.summarize(thread, llm_api_key)