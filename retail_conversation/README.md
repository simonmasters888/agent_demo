# Retail Conversation ADK Agent

Small Google ADK demo agent that talks like a sassy retail shop assistant and uses BigQuery retail demo data.

## Run

From the parent folder:

```bash
cd /Users/simonm/agent-demo
adk web
```

Then select:

```text
retail_conversation
```

CLI option:

```bash
cd /Users/simonm/agent-demo
adk run retail_conversation
```

## Data

The agent reads fixed tables from:

```text
simon-sandpit-472404.retail_demo
```

Tables used:

```text
products
customer
orders
order_items
```

## Tool Design

ADK sees one public tool:

```python
retail_router(question: str)
```

The router decides which internal BigQuery helper to use. This keeps tool routing more reliable than exposing many similar tools directly.

## Project Structure

```text
retail_conversation/
  agent.py              # ADK root_agent declaration
  router.py             # deterministic question routing
  config.py             # BigQuery table and category constants
  tools/
    products.py         # product search, compare, bundle, top sellers
    customers.py        # customer profile, value, history, orders
    orders.py           # order status, items, return eligibility
    policies.py         # reads local grounded policy files
  data/
    policies/
      returns.md
      shipping.md
      loyalty.md
      escalation.md
  README.md
  ROADMAP.md
```

The router supports:

- product search
- inventory checks
- recommendations
- similar products
- product comparison
- bundle suggestions
- top-selling products
- customer profile/value/history, when an exact email is provided
- order status/items/return eligibility, when an exact order ID is provided
- grounded return, shipping, loyalty, and escalation policies

## Example Prompts

```text
Find me high-rated electronics products.
```

```text
Compare PureForm Pro Outerwear 148 and PureForm Ultra Outerwear 338.
```

```text
Build me an Automotive starter bundle.
```

```text
What are the top selling Automotive products?
```

```text
Show me the profile for jason_townsend@hotmail.com.
```

```text
Can order b9afc36c-3ad1-4d57-8719-904c064d3fcb be returned?
```

```text
What is your return policy?
```

```text
What is your shipping policy?
```

```text
When should an issue be escalated?
```
