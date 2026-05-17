from retail_conversation.tools.customers import get_customer_context
from retail_conversation.tools.orders import get_order_context
from retail_conversation.tools.policies import get_escalation_policy, get_return_policy


def _detect_escalation(issue: str) -> str:
    """Flag likely escalations using simple policy-aligned rules."""
    text = issue.lower()
    escalation_terms = [
        "human",
        "manager",
        "escalate",
        "angry",
        "unhappy",
        "fault",
        "broken",
        "damaged",
        "compensation",
        "refund override",
        "exception",
    ]
    return "Yes" if any(term in text for term in escalation_terms) else "No"


def _suggested_reply(issue: str) -> str:
    """Draft a short customer-facing reply for the human agent."""
    text = issue.lower()
    if "return" in text:
        return (
            "Hey, I checked the order details and the returns policy. "
            "We need to confirm the delivery status and return-window eligibility before promising a return."
        )
    if "refund" in text or "compensation" in text:
        return (
            "Hey, I checked the order details. Refunds or compensation outside standard policy "
            "need human review, so I can escalate this for approval."
        )
    if "late" in text or "delivery" in text or "shipping" in text:
        return (
            "Hey, I checked the shipping details. I can walk you through the current order status "
            "and escalate if there is a delivery issue."
        )
    return (
        "Hey, I checked the account and order context. Here is the cleanest next step based on "
        "the policy and order facts."
    )


def create_case_summary(customer_email: str, order_id: str, issue: str) -> str:
    """Create a concise agent-assist case summary for a human support rep."""
    escalation_needed = _detect_escalation(issue)
    recommended_action = (
        "Escalate to a human support agent for review."
        if escalation_needed == "Yes"
        else "Handle through standard self-service guidance unless the customer requests an exception."
    )

    return (
        "Customer:\n"
        f"{get_customer_context(customer_email)}\n\n"
        "Issue:\n"
        f"{issue.strip()}\n\n"
        "Order facts:\n"
        f"{get_order_context(order_id)}\n\n"
        "Policy facts:\n"
        f"{get_return_policy()}\n\n"
        "Escalation policy:\n"
        f"{get_escalation_policy()}\n\n"
        "Recommended action:\n"
        f"{recommended_action}\n\n"
        "Suggested reply:\n"
        f"{_suggested_reply(issue)}\n\n"
        "Escalation needed:\n"
        f"{escalation_needed}"
    )
