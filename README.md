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

The review signal is then:
Adjusted CSAT gap
    =
    Actual CSAT − Expected CSAT
A more negative gap means the agent's observed CSAT is further below the level expected from their workload mix.
The 10 most negative gaps become the review candidates.
Example
For one review candidate:
Actual CSAT: 2.96
Expected CSAT: 3.34
Adjusted gap: −0.38
CSAT responses: 122
The dashboard does not interpret this as proof that the agent caused poor customer experiences. It identifies the agent as a candidate for further investigation.
Operational Context
The ranking intentionally does not combine every operational metric into one opaque score.
Instead, the dashboard displays additional context such as:
Ticket volume
SLA breach rate
Median handle time
Replacement rate
Replacement-cost exposure
Transfers
Hardware workload percentage
This keeps the primary review signal explainable while giving a manager additional information for investigation.
Replacement-cost exposure
Replacement exposure is calculated using Vireo's support-policy rule:
Product unit cost + ₹340 logistics
It represents the replacement-cost exposure associated with an agent's handled tickets.
It is not treated as money the agent caused, and it is not presented as guaranteed savings.
AI Coaching Layer
The dashboard includes an optional AI coaching feature powered by Groq.
The AI does not:
Rank agents
Select the bottom 10
Calculate CSAT
Determine causation
Replace the deterministic analytics
Instead, once a manager selects a review candidate, the AI receives the candidate's already-calculated metrics and produces four structured outputs:
Summary
A concise manager-facing interpretation of the supplied metrics.
Primary signal
The most important performance signal already visible in the supplied data.
Investigation focus
Two or three concrete checks a manager could perform to investigate the signal.
Caution
Important limitations or caveats around interpreting the available data.
The output is generated using structured JSON output so that the application receives predictable fields rather than relying on free-form text parsing.
AI generation is triggered manually by the user, avoiding unnecessary model calls during normal dashboard interaction.
Cost-Conscious AI Design
The support dataset contains thousands of tickets, but the application does not make an LLM call for every ticket.
Instead:
11,750 tickets
       ↓
Deterministic analytics
       ↓
10 review candidates
       ↓
Manager selects one agent
       ↓
Optional single AI call
       ↓
Coaching / investigation summary
This keeps the AI layer small, optional, and aligned with the requirement to avoid expensive per-ticket model calls.
Data Quality Checks
The application performs validation before calculating metrics.
Checks include:
Duplicate ticket IDs
Unknown agent references
Unknown customer references
Unknown product references
Roster assignment validity
Legacy timestamp normalization
Negative handle-time detection
Agent roster information is joined using agent_id, not display name.
This matters because the source data contains agents who can share the same display name.
Legacy Timestamp Handling
The dataset contains both current helpdesk records and legacy records.
Legacy resolution timestamps were reconstructed from a UTC event log, while helpdesk timestamps are displayed in IST.
The application therefore normalizes legacy resolution timestamps before calculating handle time.
This prevents false negative handle-time values caused by mixing timestamp conventions.
CSAT Handling
CSAT is calculated only from tickets where a customer actually provided a CSAT score.
Missing CSAT responses are not treated as zero.
This is important because the support policy states that roughly 45% of customers respond to the survey.
The dashboard therefore distinguishes:Number of completed tickets
Number of CSAT responses
Average CSAT among responses
Tier 2 Handling
The ranking is restricted to Tier 1 agents.
Vireo's support policy states that Tier 2 agents handle escalated and warranty cases and should not be compared with Tier 1 agents on volume metrics.
They are therefore excluded from the review ranking.
Tech Stack
Python
Pandas — data processing and analytics
Streamlit — dashboard UI
Plotly — interactive visualization
Groq — optional AI coaching layer
The project deliberately avoids unnecessary infrastructure or ML components because the business problem can be solved more reliably with deterministic analytics plus a targeted LLM interpretation layer.
Project Structure
vireo-support-dashboard/
│
├── app.py                 # Streamlit dashboard
├── metrics.py             # Analytics and ranking logic
├── data_loader.py         # Loading, validation and roster handling
├── ai_coach.py            # Groq structured-output coaching layer
├── requirements.txt       # Python dependencies
├── README.md
│
└── data/
    ├── tickets.csv
    ├── agents.csv
    ├── orders.csv
    ├── customers.csv
    └── products.csv