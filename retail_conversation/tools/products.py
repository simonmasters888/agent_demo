import re

from google.cloud import bigquery

from retail_conversation.config import PRODUCT_CATEGORIES, PRODUCTS_TABLE, PROJECT_ID


def format_products(rows: list[bigquery.table.Row]) -> str:
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


def clean_product_text(text: str) -> str:
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


def find_category(text: str) -> str:
    """Return a known product category mentioned in the question, if any."""
    lower_text = text.lower()
    for category in PRODUCT_CATEGORIES:
        if category.lower() in lower_text:
            return category
    return ""


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
    clean_text = clean_product_text(search_text)
    job_config = bigquery.QueryJobConfig(
        query_parameters=[
            bigquery.ScalarQueryParameter("search_text", "STRING", clean_text),
            bigquery.ScalarQueryParameter("search_pattern", "STRING", f"%{clean_text}%"),
        ]
    )
    rows = list(client.query(query, job_config=job_config).result())
    return format_products(rows)


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
            bigquery.ScalarQueryParameter("product_a_pattern", "STRING", f"%{product_a.strip()}%"),
            bigquery.ScalarQueryParameter("product_b_pattern", "STRING", f"%{product_b.strip()}%"),
        ]
    )
    rows = list(client.query(query, job_config=job_config).result())

    if len(rows) < 2:
        return "I could not find both products to compare in the retail demo data."

    first, second = rows
    cheaper = first.product_name if first.unit_price < second.unit_price else second.product_name
    higher_rated = first.product_name if first.average_rating >= second.average_rating else second.product_name
    better_stock = first.product_name if first.stock_quantity >= second.stock_quantity else second.product_name
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
    clean_need = find_category(need) or clean_product_text(need)
    job_config = bigquery.QueryJobConfig(
        query_parameters=[
            bigquery.ScalarQueryParameter("need_pattern", "STRING", f"%{clean_need}%")
        ]
    )
    rows = list(client.query(query, job_config=job_config).result())

    if rows:
        return format_products(rows)

    query = f"""
        SELECT product_name, brand, unit_price, stock_quantity, average_rating
        FROM `{PRODUCTS_TABLE}`
        WHERE is_active = TRUE
          AND stock_quantity > 0
        ORDER BY average_rating DESC, stock_quantity DESC
        LIMIT 4
    """
    rows = list(client.query(query).result())
    return format_products(rows)


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
            bigquery.ScalarQueryParameter("product_pattern", "STRING", f"%{product_name.strip()}%")
        ]
    )
    rows = list(client.query(query, job_config=job_config).result())
    return format_products(rows)


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
    return format_products(rows)


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
            bigquery.ScalarQueryParameter("product_pattern", "STRING", f"%{product_name.strip()}%")
        ]
    )
    rows = list(client.query(query, job_config=job_config).result())
    return format_products(rows)


def get_top_selling_products(category: str) -> str:
    """Show top-selling products by units sold and revenue, optionally by category."""
    from retail_conversation.config import ORDER_ITEMS_TABLE

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
            bigquery.ScalarQueryParameter("category_pattern", "STRING", f"%{clean_category}%"),
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
