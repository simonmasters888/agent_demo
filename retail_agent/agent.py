from google.adk.agents.llm_agent import Agent


# Hardcoded mock data keeps this demo small and easy to understand.
INVENTORY = {
    "black jacket": "In stock",
    "combat boots": "Only 2 remaining",
    "vinyl record": "Out of stock",
}

RETURN_POLICY = (
    "30 day returns. Items must be unworn. Receipt required."
)


def check_inventory(product_name: str) -> str:
    """Check the fake inventory status for a product."""
    product = product_name.lower().strip()
    return INVENTORY.get(
        product,
        "I do not have inventory information for that product.",
    )


def explain_return_policy() -> str:
    """Return the fake store return policy."""
    return RETURN_POLICY


root_agent = Agent(
    model='gemini-2.5-flash',
    name='retail_agent',
    description='A simple retail demo assistant.',
    instruction=(
        "You are a friendly retail assistant for a small demo store. "
        "Answer customer questions clearly and briefly. "
        "Recommend from these products when relevant: black jacket, combat boots, vinyl record. "
        "Use check_inventory when a customer asks whether a product is available. "
        "Use explain_return_policy when a customer asks about returns, refunds, or exchanges. "
        "Do not invent inventory, policies, databases, APIs, or external systems."
    ),
    # ADK exposes these Python functions as callable tools for the model.
    tools=[check_inventory, explain_return_policy],
)
