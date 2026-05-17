from google.cloud import bigquery

from retail_conversation.config import ORDER_ITEMS_TABLE, ORDERS_TABLE, PRODUCTS_TABLE, PROJECT_ID
from retail_conversation.tools.policies import RETURN_WINDOW_DAYS, get_return_policy


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
    return_policy = get_return_policy()
    if not delivery_date:
        return (
            f"Order {row.order_id} does not have a delivery date, so I cannot confirm "
            f"the {RETURN_WINDOW_DAYS} day return window.\n\nPolicy source:\n{return_policy}"
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
    within_window = days_since_delivery <= RETURN_WINDOW_DAYS
    returned_note = (
        "No items are marked returned."
        if row.returned_item_count == 0
        else f"{row.returned_item_count} of {row.item_count} items are already marked returned."
    )

    if within_window:
        return (
            f"Order {row.order_id} appears to be within the {RETURN_WINDOW_DAYS} day return window "
            f"({days_since_delivery} days since delivery). {returned_note} "
            f"Policy source: Returns Policy. Items must be unworn and a receipt or order record is required."
        )

    return (
        f"Order {row.order_id} appears outside the {RETURN_WINDOW_DAYS} day return window "
        f"({days_since_delivery} days since delivery). {returned_note} "
        f"Policy source: Returns Policy. Escalation is only recommended for delivery issues, "
        f"product faults, or other exceptional circumstances."
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
