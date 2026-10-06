from ai_coach import generate_coaching_summary


selected = {
    "name": "Siddharth Kapoor",
    "agent_id": "A3004",
    "team": "Chat Frontline",

    "actual_csat": 2.96,
    "expected_csat": 3.34,
    "adjusted_csat_gap": -0.38,
    "csat_responses": 122,

    "tickets": 286,
    "hardware_ticket_pct": 36.0,
    "sla_breach_rate": 8.7,
    "median_handle_minutes": 26,
    "replacement_rate": 27.6,
    "replacement_cost_exposure": 143600,
    "transfers": 22,
}


result = generate_coaching_summary(selected)

print("\nAI COACHING SUMMARY\n")
print(result["summary"])

print("\nPRIMARY SIGNAL\n")
print(result["primary_signal"])

print("\nINVESTIGATION FOCUS\n")
for item in result["investigation_focus"]:
    print("-", item)

print("\nCAUTION\n")
print(result["caution"])