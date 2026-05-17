from datetime import datetime, timezone
from uuid import uuid4

from google.cloud import bigquery

from retail_conversation.config import AGENT_INTERACTIONS_TABLE, PROJECT_ID


def summarize_result(result: str, max_length: int = 500) -> str:
    """Keep logs useful without storing huge tool responses."""
    compact = " ".join(result.split())
    if len(compact) <= max_length:
        return compact
    return f"{compact[: max_length - 3]}..."


def log_interaction(
    *,
    user_message: str,
    router_decision: str,
    tool_result: str,
    issue_type: str = "",
    customer_email_present: bool = False,
    order_id_present: bool = False,
    case_summary_requested: bool = False,
    escalation_recommended: bool = False,
) -> None:
    """Best-effort BigQuery interaction logging.

    Logging must never break the customer conversation, so this function
    intentionally swallows insert errors.
    """
    client = bigquery.Client(project=PROJECT_ID)
    row = {
        "event_timestamp": datetime.now(timezone.utc).isoformat(),
        "event_id": str(uuid4()),
        "user_message": user_message,
        "router_decision": router_decision,
        "tool_result_summary": summarize_result(tool_result),
        "issue_type": issue_type,
        "customer_email_present": customer_email_present,
        "order_id_present": order_id_present,
        "case_summary_requested": case_summary_requested,
        "escalation_recommended": escalation_recommended,
    }

    try:
        client.insert_rows_json(AGENT_INTERACTIONS_TABLE, [row])
    except Exception:
        pass
