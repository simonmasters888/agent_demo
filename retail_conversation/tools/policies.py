from functools import lru_cache
from pathlib import Path


POLICY_DIR = Path(__file__).resolve().parents[1] / "data" / "policies"
RETURN_WINDOW_DAYS = 30

POLICY_FILES = {
    "returns": "returns.md",
    "shipping": "shipping.md",
    "loyalty": "loyalty.md",
    "escalation": "escalation.md",
}


@lru_cache(maxsize=None)
def read_policy(policy_name: str) -> str:
    """Read a local markdown policy file by policy name."""
    filename = POLICY_FILES.get(policy_name)
    if not filename:
        return "I could not find that policy."

    path = POLICY_DIR / filename
    return path.read_text(encoding="utf-8").strip()


def get_policy(policy_name: str) -> str:
    """Return one grounded policy document by name."""
    policy_key = policy_name.lower().strip()
    return read_policy(policy_key)


def get_return_policy() -> str:
    """Return the grounded returns policy."""
    return read_policy("returns")


def get_shipping_policy() -> str:
    """Return the grounded shipping policy."""
    return read_policy("shipping")


def get_loyalty_policy() -> str:
    """Return the grounded loyalty policy."""
    return read_policy("loyalty")


def get_escalation_policy() -> str:
    """Return the grounded escalation policy."""
    return read_policy("escalation")
