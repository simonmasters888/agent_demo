import re

from google.adk.agents.llm_agent import Agent
from google.cloud import bigquery


# Keep the BigQuery target explicit so the model cannot choose arbitrary tables.
PROJECT_ID = "simon-sandpit-472404"
DATASET_ID = "retail_demo"
PRODUCTS_TABLE = f"{PROJECT_ID}.{DATASET_ID}.products"
CUSTOMERS_TABLE = f"{PROJECT_ID}.{DATASET_ID}.customer"
ORDERS_TABLE = f"{PROJECT_ID}.{DATASET_ID}.orders"
ORDER_ITEMS_TABLE = f"{PROJECT_ID}.{DATASET_ID}.order_items"

# This policy is still local demo data, not from BigQuery.
RETURN_POLICY = "30 day returns. Items must be unworn. Receipt required."
PRODUCT_CATEGORIES = [
    "Automotive",
    "Beauty",
    "Books",
    "Clothing",
    "Electronics",
    "Home & Garden",
    "Sports",
    "Toys",
]

EMAIL_PATTERN = re.compile(r"[\w.+-]+@[\w-]+\.[\w.-]+")
ORDER_ID_PATTERN = re.compile(
    r"\b[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}\b",
    re.IGNORECASE,
)


def _find_email(text: str) -> str | None:
    """Extract the first email address from a customer question."""
    match = EMAIL_PATTERN.search(text)
    return match.group(0) if match else None


def _find_order_id(text: str) -> str | None:
    """Extract the first UUID-style order id from a customer question."""
    match = ORDER_ID_PATTERN.search(text)
    return match.group(0) if match else None


def _clean_product_text(text: str) -> str:
    """Remove common shopping phrases so product search terms are cleaner."""
    cleaned = re.sub(r"[^a-zA-Z0-9 &-]", " ", text.lower())
    for phrase in [
        "recommend products similar to",
        "recommend something similar to",
        "similar products to",
        "similar to",
        "do you have",
        "in stock",
        "available",
        "find me",
        "show me",
        "search for",
        "products",
        "product",
        "please",
    ]:
        cleaned = cleaned.replace(phrase, " ")
    return " ".join(cleaned.split())


def _find_category(text: str) -> str:
    """Return a known product category mentioned in the question, if any."""
    lower_text = text.lower()
    for category in PRODUCT_CATEGORIES:
        if category.lower() in lower_text:
            return category
    return ""


def _format_products(rows: list[bigquery.table.Row]) -> str:
    """Turn BigQuery product rows into a short customer-friendly response."""
    if not rows:
        return "I could not find matching products in the retail demo data."

    products = []
    for row in rows:
        stock = "out of stock" if row.stock_quantity == 0 else f"{row.stock_quantity} in stock"
        products.append(
            f"{row.product_name} by {row.brand}: ${row.unit_price:.2f}, "
            f"{stock}, rating {row.average_rating:.1f}/5"
        )

    return "\n".join(products)


def search_products(search_text: str) -> str:
    """Find or browse products by name, category, subcategory, brand, or tag."""
    client = bigquery.Client(project=PROJECT_ID)
    query = f"""
        WITH terms AS (
          SELECT term
          FROM UNNEST(SPLIT(REGEXP_REPLACE(LOWER(@search_text), r"[^a-z0-9 ]", " "), " ")) AS term
          WHERE LENGTH(term) > 2
            AND term NOT IN (
              "find", "show", "some", "with", "high", "rated", "rating",
              "products", "product", "recommend", "popular", "stock"
            )
        ),
        scored AS (
          SELECT
            product_name,
            brand,
            category,
            subcategory,
            unit_price,
            stock_quantity,
            average_rating,
            CASE WHEN LOWER(product_name) = LOWER(@search_text) THEN 20 ELSE 0 END
              + CASE WHEN LOWER(product_name) LIKE LOWER(@search_pattern) THEN 10 ELSE 0 END
              + CASE WHEN LOWER(category) LIKE LOWER(@search_pattern) THEN 7 ELSE 0 END
              + CASE WHEN LOWER(subcategory) LIKE LOWER(@search_pattern) THEN 6 ELSE 0 END
              + CASE WHEN LOWER(brand) LIKE LOWER(@search_pattern) THEN 5 ELSE 0 END
              + (
                SELECT COUNTIF(
                  LOWER(product_name) LIKE CONCAT("%", term, "%")
                  OR LOWER(category) LIKE CONCAT("%", term, "%")
                  OR LOWER(subcategory) LIKE CONCAT("%", term, "%")
                  OR LOWER(brand) LIKE CONCAT("%", term, "%")
                  OR LOWER(tags) LIKE CONCAT("%", term, "%")
                )
                FROM terms
              ) AS match_score
          FROM `{PRODUCTS_TABLE}`
          WHERE is_active = TRUE
        )
        SELECT product_name, brand, unit_price, stock_quantity, average_rating
        FROM scored
        WHERE match_score > 0
          OR LOWER(product_name) LIKE LOWER(@search_pattern)
          OR LOWER(category) LIKE LOWER(@search_pattern)
          OR LOWER(subcategory) LIKE LOWER(@search_pattern)
          OR LOWER(brand) LIKE LOWER(@search_pattern)
        ORDER BY
          stock_quantity > 0 DESC,
          match_score DESC,
          average_rating DESC,
          stock_quantity DESC
        LIMIT 5
    """
    clean_text = _clean_product_text(search_text)
    job_config = bigquery.QueryJobConfig(
        query_parameters=[
            bigquery.ScalarQueryParameter("search_text", "STRING", clean_text),
            bigquery.ScalarQueryParameter("search_pattern", "STRING", f"%{clean_text}%"),
        ]
    )
    rows = list(client.query(query, job_config=job_config).result())
    return _format_products(rows)


def compare_products(product_a: str, product_b: str) -> str:
    """Compare two product names by price, stock, and rating."""
    client = bigquery.Client(project=PROJECT_ID)
    query = f"""
        WITH selected AS (
          SELECT
            product_name,
            brand,
            unit_price,
            stock_quantity,
            average_rating,
            CASE
              WHEN LOWER(product_name) LIKE LOWER(@product_a_pattern) THEN "A"
              WHEN LOWER(product_name) LIKE LOWER(@product_b_pattern) THEN "B"
            END AS requested_product
          FROM `{PRODUCTS_TABLE}`
          WHERE is_active = TRUE
            AND (
              LOWER(product_name) LIKE LOWER(@product_a_pattern)
              OR LOWER(product_name) LIKE LOWER(@product_b_pattern)
            )
          QUALIFY ROW_NUMBER() OVER (
            PARTITION BY requested_product
            ORDER BY average_rating DESC, stock_quantity DESC
          ) = 1
        )
        SELECT product_name, brand, unit_price, stock_quantity, average_rating
        FROM selected
        ORDER BY requested_product
    """
    job_config = bigquery.QueryJobConfig(
        query_parameters=[
            bigquery.ScalarQueryParameter(
                "product_a_pattern",
                "STRING",
                f"%{product_a.strip()}%",
            ),
            bigquery.ScalarQueryParameter(
                "product_b_pattern",
                "STRING",
                f"%{product_b.strip()}%",
            ),
        ]
    )
    rows = list(client.query(query, job_config=job_config).result())

    if len(rows) < 2:
        return "I could not find both products to compare in the retail demo data."

    first, second = rows
    cheaper = first.product_name if first.unit_price < second.unit_price else second.product_name
    higher_rated = (
        first.product_name
        if first.average_rating >= second.average_rating
        else second.product_name
    )
    better_stock = (
        first.product_name
        if first.stock_quantity >= second.stock_quantity
        else second.product_name
    )
    return (
        f"{first.product_name} by {first.brand}: ${first.unit_price:.2f}, "
        f"{first.stock_quantity} in stock, rating {first.average_rating:.1f}/5.\n"
        f"{second.product_name} by {second.brand}: ${second.unit_price:.2f}, "
        f"{second.stock_quantity} in stock, rating {second.average_rating:.1f}/5.\n"
        f"Cheaper: {cheaper}. Higher rated: {higher_rated}. More stock: {better_stock}."
    )


def build_product_bundle(need: str) -> str:
    """Build a small in-stock product bundle for a customer need or category."""
    client = bigquery.Client(project=PROJECT_ID)
    query = f"""
        WITH matches AS (
          SELECT
            product_name,
            brand,
            category,
            subcategory,
            unit_price,
            stock_quantity,
            average_rating,
            ROW_NUMBER() OVER (
              PARTITION BY category, subcategory
              ORDER BY average_rating DESC, stock_quantity DESC
            ) AS rank_in_group
          FROM `{PRODUCTS_TABLE}`
          WHERE is_active = TRUE
            AND stock_quantity > 0
            AND (
              LOWER(product_name) LIKE LOWER(@need_pattern)
              OR LOWER(category) LIKE LOWER(@need_pattern)
              OR LOWER(subcategory) LIKE LOWER(@need_pattern)
              OR LOWER(tags) LIKE LOWER(@need_pattern)
            )
        )
        SELECT product_name, brand, unit_price, stock_quantity, average_rating
        FROM matches
        WHERE rank_in_group = 1
        ORDER BY average_rating DESC, stock_quantity DESC
        LIMIT 4
    """
    clean_need = _find_category(need) or _clean_product_text(need)
    job_config = bigquery.QueryJobConfig(
        query_parameters=[
            bigquery.ScalarQueryParameter("need_pattern", "STRING", f"%{clean_need}%")
        ]
    )
    rows = list(client.query(query, job_config=job_config).result())

    if rows:
        return _format_products(rows)

    query = f"""
        SELECT product_name, brand, unit_price, stock_quantity, average_rating
        FROM `{PRODUCTS_TABLE}`
        WHERE is_active = TRUE
          AND stock_quantity > 0
        ORDER BY average_rating DESC, stock_quantity DESC
        LIMIT 4
    """
    rows = list(client.query(query).result())
    return _format_products(rows)


def check_inventory(product_name: str) -> str:
    """Check stock for a specific product name. Do not use for recommendations."""
    client = bigquery.Client(project=PROJECT_ID)
    query = f"""
        SELECT product_name, brand, unit_price, stock_quantity, average_rating
        FROM `{PRODUCTS_TABLE}`
        WHERE is_active = TRUE
          AND LOWER(product_name) LIKE LOWER(@product_pattern)
        ORDER BY stock_quantity DESC
        LIMIT 5
    """
    job_config = bigquery.QueryJobConfig(
        query_parameters=[
            bigquery.ScalarQueryParameter(
                "product_pattern",
                "STRING",
                f"%{product_name.strip()}%",
            )
        ]
    )
    rows = list(client.query(query, job_config=job_config).result())
    return _format_products(rows)


def recommend_products(need_or_category: str) -> str:
    """Recommend in-stock products for a customer need, category, or broad request."""
    results = search_products(need_or_category)

    if "could not find" not in results:
        return results

    client = bigquery.Client(project=PROJECT_ID)
    query = f"""
        SELECT product_name, brand, unit_price, stock_quantity, average_rating
        FROM `{PRODUCTS_TABLE}`
        WHERE is_active = TRUE
          AND stock_quantity > 0
        ORDER BY average_rating DESC, stock_quantity DESC
        LIMIT 5
    """
    rows = list(client.query(query).result())
    return _format_products(rows)


def get_order_status(order_id: str) -> str:
    """Look up one order's shipping, payment, delivery, and total status."""
    client = bigquery.Client(project=PROJECT_ID)
    query = f"""
        SELECT
          order_id,
          order_status,
          payment_status,
          shipping_method,
          estimated_delivery_date,
          actual_delivery_date,
          total_amount
        FROM `{ORDERS_TABLE}`
        WHERE order_id = @order_id
        LIMIT 1
    """
    job_config = bigquery.QueryJobConfig(
        query_parameters=[
            bigquery.ScalarQueryParameter("order_id", "STRING", order_id.strip())
        ]
    )
    rows = list(client.query(query, job_config=job_config).result())

    if not rows:
        return "I could not find that order in the retail demo data."

    row = rows[0]
    delivery = row.actual_delivery_date or row.estimated_delivery_date or "not available"
    return (
        f"Order {row.order_id} is {row.order_status}. "
        f"Payment status: {row.payment_status}. "
        f"Shipping: {row.shipping_method}. "
        f"Delivery date: {delivery}. "
        f"Total: ${row.total_amount:.2f}."
    )


def get_order_items(order_id: str) -> str:
    """List the products and quantities inside a specific order."""
    client = bigquery.Client(project=PROJECT_ID)
    query = f"""
        SELECT
          p.product_name,
          p.brand,
          oi.quantity,
          oi.unit_price_at_purchase,
          oi.line_total,
          oi.is_returned,
          oi.return_reason
        FROM `{ORDER_ITEMS_TABLE}` AS oi
        JOIN `{PRODUCTS_TABLE}` AS p
          ON oi.product_id = p.product_id
        WHERE oi.order_id = @order_id
        ORDER BY p.product_name
    """
    job_config = bigquery.QueryJobConfig(
        query_parameters=[
            bigquery.ScalarQueryParameter("order_id", "STRING", order_id.strip())
        ]
    )
    rows = list(client.query(query, job_config=job_config).result())

    if not rows:
        return "I could not find any items for that order in the retail demo data."

    items = []
    for row in rows:
        returned = "returned" if row.is_returned else "not returned"
        return_reason = f", reason: {row.return_reason}" if row.return_reason else ""
        items.append(
            f"{row.quantity} x {row.product_name} by {row.brand} "
            f"at ${row.unit_price_at_purchase:.2f} each, "
            f"line total ${row.line_total:.2f}, {returned}{return_reason}"
        )

    return "\n".join(items)


def get_customer_orders(customer_email: str) -> str:
    """List recent orders for a customer email. Do not use for profile questions."""
    client = bigquery.Client(project=PROJECT_ID)
    query = f"""
        SELECT
          c.first_name,
          c.last_name,
          c.email,
          o.order_id,
          o.order_date,
          o.order_status,
          o.payment_status,
          o.total_amount
        FROM `{CUSTOMERS_TABLE}` AS c
        JOIN `{ORDERS_TABLE}` AS o
          ON c.customer_id = o.customer_id
        WHERE LOWER(c.email) = LOWER(@customer_email)
        ORDER BY o.order_date DESC
        LIMIT 5
    """
    job_config = bigquery.QueryJobConfig(
        query_parameters=[
            bigquery.ScalarQueryParameter(
                "customer_email",
                "STRING",
                customer_email.strip(),
            )
        ]
    )
    rows = list(client.query(query, job_config=job_config).result())

    if not rows:
        return "I could not find recent orders for that customer email in the retail demo data."

    customer_name = f"{rows[0].first_name} {rows[0].last_name}"
    orders = [f"Recent orders for {customer_name}:"]
    for row in rows:
        order_date = row.order_date.date() if row.order_date else "unknown date"
        orders.append(
            f"{row.order_id} on {order_date}: {row.order_status}, "
            f"payment {row.payment_status}, total ${row.total_amount:.2f}"
        )

    return "\n".join(orders)


def get_customer_profile(customer_email: str) -> str:
    """Look up a customer's profile, tier, location, loyalty, and subscriptions."""
    client = bigquery.Client(project=PROJECT_ID)
    query = f"""
        SELECT
          first_name,
          last_name,
          email,
          city,
          country,
          customer_tier,
          preferred_category,
          loyalty_points,
          account_status,
          is_email_subscribed,
          is_sms_subscribed
        FROM `{CUSTOMERS_TABLE}`
        WHERE LOWER(email) = LOWER(@customer_email)
        LIMIT 1
    """
    job_config = bigquery.QueryJobConfig(
        query_parameters=[
            bigquery.ScalarQueryParameter(
                "customer_email",
                "STRING",
                customer_email.strip(),
            )
        ]
    )
    rows = list(client.query(query, job_config=job_config).result())

    if not rows:
        return "I could not find that customer email in the retail demo data."

    row = rows[0]
    email_status = "subscribed to email" if row.is_email_subscribed else "not subscribed to email"
    sms_status = "subscribed to SMS" if row.is_sms_subscribed else "not subscribed to SMS"
    return (
        f"{row.first_name} {row.last_name} is a {row.customer_tier} customer "
        f"in {row.city}, {row.country}. Account status: {row.account_status}. "
        f"Preferred category: {row.preferred_category}. "
        f"Loyalty points: {row.loyalty_points}. "
        f"Marketing: {email_status}, {sms_status}."
    )


def get_customer_value_summary(customer_email: str) -> str:
    """Summarize a customer's value: order count, total spend, average order value."""
    client = bigquery.Client(project=PROJECT_ID)
    query = f"""
        SELECT
          c.first_name,
          c.last_name,
          COUNT(o.order_id) AS order_count,
          COALESCE(SUM(o.total_amount), 0) AS total_spend,
          COALESCE(AVG(o.total_amount), 0) AS average_order_value,
          MAX(o.order_date) AS last_order_date
        FROM `{CUSTOMERS_TABLE}` AS c
        LEFT JOIN `{ORDERS_TABLE}` AS o
          ON c.customer_id = o.customer_id
        WHERE LOWER(c.email) = LOWER(@customer_email)
        GROUP BY c.first_name, c.last_name
        LIMIT 1
    """
    job_config = bigquery.QueryJobConfig(
        query_parameters=[
            bigquery.ScalarQueryParameter(
                "customer_email",
                "STRING",
                customer_email.strip(),
            )
        ]
    )
    rows = list(client.query(query, job_config=job_config).result())

    if not rows:
        return "I could not find that customer email in the retail demo data."

    row = rows[0]
    last_order = row.last_order_date.date() if row.last_order_date else "no orders yet"
    return (
        f"{row.first_name} {row.last_name} has placed {row.order_count} orders. "
        f"Total spend: ${row.total_spend:.2f}. "
        f"Average order value: ${row.average_order_value:.2f}. "
        f"Last order date: {last_order}."
    )


def get_customer_product_history(customer_email: str) -> str:
    """Show what product categories a customer buys most from past orders."""
    client = bigquery.Client(project=PROJECT_ID)
    query = f"""
        SELECT
          p.category,
          COUNT(DISTINCT o.order_id) AS order_count,
          SUM(oi.quantity) AS units_bought,
          SUM(oi.line_total) AS total_spend
        FROM `{CUSTOMERS_TABLE}` AS c
        JOIN `{ORDERS_TABLE}` AS o
          ON c.customer_id = o.customer_id
        JOIN `{ORDER_ITEMS_TABLE}` AS oi
          ON o.order_id = oi.order_id
        JOIN `{PRODUCTS_TABLE}` AS p
          ON oi.product_id = p.product_id
        WHERE LOWER(c.email) = LOWER(@customer_email)
        GROUP BY p.category
        ORDER BY total_spend DESC
        LIMIT 5
    """
    job_config = bigquery.QueryJobConfig(
        query_parameters=[
            bigquery.ScalarQueryParameter(
                "customer_email",
                "STRING",
                customer_email.strip(),
            )
        ]
    )
    rows = list(client.query(query, job_config=job_config).result())

    if not rows:
        return "I could not find purchase history for that customer email."

    history = ["Top purchase categories:"]
    for row in rows:
        history.append(
            f"{row.category}: {row.units_bought} units across {row.order_count} orders, "
            f"${row.total_spend:.2f} total spend"
        )

    return "\n".join(history)


def get_customer_context(customer_email: str) -> str:
    """Get profile, value, purchase history, and recent orders for a customer email."""
    clean_email = customer_email.strip()
    return (
        "Customer profile:\n"
        f"{get_customer_profile(clean_email)}\n\n"
        "Customer value:\n"
        f"{get_customer_value_summary(clean_email)}\n\n"
        "Purchase history:\n"
        f"{get_customer_product_history(clean_email)}\n\n"
        "Recent orders:\n"
        f"{get_customer_orders(clean_email)}"
    )


def recommend_similar_products(product_name: str) -> str:
    """Recommend products similar to a specific product. Do not use inventory lookup."""
    client = bigquery.Client(project=PROJECT_ID)
    query = f"""
        WITH seed AS (
          SELECT product_id, category, subcategory, brand
          FROM `{PRODUCTS_TABLE}`
          WHERE is_active = TRUE
            AND LOWER(product_name) LIKE LOWER(@product_pattern)
          ORDER BY average_rating DESC
          LIMIT 1
        )
        SELECT
          p.product_name,
          p.brand,
          p.unit_price,
          p.stock_quantity,
          p.average_rating
        FROM `{PRODUCTS_TABLE}` AS p
        CROSS JOIN seed
        WHERE p.is_active = TRUE
          AND p.stock_quantity > 0
          AND p.product_id != seed.product_id
          AND (
            p.subcategory = seed.subcategory
            OR p.category = seed.category
            OR p.brand = seed.brand
          )
        ORDER BY
          p.subcategory = seed.subcategory DESC,
          p.brand = seed.brand DESC,
          p.average_rating DESC
        LIMIT 5
    """
    job_config = bigquery.QueryJobConfig(
        query_parameters=[
            bigquery.ScalarQueryParameter(
                "product_pattern",
                "STRING",
                f"%{product_name.strip()}%",
            )
        ]
    )
    rows = list(client.query(query, job_config=job_config).result())
    return _format_products(rows)


def check_return_eligibility(order_id: str) -> str:
    """Check whether a specific order can be returned using delivery date and policy."""
    client = bigquery.Client(project=PROJECT_ID)
    query = f"""
        SELECT
          o.order_id,
          o.order_status,
          o.actual_delivery_date,
          o.estimated_delivery_date,
          COUNT(oi.order_item_id) AS item_count,
          COUNTIF(oi.is_returned) AS returned_item_count
        FROM `{ORDERS_TABLE}` AS o
        LEFT JOIN `{ORDER_ITEMS_TABLE}` AS oi
          ON o.order_id = oi.order_id
        WHERE o.order_id = @order_id
        GROUP BY
          o.order_id,
          o.order_status,
          o.actual_delivery_date,
          o.estimated_delivery_date
        LIMIT 1
    """
    job_config = bigquery.QueryJobConfig(
        query_parameters=[
            bigquery.ScalarQueryParameter("order_id", "STRING", order_id.strip())
        ]
    )
    rows = list(client.query(query, job_config=job_config).result())

    if not rows:
        return "I could not find that order in the retail demo data."

    row = rows[0]
    delivery_date = row.actual_delivery_date or row.estimated_delivery_date
    if not delivery_date:
        return (
            f"Order {row.order_id} does not have a delivery date, so I cannot confirm "
            f"the 30 day return window. Policy: {RETURN_POLICY}"
        )

    eligibility_date = client.query(
        "SELECT DATE_DIFF(CURRENT_DATE(), @delivery_date, DAY) AS days_since_delivery",
        job_config=bigquery.QueryJobConfig(
            query_parameters=[
                bigquery.ScalarQueryParameter("delivery_date", "DATE", delivery_date)
            ]
        ),
    ).result()
    days_since_delivery = list(eligibility_date)[0].days_since_delivery
    within_window = days_since_delivery <= 30
    returned_note = (
        "No items are marked returned."
        if row.returned_item_count == 0
        else f"{row.returned_item_count} of {row.item_count} items are already marked returned."
    )

    if within_window:
        return (
            f"Order {row.order_id} appears to be within the 30 day return window "
            f"({days_since_delivery} days since delivery). {returned_note} "
            f"Policy: items must be unworn and receipt is required."
        )

    return (
        f"Order {row.order_id} appears outside the 30 day return window "
        f"({days_since_delivery} days since delivery). {returned_note} "
        f"Policy: items must be unworn and receipt is required."
    )


def get_order_context(order_id: str) -> str:
    """Get status, items, and return eligibility for one order."""
    clean_order_id = order_id.strip()
    return (
        "Order status:\n"
        f"{get_order_status(clean_order_id)}\n\n"
        "Order items:\n"
        f"{get_order_items(clean_order_id)}\n\n"
        "Return eligibility:\n"
        f"{check_return_eligibility(clean_order_id)}"
    )


def get_top_selling_products(category: str) -> str:
    """Show top-selling products by units sold and revenue, optionally by category."""
    client = bigquery.Client(project=PROJECT_ID)
    query = f"""
        SELECT
          p.product_name,
          p.brand,
          p.category,
          SUM(oi.quantity) AS units_sold,
          SUM(oi.line_total) AS revenue
        FROM `{ORDER_ITEMS_TABLE}` AS oi
        JOIN `{PRODUCTS_TABLE}` AS p
          ON oi.product_id = p.product_id
        WHERE @category = ""
          OR LOWER(p.category) LIKE LOWER(@category_pattern)
        GROUP BY p.product_name, p.brand, p.category
        ORDER BY units_sold DESC, revenue DESC
        LIMIT 5
    """
    clean_category = category.strip()
    job_config = bigquery.QueryJobConfig(
        query_parameters=[
            bigquery.ScalarQueryParameter("category", "STRING", clean_category),
            bigquery.ScalarQueryParameter(
                "category_pattern",
                "STRING",
                f"%{clean_category}%",
            ),
        ]
    )
    rows = list(client.query(query, job_config=job_config).result())

    if not rows:
        return "I could not find top-selling products for that category."

    products = []
    for row in rows:
        products.append(
            f"{row.product_name} by {row.brand} ({row.category}): "
            f"{row.units_sold} units sold, ${row.revenue:.2f} revenue"
        )

    return "\n".join(products)


def get_return_policy() -> str:
    """Return the general return policy only, not order-specific eligibility."""
    return RETURN_POLICY


def retail_router(question: str) -> str:
    """Answer a retail question by routing it to the right safe internal tool."""
    text = question.lower()
    email = _find_email(question)
    order_id = _find_order_id(question)

    if email:
        if any(word in text for word in ["value", "spend", "spent", "order count", "average order"]):
            return get_customer_value_summary(email)
        if any(word in text for word in ["buy most", "buys most", "categories", "purchase history", "bought"]):
            return get_customer_product_history(email)
        if any(word in text for word in ["recent orders", "orders", "order history"]):
            return get_customer_orders(email)
        return get_customer_context(email)

    if any(word in text for word in ["customer", "profile", "loyalty", "tier"]) and not email:
        return "I need the customer's exact email address before I can look up customer details."

    if order_id:
        return get_order_context(order_id)

    if any(word in text for word in ["order", "delivery", "shipping", "returned", "return eligibility"]) and not order_id:
        if "return policy" in text or "returns policy" in text:
            return get_return_policy()
        return "I need the exact order ID before I can look up order details."

    if "return policy" in text or "returns policy" in text or "refund policy" in text:
        return get_return_policy()

    if any(word in text for word in ["top selling", "best selling", "sales ranking", "merchandising"]):
        return get_top_selling_products(_find_category(question))

    if "similar to" in text:
        product_name = question.lower().split("similar to", 1)[1]
        return recommend_similar_products(_clean_product_text(product_name))

    if "compare" in text and " and " in text:
        comparison = question.lower().split("compare", 1)[1]
        product_a, product_b = comparison.split(" and ", 1)
        return compare_products(_clean_product_text(product_a), _clean_product_text(product_b))

    if any(word in text for word in ["bundle", "outfit", "starter kit", "starter", "build me"]):
        return build_product_bundle(question)

    if any(word in text for word in ["in stock", "available", "do you have", "stock"]):
        return check_inventory(_clean_product_text(question))

    if any(word in text for word in ["recommend", "popular", "high-rated", "high rated", "best"]):
        return recommend_products(question)

    return search_products(question)


root_agent = Agent(
    model="gemini-2.5-flash",
    name="retail_conversation",
    description="A sassy retail shop assistant using BigQuery product data.",
    instruction=(
        "You are a real shop assistant with a sassy, Gen Z personality. "
        "Sound confident, upbeat, and conversational, like someone working the floor "
        "who knows the stock and can give a tasteful opinion. "
        "Use light slang sparingly, such as 'honestly', 'low-key', 'solid pick', "
        "'not gonna lie', or 'that's the move'. "
        "Do not be rude, mean, flirty, chaotic, or unprofessional. "
        "Keep answers short, useful, and customer-friendly. "
        "If the data says something is unavailable, say so plainly with a little personality. "
        "Use retail_router for customer, order, product, comparison, bundle, inventory, "
        "recommendation, top-selling, and return questions. "
        "After a tool returns data, include the important fields from the tool result; "
        "do not replace tool data with a generic answer. "
        "Only show customer data when the user provides an exact customer email. "
        "Only show order data when the user provides an exact order ID. "
        "Base product, customer, and order answers on the tools, not guesses. "
        "Never invent stock, orders, customer facts, prices, or policies."
    ),
    # ADK calls this one router; Python owns the deterministic routing and SQL.
    tools=[retail_router],
)
