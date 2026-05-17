import re

from retail_conversation.tools.customers import get_customer_context
from retail_conversation.tools.orders import get_order_context
from retail_conversation.tools.policies import (
    get_escalation_policy,
    get_return_policy,
    get_shipping_policy,
)
from retail_conversation.tools.products import recommend_products


EMAIL_PATTERN = re.compile(r"[\w.+-]+@[\w-]+\.[\w.-]+")
ORDER_ID_PATTERN = re.compile(
    r"\b[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}\b",
    re.IGNORECASE,
)


def _find_email(text: str) -> str | None:
    match = EMAIL_PATTERN.search(text)
    return match.group(0).rstrip(".,;:!?") if match else None


def _find_order_id(text: str) -> str | None:
    match = ORDER_ID_PATTERN.search(text)
    return match.group(0) if match else None


def _detect_issue_type(question: str) -> str:
    """Classify the customer's broad support issue with simple keyword rules."""
    text = question.lower()

    if any(word in text for word in ["human", "agent", "manager", "escalate", "unhappy", "angry"]):
        return "escalation request"
    if any(word in text for word in ["refund", "money back", "compensation", "credit"]):
        return "refund question"
    if any(word in text for word in ["return", "send it back", "exchange"]):
        return "return request"
    if any(word in text for word in ["late", "delayed", "where is", "delivery", "shipping"]):
        return "delivery or order status"
    if any(word in text for word in ["recommend", "alternative", "instead", "similar"]):
        return "product recommendation"
    if any(word in text for word in ["loyalty", "points", "tier"]):
        return "loyalty question"

    return "general support"


def _next_action(issue_type: str, has_email: bool, has_order_id: bool) -> str:
    """Return a concise recommended next action for the support workflow."""
    if issue_type in ["return request", "refund question", "delivery or order status"] and not has_order_id:
        return "Ask the customer for the exact order ID before checking order-specific details."

    if issue_type in ["loyalty question", "general support"] and not has_email:
        return "Ask the customer for their exact email address before checking customer-specific details."

    if issue_type == "escalation request":
        return "Offer to escalate to a human support agent and prepare a concise case summary."

    if issue_type == "refund question":
        return "Explain that refunds or special compensation need human approval if they go beyond standard policy."

    if issue_type == "return request":
        return "Use the order facts and returns policy to explain eligibility and next steps."

    if issue_type == "delivery or order status":
        return "Use the order facts and shipping policy to explain the current delivery status."

    if issue_type == "product recommendation":
        return "Recommend suitable in-stock alternatives based on the customer request."

    return "Answer with grounded customer, order, product, or policy facts and ask for missing identifiers if needed."


def resolve_customer_issue(question: str) -> str:
    """Resolve a broad CX support issue using customer, order, product, and policy context."""
    email = _find_email(question)
    order_id = _find_order_id(question)
    issue_type = _detect_issue_type(question)

    sections = [f"Issue type: {issue_type}"]

    if email:
        sections.append(f"Customer context:\n{get_customer_context(email)}")
    elif issue_type in ["loyalty question", "general support"]:
        sections.append("Missing customer detail: exact customer email is required for customer-specific help.")

    if order_id:
        sections.append(f"Order context:\n{get_order_context(order_id)}")
    elif issue_type in ["return request", "refund question", "delivery or order status"]:
        sections.append("Missing order detail: exact order ID is required for order-specific help.")

    if issue_type in ["return request", "refund question"]:
        sections.append(f"Relevant policy:\n{get_return_policy()}")
    elif issue_type == "delivery or order status":
        sections.append(f"Relevant policy:\n{get_shipping_policy()}")
    elif issue_type == "escalation request":
        sections.append(f"Relevant policy:\n{get_escalation_policy()}")
    elif issue_type == "product recommendation":
        sections.append(f"Recommended products:\n{recommend_products(question)}")

    sections.append(
        "Next best action:\n"
        f"{_next_action(issue_type, has_email=bool(email), has_order_id=bool(order_id))}"
    )

    return "\n\n".join(sections)
