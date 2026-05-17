import re

from retail_conversation.tools.cases import create_case_summary
from retail_conversation.tools.customers import (
    get_customer_context,
    get_customer_orders,
    get_customer_product_history,
    get_customer_value_summary,
)
from retail_conversation.tools.issues import resolve_customer_issue
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
            return "I need the customer's exact email address before I can create a case summary."
        if not order_id:
            return "I need the exact order ID before I can create a case summary."
        return create_case_summary(email, order_id, question)

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
        return resolve_customer_issue(question)

    if email:
        if any(word in text for word in ["value", "spend", "spent", "order count", "average order"]):
            return get_customer_value_summary(email)
        if any(word in text for word in ["buy most", "buys most", "categories", "purchase history", "bought"]):
            return get_customer_product_history(email)
        if any(word in text for word in ["recent orders", "orders", "order history"]):
            return get_customer_orders(email)
        return get_customer_context(email)

    if "loyalty policy" in text or ("loyalty" in text and "policy" in text):
        return get_loyalty_policy()

    if any(word in text for word in ["customer", "profile", "loyalty", "tier"]) and not email:
        return "I need the customer's exact email address before I can look up customer details."

    if order_id:
        return get_order_context(order_id)

    if any(word in text for word in ["order", "delivery", "shipping", "returned", "return eligibility"]) and not order_id:
        if "return policy" in text or "returns policy" in text:
            return get_return_policy()
        if "shipping policy" in text or ("shipping" in text and "policy" in text):
            return get_shipping_policy()
        return "I need the exact order ID before I can look up order details."

    if "return policy" in text or "returns policy" in text or "refund policy" in text:
        return get_return_policy()

    if "shipping policy" in text or ("shipping" in text and "policy" in text):
        return get_shipping_policy()

    if "escalation policy" in text or "when should" in text and "escalat" in text:
        return get_escalation_policy()

    if any(word in text for word in ["top selling", "best selling", "sales ranking", "merchandising"]):
        return get_top_selling_products(find_category(question))

    if "similar to" in text:
        product_name = question.lower().split("similar to", 1)[1]
        return recommend_similar_products(clean_product_text(product_name))

    if "compare" in text and " and " in text:
        comparison = question.lower().split("compare", 1)[1]
        product_a, product_b = comparison.split(" and ", 1)
        return compare_products(clean_product_text(product_a), clean_product_text(product_b))

    if any(word in text for word in ["bundle", "outfit", "starter kit", "starter", "build me"]):
        return build_product_bundle(question)

    if any(word in text for word in ["in stock", "available", "do you have", "stock"]):
        return check_inventory(clean_product_text(question))

    if any(word in text for word in ["recommend", "popular", "high-rated", "high rated", "best"]):
        return recommend_products(question)

    return search_products(question)
