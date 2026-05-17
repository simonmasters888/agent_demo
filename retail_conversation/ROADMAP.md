# Retail Conversation CX Roadmap

## Goal

Expand the current ADK retail agent into a stronger Gemini Enterprise / CX showcase.

The demo should show a realistic customer experience workflow:

1. A customer asks for help with an order or product.
2. The agent grounds answers in BigQuery retail data.
3. The agent uses policy knowledge for returns, shipping, loyalty, and escalation.
4. The agent recommends next-best actions.
5. The agent can produce an agent-assist case summary for a human support rep.
6. The solution is deployable, observable, and explainable.

## Current State

The project currently has:

- Google ADK agent deployed to Cloud Run.
- BigQuery-backed retail data access.
- A single public ADK tool: `retail_router(question: str)`.
- Internal tools for:
  - product search
  - inventory checks
  - recommendations
  - similar products
  - product comparisons
  - bundles
  - customer context
  - order context
  - return policy
- Basic privacy guardrails:
  - exact email required for customer data
  - exact order ID required for order data
- Sassy shop-assistant tone.

## Key Gaps

- The agent is still mostly a data lookup assistant.
- Policies are hardcoded instead of grounded in a knowledge source.
- Customer issue resolution is not a first-class workflow.
- No agent-assist summary or case handoff.
- No conversation logging or analytics loop.
- Single large `agent.py` file is becoming hard to maintain.
- The demo lacks a scripted story for stakeholders.

## Target Demo Story

Primary scenario:

```text
A customer contacts support about an order.
The agent identifies the customer and order, checks order status, reviews items,
evaluates return eligibility, explains policy, recommends alternatives, and creates
a concise case summary for a human agent if needed.
```

Example prompt:

```text
I'm Jason Townsend. My email is jason_townsend@hotmail.com.
Can you help me with order b9afc36c-3ad1-4d57-8719-904c064d3fcb?
I want to know if I can return it and what else you recommend.
```

Expected agent behavior:

- Pull customer context from BigQuery.
- Pull order context from BigQuery.
- Evaluate return eligibility.
- Explain the return policy.
- Recommend similar or alternative products.
- Offer a concise next step.
- Optionally produce a support case summary.

## Phase 1: Refactor For Maintainability

Move the current single-file implementation into small modules.

Target structure:

```text
retail_conversation/
  agent.py
  config.py
  router.py
  tools/
    __init__.py
    products.py
    customers.py
    orders.py
    policies.py
    cases.py
  data/
    policies/
      returns.md
      shipping.md
      loyalty.md
      escalation.md
  README.md
  ROADMAP.md
```

Acceptance criteria:

- `adk run retail_conversation` still works.
- `adk web` still works.
- Existing prompts still work.
- `retail_router(question: str)` remains the main ADK-exposed tool.
- No behavior regression in product, customer, order, or return flows.

## Phase 2: Policy Knowledge Base

Replace hardcoded policy text with small local markdown policy files.

Policies:

- returns
- shipping
- loyalty
- escalation

Initial implementation:

- Read local markdown files from `data/policies`.
- Keep this simple and deterministic.
- Later option: move policies to Cloud Storage, BigQuery, or a Conversational Agents data store.

Acceptance criteria:

- Agent can answer:
  - "What is the return policy?"
  - "How does shipping work?"
  - "How do loyalty points work?"
  - "When should this be escalated?"
- Answers cite which policy area they used.
- Order-specific return eligibility still uses order data plus policy text.

## Phase 3: Customer Issue Resolution Workflow

Add a workflow-level tool:

```python
resolve_customer_issue(question: str) -> str
```

It should:

- extract email and order ID when present
- load customer context
- load order context
- identify likely issue type
- return next best action
- explain the reasoning using grounded facts

Issue types:

- return request
- late delivery
- product recommendation
- order status
- refund question
- loyalty question
- escalation request

Acceptance criteria:

- One prompt can trigger a complete support workflow.
- The response includes:
  - customer facts
  - order facts
  - policy facts
  - next recommended action
- If email or order ID is missing, the agent asks for exactly what it needs.

## Phase 4: Agent Assist / Case Summary

Add a tool:

```python
create_case_summary(customer_email: str, order_id: str, issue: str) -> str
```

Status: implemented in `tools/cases.py`.

Output format:

```text
Customer:
Issue:
Order facts:
Policy facts:
Recommended action:
Suggested reply:
Escalation needed:
```

Acceptance criteria:

- Agent can produce a clean handoff summary.
- Summary is concise enough for a human support rep.
- No invented facts.
- Escalation flag follows policy rules.

## Phase 5: Conversation Logging

Add lightweight BigQuery logging for demo observability.

Potential table:

```text
retail_demo.agent_conversations
```

Fields:

```text
timestamp
session_id
user_message
router_decision
tool_result_summary
issue_type
customer_email_present
order_id_present
escalation_recommended
```

Acceptance criteria:

- Each routed request can be logged.
- Logging failures do not break the customer conversation.
- Demo can show how interactions become analyzable data.

## Phase 6: Insights Demo

Use logged conversations to show CX analytics.

Example questions:

```text
What issues are customers asking about most?
Which products cause the most return conversations?
How often does the agent recommend escalation?
Which categories drive recommendation requests?
```

Acceptance criteria:

- BigQuery queries or views answer these questions.
- README includes demo queries.
- Optional: simple Looker Studio dashboard later.

## Phase 7: Enterprise Integration Story

Position the deployed ADK agent as part of a broader Gemini Enterprise / CX architecture.

Future integration options:

- Register ADK agent with Gemini Enterprise / Agent Engine.
- Add Dialogflow CX / Conversational Agents front end.
- Add data stores for policies and FAQs.
- Add Agent Assist-style workflow for human reps.
- Add Conversational Insights-style analytics from logs.
- Add authentication and role-based access.

Acceptance criteria:

- Architecture diagram or README section explains where this fits.
- Demo clearly distinguishes:
  - customer-facing self service
  - employee-facing agent assist
  - analytics / insights layer
  - governance and access controls

## Implementation Order

Recommended build order:

1. Phase 1: Refactor into modules.
2. Phase 2: Add policy knowledge files.
3. Phase 3: Add issue resolution workflow.
4. Phase 4: Add case summary.
5. Phase 5: Add conversation logging.
6. Phase 6: Add insights queries.
7. Phase 7: Add enterprise integration documentation.

## Demo Prompts To Preserve

These should continue working after every phase:

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

## Deployment Checklist

Before each redeploy:

```bash
cd /Users/simonm/agent-demo
.venv/bin/python -m py_compile retail_conversation/agent.py
adk run retail_conversation
```

Deploy:

```bash
cd /Users/simonm/agent-demo
adk deploy cloud_run \
  --project=simon-sandpit-472404 \
  --region=australia-southeast1 \
  --service_name=retail-conversation \
  --app_name=retail_conversation \
  --with_ui \
  retail_conversation \
  -- \
  --allow-unauthenticated \
  --set-env-vars=GOOGLE_GENAI_USE_VERTEXAI=1,GOOGLE_CLOUD_PROJECT=simon-sandpit-472404,GOOGLE_CLOUD_LOCATION=australia-southeast1
```
