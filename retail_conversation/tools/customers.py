from google.cloud import bigquery

from retail_conversation.config import (
    CUSTOMERS_TABLE,
    ORDER_ITEMS_TABLE,
    ORDERS_TABLE,
    PRODUCTS_TABLE,
    PROJECT_ID,
)


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
            bigquery.ScalarQueryParameter("customer_email", "STRING", customer_email.strip())
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
            bigquery.ScalarQueryParameter("customer_email", "STRING", customer_email.strip())
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
            bigquery.ScalarQueryParameter("customer_email", "STRING", customer_email.strip())
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
            bigquery.ScalarQueryParameter("customer_email", "STRING", customer_email.strip())
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
