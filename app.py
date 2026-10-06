from data_loader import (
    load_data,
    validate_data,
    normalize_timestamps,
    attach_agent_roster,
)

from metrics import (
    calculate_agent_metrics,
    build_review_table,
    calculate_work_type_diagnostics,
    build_population_comparison,
)

from ai_coach import generate_coaching_summary

import pandas as pd
import plotly.express as px
import streamlit as st


# ============================================================
# PAGE SETUP
# ============================================================

st.set_page_config(
    page_title="Vireo Support Performance",
    page_icon="🎧",
    layout="wide",
)

st.title("Vireo Support Performance")
st.caption(
    "Tier 1 agent review for training prioritization"
)


# ============================================================
# LOAD + VALIDATE DATA
# ============================================================

tickets, agents, orders, customers, products = load_data()

validate_data(
    tickets,
    agents,
    orders,
    customers,
    products,
)

tickets = normalize_timestamps(tickets)

tickets = attach_agent_roster(
    tickets,
    agents,
)


# ============================================================
# CALCULATE METRICS
# ============================================================

metrics = calculate_agent_metrics(tickets)

review_table = build_review_table(
    tickets,
    products,
)

population_comparison = build_population_comparison(tickets)

review_agents = review_table["agent_id"].tolist()

work_type_diagnostics = calculate_work_type_diagnostics(
    tickets,
    review_agents=review_agents,
)


# ============================================================
# TOP-LEVEL BUSINESS METRICS
# ============================================================

completed = tickets[
    tickets["status"].isin(["resolved", "closed"])
].copy()

total_tickets = len(tickets)

overall_csat = completed["csat_score"].mean()

replacement_count = (
    completed["replacement_issued"] == "Y"
).sum()

replacement_rate = (
    replacement_count / len(completed)
    if len(completed) > 0
    else 0
)

total_replacement_exposure = 0.0

completed_with_cost = completed.merge(
    products[["sku", "unit_cost_inr"]],
    left_on="product_sku",
    right_on="sku",
    how="left",
)

replacement_mask = (
    completed_with_cost["replacement_issued"] == "Y"
)

completed_with_cost.loc[
    replacement_mask,
    "replacement_cost_exposure",
] = (
    completed_with_cost.loc[
        replacement_mask,
        "unit_cost_inr",
    ]
    + 340
)

total_replacement_exposure = (
    completed_with_cost["replacement_cost_exposure"]
    .fillna(0)
    .sum()
)


# ============================================================
# KPI CARDS
# ============================================================

st.subheader("Overview")

col1, col2, col3, col4 = st.columns(4)

with col1:
    st.metric(
        "Total tickets",
        f"{total_tickets:,}",
    )

with col2:
    st.metric(
        "Overall CSAT",
        f"{overall_csat:.2f} / 5",
    )

with col3:
    st.metric(
        "Replacement rate",
        f"{replacement_rate * 100:.1f}%",
    )

with col4:
    st.metric(
        "Agents for review",
        len(review_table),
    )


st.divider()


# ============================================================
# BUSINESS CONTEXT
# ============================================================

st.subheader("Review objective")

st.write(
    """
    The review list identifies Tier 1 agents whose observed CSAT is
    furthest below the level expected from the mix of hardware and
    non-hardware work they handled.

    These are review candidates, not proof of individual fault.
    Operational metrics and work-type diagnostics provide additional
    context for investigation.
    """
)


# ============================================================
# BOTTOM 10 TABLE
# ============================================================

st.subheader("Tier 1 review candidates")

display_table = review_table[
    [
        "review_rank",
        "agent_id",
        "name",
        "team",
        "actual_csat",
        "expected_csat",
        "adjusted_csat_gap",
        "csat_responses",
        "tickets",
        "hardware_ticket_pct",
        "sla_breach_rate",
        "median_handle_minutes",
        "replacement_rate",
        "replacement_cost_exposure",
        "transfers",
    ]
].copy()

display_table = display_table.rename(
    columns={
        "review_rank": "Rank",
        "agent_id": "Agent ID",
        "name": "Agent",
        "team": "Team",
        "actual_csat": "Actual CSAT",
        "expected_csat": "Expected CSAT",
        "adjusted_csat_gap": "CSAT gap",
        "csat_responses": "CSAT responses",
        "tickets": "Tickets",
        "hardware_ticket_pct": "Hardware %",
        "sla_breach_rate": "SLA breach %",
        "median_handle_minutes": "Median handle (min)",
        "replacement_rate": "Replacement %",
        "replacement_cost_exposure": "Replacement exposure",
        "transfers": "Transfers",
    }
)

st.dataframe(
    display_table,
    use_container_width=True,
    hide_index=True,
    column_config={
        "Actual CSAT": st.column_config.NumberColumn(
            format="%.2f"
        ),
        "Expected CSAT": st.column_config.NumberColumn(
            format="%.2f"
        ),
        "CSAT gap": st.column_config.NumberColumn(
            format="%.2f"
        ),
        "Hardware %": st.column_config.NumberColumn(
            format="%.1f%%"
        ),
        "SLA breach %": st.column_config.NumberColumn(
            format="%.1f%%"
        ),
        "Replacement %": st.column_config.NumberColumn(
            format="%.1f%%"
        ),
        "Replacement exposure": st.column_config.NumberColumn(
            format="₹%.0f"
        ),
    },
)

# ============================================================
# POPULATION COMPARISON
# ============================================================

st.subheader("Tier 1 CSAT performance relative to expected")

st.caption(
    "Adjusted CSAT gap across the eligible Tier 1 population. "
    "The 10 review candidates are the agents furthest below "
    "their expected CSAT after accounting for work mix."
)

if population_comparison.empty:

    st.info(
        "Not enough data to build the population comparison."
    )

else:

    chart_data = population_comparison.copy()

    chart_data["label"] = (
        chart_data["name"]
        + " — "
        + chart_data["team"]
    )

    chart_data["group"] = chart_data[
        "review_candidate"
    ].map(
        {
            True: "Review candidate",
            False: "Other Tier 1 agent",
        }
    )

    fig = px.bar(
        chart_data,
        x="adjusted_csat_gap",
        y="label",
        orientation="h",
        color="group",
        hover_data={
            "adjusted_csat_gap": ":.2f",
            "actual_csat": ":.2f",
            "expected_csat": ":.2f",
            "csat_responses": True,
            "group": True,
            "label": False,
        },
        labels={
            "adjusted_csat_gap": "Adjusted CSAT gap vs expected",
            "label": "",
            "group": "",
            "actual_csat": "Actual CSAT",
            "expected_csat": "Expected CSAT",
            "csat_responses": "CSAT responses",
        },
    )

    fig.add_vline(
        x=0,
        line_dash="dash",
        line_width=1,
        annotation_text="Expected performance",
        annotation_position="top",
    )

    fig.update_layout(
        height=max(550, len(chart_data) * 28),
        margin=dict(l=10, r=20, t=40, b=10),
        legend_title_text="",
    )

    st.plotly_chart(
        fig,
        use_container_width=True,
    )

# ============================================================
# AGENT DETAIL
# ============================================================

st.divider()

st.subheader("Agent detail")

agent_options = review_table[
    ["agent_id", "name", "team"]
].drop_duplicates()

agent_labels = {
    row["agent_id"]: (
        f'{row["name"]} — {row["team"]} '
        f'({row["agent_id"]})'
    )
    for _, row in agent_options.iterrows()
}

selected_agent_id = st.selectbox(
    "Select a review candidate",
    options=agent_options["agent_id"].tolist(),
    format_func=lambda agent_id: agent_labels[agent_id],
)


# ============================================================
# SELECTED AGENT METRICS
# ============================================================

selected = review_table[
    review_table["agent_id"] == selected_agent_id
].iloc[0]

agent_col1, agent_col2, agent_col3, agent_col4 = st.columns(4)

with agent_col1:
    st.metric(
        "Actual CSAT",
        f'{selected["actual_csat"]:.2f}',
    )

with agent_col2:
    st.metric(
        "Expected CSAT",
        f'{selected["expected_csat"]:.2f}',
    )

with agent_col3:
    st.metric(
        "Adjusted gap",
        f'{selected["adjusted_csat_gap"]:.2f}',
    )

with agent_col4:
    st.metric(
        "CSAT responses",
        f'{int(selected["csat_responses"]):,}',
    )


# ============================================================
# OPERATIONAL CONTEXT
# ============================================================

st.markdown("### Operational context")

op_col1, op_col2, op_col3, op_col4, op_col5 = st.columns(5)

with op_col1:
    st.metric(
        "Tickets",
        f'{int(selected["tickets"]):,}',
    )

with op_col2:
    st.metric(
        "SLA breach",
        f'{selected["sla_breach_rate"]:.1f}%',
    )

with op_col3:
    st.metric(
        "Median handle",
        f'{selected["median_handle_minutes"]:.0f} min',
    )

with op_col4:
    st.metric(
        "Replacement rate",
        f'{selected["replacement_rate"]:.1f}%',
    )

with op_col5:
    st.metric(
        "Transfers",
        f'{int(selected["transfers"]):,}',
    )

st.write(
    f'Associated replacement-cost exposure: '
    f'₹{selected["replacement_cost_exposure"]:,.0f}'
)

# ============================================================
# WORK-TYPE DIAGNOSTIC
# ============================================================

st.markdown("### CSAT by work type")

agent_diagnostics = work_type_diagnostics[
    work_type_diagnostics["agent_id"] == selected_agent_id
].copy()

if agent_diagnostics.empty:

    st.info(
        "No work-type diagnostic data is available "
        "for this agent."
    )

else:

    diagnostic_display = agent_diagnostics[
        [
            "work_type",
            "csat_responses",
            "actual_csat",
            "team_csat",
            "csat_gap_vs_team",
        ]
    ].copy()

    diagnostic_display["work_type"] = (
        diagnostic_display["work_type"]
        .replace(
            {
                "hardware": "Hardware",
                "non_hardware": "Non-hardware",
            }
        )
    )

    diagnostic_display = diagnostic_display.rename(
        columns={
            "work_type": "Work type",
            "csat_responses": "CSAT responses",
            "actual_csat": "Agent CSAT",
            "team_csat": "Team CSAT",
            "csat_gap_vs_team": "Gap vs team",
        }
    )

    st.dataframe(
        diagnostic_display,
        use_container_width=True,
        hide_index=True,
        column_config={
            "Agent CSAT": st.column_config.NumberColumn(
                format="%.2f"
            ),
            "Team CSAT": st.column_config.NumberColumn(
                format="%.2f"
            ),
            "Gap vs team": st.column_config.NumberColumn(
                format="%.2f"
            ),
        },
    )


# ============================================================
# INTERPRETATION
# ============================================================

st.markdown("### Review signal")

diagnostic_lookup = (
    agent_diagnostics
    .set_index("work_type")
)

if (
    "hardware" in diagnostic_lookup.index
    and "non_hardware" in diagnostic_lookup.index
):

    hardware_gap = diagnostic_lookup.loc[
        "hardware",
        "csat_gap_vs_team",
    ]

    non_hardware_gap = diagnostic_lookup.loc[
        "non_hardware",
        "csat_gap_vs_team",
    ]

    if hardware_gap < -0.10 and non_hardware_gap >= 0:

        st.info(
            "The CSAT gap is concentrated in hardware work. "
            "The agent is at or above the team benchmark on "
            "non-hardware work, so the hardware workflow is a "
            "useful area for investigation."
        )

    elif hardware_gap >= 0 and non_hardware_gap < -0.10:

        st.info(
            "The CSAT gap is concentrated in non-hardware work. "
            "Hardware CSAT is at or above the team benchmark."
        )

    elif hardware_gap < -0.10 and non_hardware_gap < -0.10:

        st.warning(
            "The agent is below the team benchmark in both "
            "hardware and non-hardware work. This suggests a "
            "broader performance signal, although it is not "
            "evidence of causation."
        )

    else:

        st.info(
            "The work-type breakdown does not show a strong "
            "single-work-type signal. Review the operational "
            "metrics alongside the CSAT gap."
        )

else:

    st.info(
        "There are not enough responses in both work types "
        "to produce a full work-type comparison."
    )

# ============================================================
# AI COACHING SUMMARY
# ============================================================

st.markdown("### 🤖 AI coaching & investigation")

st.caption(
    "Optional AI interpretation of the selected agent's metrics. "
    "The deterministic review ranking remains the source of truth."
)

if st.button("Generate AI coaching summary"):

    with st.spinner("Generating coaching summary..."):

        try:
            coaching = generate_coaching_summary(selected)

            st.markdown("Summary")
            st.write(coaching["summary"])

            st.markdown("Primary signal")
            st.write(coaching["primary_signal"])

            st.markdown("Investigation focus")

            for item in coaching["investigation_focus"]:
                st.markdown(f"- {item}")

            st.markdown("Caution")
            st.info(coaching["caution"])

        except Exception as e:

            st.error(
                f"AI coaching failed: {e}"
            )
# ============================================================
# DATA QUALITY / METHODOLOGY
# ============================================================

st.divider()

with st.expander("Methodology and data notes"):

    st.markdown(
        """
        Review ranking

        Agents are ranked by adjusted CSAT gap: actual CSAT minus
        expected CSAT based on their hardware/non-hardware workload
        mix and the corresponding team benchmarks.

        CSAT

        Only tickets with a recorded CSAT response are included in
        CSAT averages. Missing CSAT responses are not treated as zero.

        Operational metrics

        SLA breach, handle time, replacements and transfers are shown
        as contextual metrics rather than being combined into the
        ranking score.

        Replacement exposure

        Replacement exposure uses the support-policy calculation of
        product unit cost + ₹340 logistics. It represents associated
        exposure, not savings or costs proven to be caused by an agent.

        Work-type diagnostics

        Hardware includes Charging & Battery, Warranty & Repair, and
        Returns & Refunds. Work-type comparisons require at least
        10 CSAT responses in the relevant work type.

        Important

        The review list identifies candidates for investigation and
        training prioritization. It does not establish individual
        causation.
        """
    )