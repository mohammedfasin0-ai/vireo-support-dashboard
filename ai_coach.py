import json
import os
from dotenv import load_dotenv
from groq import Groq


MODEL = "openai/gpt-oss-20b"


COACHING_SCHEMA = {
    "type": "object",
    "properties": {
        "summary": {
            "type": "string",
            "description": (
                "A concise manager-facing summary of the agent's performance "
                "signal based only on the supplied data."
            ),
        },
        "primary_signal": {
            "type": "string",
            "description": (
                "The most important performance signal that deserves "
                "attention."
            ),
        },
        "investigation_focus": {
            "type": "array",
            "items": {"type": "string"},
            "description": (
                "Two or three concrete things a manager should investigate."
            ),
        },
        "caution": {
            "type": "string",
            "description": (
                "An important caveat about interpreting the data, especially "
                "where the data does not establish causation or where evidence "
                "is insufficient."
            ),
        },
    },
    "required": [
        "summary",
        "primary_signal",
        "investigation_focus",
        "caution",
    ],
    "additionalProperties": False,
}


SYSTEM_PROMPT = """
You are an AI coaching assistant inside a customer-support performance
dashboard for Vireo Audio.

Your job is NOT to rank agents and NOT to decide who belongs in the review
group.

The deterministic analytics system has already selected the agent for review.
Your job is to interpret the supplied performance metrics and turn them into
a concise manager-facing coaching and investigation summary.

Rules:

1. Use ONLY the information supplied in the input.
2. Clearly distinguish observed metrics from suggested investigation areas.
3. Do not invent ticket examples, customer complaints, causes, or behaviors.
4. Do not imply that a suggested investigation has already been performed.
5. Do not claim causation from correlations or operational metrics.
6. Do not claim that an agent caused a cost, replacement, SLA breach, or poor
   CSAT unless the supplied data explicitly establishes causation.
7. Replacement cost exposure means cost associated with the agent's handled
   tickets. It is NOT proof that the agent caused the cost.
8. All monetary values are in Indian rupees (INR). Use ₹, never $.
9. A negative adjusted CSAT gap means the agent's actual CSAT is below the
   expected CSAT calculated by the deterministic analytics.
10. Do not reinterpret or replace the deterministic ranking.
11. Treat hardware/non-hardware work mix as context, not as proof of difficulty
    or agent fault.
12. If the available evidence is insufficient to explain a signal, explicitly
    say that further investigation is required.
13. Investigation suggestions should identify analyses or operational checks
    that a manager could perform; do not present them as findings.
14. Keep the output concise and useful to a support manager.
15. Do not use words such as "indicates", "suggests", "shows", or
    "contributes to" to describe an underlying cause unless that cause is
    directly supported by the supplied data.

16. Do not infer resolution quality, response tone, ticket complexity,
    workload difficulty, customer behavior, or agent efficiency from aggregate
    metrics alone.

17. Investigation focus should be framed as a question or verification step,
    not as an implied finding.

18. Do not use the word "correlation" unless an actual correlation was provided
    in the input.

19. When only aggregate metrics are available, explicitly distinguish:
    - observed signal
    - possible hypotheses
    - checks that could validate those hypotheses.
"""


def build_coaching_input(selected):
    """
    Convert the selected agent's deterministic metrics
    into a small, structured payload for the AI coach.
    """

    return {
        "agent": {
            "name": selected["name"],
            "agent_id": selected["agent_id"],
            "team": selected["team"],
        },
        "performance": {
            "actual_csat": float(selected["actual_csat"]),
            "expected_csat": float(selected["expected_csat"]),
            "adjusted_csat_gap": float(
                selected["adjusted_csat_gap"]
            ),
            "csat_responses": int(
                selected["csat_responses"]
            ),
        },
        "operational_context": {
            "tickets": int(selected["tickets"]),
            "hardware_ticket_pct": float(
                selected["hardware_ticket_pct"]
            ),
            "sla_breach_rate": float(
                selected["sla_breach_rate"]
            ),
            "median_handle_minutes": float(selected["median_handle_minutes"]
            ),
            "replacement_rate": float(
                selected["replacement_rate"]
            ),
            "replacement_cost_exposure": float(
                selected["replacement_cost_exposure"]
            ),
            "transfers": int(selected["transfers"]),
        },
    }


def generate_coaching_summary(selected):
    """
    Generate an AI-assisted coaching summary for one
    deterministically selected review candidate.
    """
    load_dotenv()

    api_key = os.getenv("GROQ_API_KEY")

    if not api_key:
        raise RuntimeError(
            "GROQ_API_KEY environment variable is not set."
        )

    client = Groq(api_key=api_key)

    coaching_input = build_coaching_input(selected)

    response = client.chat.completions.create(
        model=MODEL,
        messages=[
            {
                "role": "system",
                "content": SYSTEM_PROMPT,
            },
            {
                "role": "user",
                "content": (
                    "Analyze this selected review candidate:\n\n"
                    + json.dumps(
                        coaching_input,
                        indent=2,
                    )
                ),
            },
        ],
        response_format={
            "type": "json_schema",
            "json_schema": {
                "name": "agent_coaching_summary",
                "strict": True,
                "schema": COACHING_SCHEMA,
            },
        },
        temperature=0.2,
    )

    content = response.choices[0].message.content

    if not content:
        raise RuntimeError(
            "Groq returned an empty response."
        )

    return json.loads(content)