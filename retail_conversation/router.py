import re

from retail_conversation.tools.cases import create_case_summary
from retail_conversation.tools.customers import (
    get_customer_context,
    get_customer_orders,
    get_customer_product_history,
    get_customer_value_summary,
)
from retail_conversation.tools.issues import resolve_customer_issue
from retail_conversation.tools.logging import log_interaction
from retail_conversation.tools.orders import get_order_context
from retail_conversation.tools.policies import (
    get_escalation_policy,
    get_loyalty_policy,
    get_return_policy,
    get_shipping_policy,
)
from retail_conversation.tools.products import (
    build_product_bundle,
    check_inventory,
    clean_product_text,
    compare_products,
    find_category,
    get_top_selling_products,
    recommend_products,
    recommend_similar_products,
    search_products,
)


EMAIL_PATTERN = re.compile(r"[\w.+-]+@[\w-]+\.[\w.-]+")
ORDER_ID_PATTERN = re.compile(
    r"\b[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}\b",
    re.IGNORECASE,
)


def _find_email(text: str) -> str | None:
    """Extract the first email address from a customer question."""
    match = EMAIL_PATTERN.search(text)
    return match.group(0).rstrip(".,;:!?") if match else None


def _find_order_id(text: str) -> str | None:
    """Extract the first UUID-style order id from a customer question."""
    match = ORDER_ID_PATTERN.search(text)
    return match.group(0) if match else None


def _issue_type(question: str) -> str:
    """Return a simple issue type label for logging."""
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
    return ""


def _escalation_recommended(result: str) -> bool:
    """Detect whether the tool result recommends escalation."""
    lowered = result.lower()
    explicit_escalation = re.search(r"escalation needed:\s*(yes|no)", lowered)
    if explicit_escalation:
        return explicit_escalation.group(1) == "yes"
    return "recommended action:\nescalate" in lowered or "offer to escalate" in lowered


def _respond(
    *,
    question: str,
    router_decision: str,
    result: str,
    issue_type: str = "",
    email: str | None = None,
    order_id: str | None = None,
    case_summary_requested: bool = False,
) -> str:
    """Log the route decision, then return the original tool result."""
    log_interaction(
        user_message=question,
        router_decision=router_decision,
        tool_result=result,
        issue_type=issue_type,
        customer_email_present=bool(email),
        order_id_present=bool(order_id),
        case_summary_requested=case_summary_requested,
        escalation_recommended=_escalation_recommended(result),
    )
    return result


def retail_router(question: str) -> str:
    """Answer a retail question by routing it to the right safe internal tool."""
    text = question.lower()
    email = _find_email(question)
    order_id = _find_order_id(question)

    case_keywords = [
        "case summary",
        "summarize this issue",
        "handoff",
        "hand off",
        "agent assist",
        "support summary",
    ]
    if any(keyword in text for keyword in case_keywords):
        if not email:
            result = "I need the customer's exact email address before I can create a case summary."
            return _respond(
                question=question,
                router_decision="case_summary_missing_email",
                result=result,
                order_id=order_id,
                case_summary_requested=True,
            )
        if not order_id:
            result = "I need the exact order ID before I can create a case summary."
            return _respond(
                question=question,
                router_decision="case_summary_missing_order_id",
                result=result,
                email=email,
                case_summary_requested=True,
            )
        result = create_case_summary(email, order_id, question)
        return _respond(
            question=question,
            router_decision="case_summary",
            result=result,
            issue_type=_issue_type(question),
            email=email,
            order_id=order_id,
            case_summary_requested=True,
        )

    issue_keywords = [
        "help me",
        "issue",
        "problem",
        "unhappy",
        "angry",
        "complaint",
        "refund",
        "compensation",
        "speak to someone",
        "human",
        "manager",
        "arrived late",
        "delayed",
    ]
    if any(keyword in text for keyword in issue_keywords):
        result = resolve_customer_issue(question)
        return _respond(
            question=question,
            router_decision="issue_resolution",
            result=result,
            issue_type=_issue_type(question),
            email=email,
            order_id=order_id,
        )

    if email:
        if any(word in text for word in ["value", "spend", "spent", "order count", "average order"]):
            result = get_customer_value_summary(email)
            return _respond(question=question, router_decision="customer_value", result=result, email=email)
        if any(word in text for word in ["buy most", "buys most", "categories", "purchase history", "bought"]):
            result = get_customer_product_history(email)
            return _respond(question=question, router_decision="customer_product_history", result=result, email=email)
        if any(word in text for word in ["recent orders", "orders", "order history"]):
            result = get_customer_orders(email)
            return _respond(question=question, router_decision="customer_orders", result=result, email=email)
        result = get_customer_context(email)
        return _respond(question=question, router_decision="customer_context", result=result, email=email)

    if "loyalty policy" in text or ("loyalty" in text and "policy" in text):
        result = get_loyalty_policy()
        return _respond(question=question, router_decision="loyalty_policy", result=result)

    if any(word in text for word in ["customer", "profile", "loyalty", "tier"]) and not email:
        result = "I need the customer's exact email address before I can look up customer details."
        return _respond(question=question, router_decision="customer_missing_email", result=result)

    if order_id:
        result = get_order_context(order_id)
        return _respond(question=question, router_decision="order_context", result=result, order_id=order_id)

    if any(word in text for word in ["order", "delivery", "shipping", "returned", "return eligibility"]) and not order_id:
        if "return policy" in text or "returns policy" in text:
            result = get_return_policy()
            return _respond(question=question, router_decision="return_policy", result=result)
        if "shipping policy" in text or ("shipping" in text and "policy" in text):
            result = get_shipping_policy()
            return _respond(question=question, router_decision="shipping_policy", result=result)
        result = "I need the exact order ID before I can look up order details."
        return _respond(question=question, router_decision="order_missing_order_id", result=result)

    if "return policy" in text or "returns policy" in text or "refund policy" in text:
        result = get_return_policy()
        return _respond(question=question, router_decision="return_policy", result=result)

    if "shipping policy" in text or ("shipping" in text and "policy" in text):
        result = get_shipping_policy()
        return _respond(question=question, router_decision="shipping_policy", result=result)

    if "escalation policy" in text or "when should" in text and "escalat" in text:
        result = get_escalation_policy()
        return _respond(question=question, router_decision="escalation_policy", result=result)

    if any(word in text for word in ["top selling", "best selling", "sales ranking", "merchandising"]):
        result = get_top_selling_products(find_category(question))
        return _respond(question=question, router_decision="top_selling_products", result=result)

    if "similar to" in text:
        product_name = question.lower().split("similar to", 1)[1]
        result = recommend_similar_products(clean_product_text(product_name))
        return _respond(question=question, router_decision="similar_products", result=result)

    if "compare" in text and " and " in text:
        comparison = question.lower().split("compare", 1)[1]
        product_a, product_b = comparison.split(" and ", 1)
        result = compare_products(clean_product_text(product_a), clean_product_text(product_b))
        return _respond(question=question, router_decision="compare_products", result=result)

    if any(word in text for word in ["bundle", "outfit", "starter kit", "starter", "build me"]):
        result = build_product_bundle(question)
        return _respond(question=question, router_decision="product_bundle", result=result)

    if any(word in text for word in ["in stock", "available", "do you have", "stock"]):
        result = check_inventory(clean_product_text(question))
        return _respond(question=question, router_decision="inventory_check", result=result)

    if any(word in text for word in ["recommend", "popular", "high-rated", "high rated", "best"]):
        result = recommend_products(question)
        return _respond(question=question, router_decision="product_recommendation", result=result)

    result = search_products(question)
    return _respond(question=question, router_decision="product_search", result=result)
