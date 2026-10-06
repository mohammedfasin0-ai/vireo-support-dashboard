# Vireo Support Performance Dashboard

A Streamlit dashboard for prioritizing Tier 1 customer-support agents for training review using workload-adjusted CSAT, operational context, and an optional AI coaching layer.

## Business Problem

Vireo Audio wants to prioritize its Q3 training budget of ₹4 lakh.

The support team has 44 agents across multiple teams, channels, shifts, and workloads. A simple "lowest CSAT" ranking can be misleading because some agents handle substantially different mixes of hardware-related and non-hardware work.

The dashboard answers:

> Which Tier 1 agents should be prioritized for review, after accounting for the type of work they handled?

The output is a review list, not a finding of individual fault.

---

## What the Dashboard Does

The application:

1. Loads and validates support, agent, customer, order, and product data.
2. Normalizes legacy resolution timestamps.
3. Resolves agent assignments using agent_id and the applicable roster period.
4. Calculates CSAT and operational metrics.
5. Builds an expected-CSAT benchmark based on each agent's workload mix.
6. Ranks Tier 1 agents by their adjusted CSAT gap.
7. Provides operational context for the review candidates.
8. Provides work-type diagnostics to help investigate the signal.
9. Optionally uses Groq to generate a concise manager-facing coaching and investigation summary.

The deterministic analytics are the source of truth for the ranking. The LLM is only used after an agent has already been selected.

---

## Key Result

The dataset contains:

- 11,750 tickets
- 44 agents
- 10,138 resolved tickets
- 1,045 closed tickets
- 5,196 CSAT responses
- 14 products

The dashboard produces a 10-agent Tier 1 review list.

The review candidates are ranked by the most negative workload-adjusted CSAT gap.

---

## Why Raw CSAT Isn't Enough

A raw CSAT ranking treats every agent as if they handled the same type of work.

That is problematic because Vireo's support operation includes specialized queues. In particular, hardware-related cases can represent a different workload mix from general support.

The dashboard therefore separates completed CSAT responses into:

- Hardware-related work
- Non-hardware work

Hardware-related work is defined for this analysis as:

- Charging & Battery
- Warranty & Repair
- Returns & Refunds

This classification is used as an analytical workload dimension. It does not establish that one work type is inherently more difficult.

---

## Workload-Adjusted CSAT

For each eligible Tier 1 agent, the dashboard calculates an expected CSAT using:

- The agent's own hardware/non-hardware response mix
- The corresponding team benchmark for each work type

Conceptually:

`text
Expected CSAT
    =
    (Agent hardware share × Team hardware CSAT)
    +
    (Agent non-hardware share × Team non-hardware CSAT)