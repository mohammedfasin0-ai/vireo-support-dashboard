import pandas as pd


def calculate_handle_time(tickets):
    tickets = tickets.copy()

    tickets["handle_time_minutes"] = (
        tickets["resolved_at"] - tickets["first_response_at"]
    ).dt.total_seconds() / 60

    return tickets

def validate_handle_time(tickets):
    invalid = tickets[
        tickets["handle_time_minutes"].notna()
        & (tickets["handle_time_minutes"] < 0)
    ]

    if not invalid.empty:
        raise ValueError(
            f"Found {len(invalid)} tickets with negative handle time."
        )

    return True

def calculate_agent_metrics(tickets):
    tickets = tickets.copy()

    tickets = calculate_handle_time(tickets)
    tickets = calculate_sla_metrics(tickets)

    completed = tickets[
        tickets["status"].isin(["resolved", "closed"])
    ].copy()
    completed = tickets[
        tickets["status"].isin(["resolved", "closed"])
    ].copy()

    metrics = (
        completed
        .groupby(
            [
                "agent_id",
                "name",
                "team",
                "tier",
                "shift",
            ]
        )
        .agg(
            tickets=("ticket_id", "count"),

            csat_responses=(
                "csat_score",
                lambda x: x.notna().sum()
            ),

            csat=(
                "csat_score",
                "mean"
            ),

            median_handle_minutes=(
                "handle_time_minutes",
                "median"
            ),

            p90_handle_minutes=(
                "handle_time_minutes",
                lambda x: x.quantile(0.90)
            ),

            sla_breaches=(
                "sla_breach",
                "sum"
            ),

            replacements=(
                "replacement_issued",
                lambda x: (x == "Y").sum()
            ),

            transfers=(
                "transfers",
                "sum"
            ),
        )
        .reset_index()
    )

    # ---------------------------------------------------------
    # CHANNEL MIX
    # ---------------------------------------------------------

    channel_counts = (
        completed
        .groupby(["agent_id", "channel"])
        .size()
        .unstack(fill_value=0)
        .reindex(
            columns=["chat", "email", "voice", "social"],
            fill_value=0
        )
        .rename(
            columns={
                "chat": "chat_tickets",
                "email": "email_tickets",
                "voice": "voice_tickets",
                "social": "social_tickets",
            }
        )
    )

    # ---------------------------------------------------------
    # CHANNEL-SPECIFIC SLA BREACH COUNTS
    # ---------------------------------------------------------

    channel_breaches = (
        completed[completed["sla_breach"]]
        .groupby(["agent_id", "channel"])
        .size()
        .unstack(fill_value=0)
        .reindex(
            columns=["chat", "email", "voice", "social"],
            fill_value=0
        )
        .rename(
            columns={
                "chat": "chat_breaches",
                "email": "email_breaches",
                "voice": "voice_breaches",
                "social": "social_breaches",
            }
        )
    )

    # Add channel counts to agent metrics
    metrics = metrics.merge(
        channel_counts,
        on="agent_id",
        how="left"
    )

    # Add channel breach counts
    metrics = metrics.merge(
        channel_breaches,
        on="agent_id",
        how="left"
    )

    # Agents with zero breaches get 0 instead of NaN
    breach_columns = [
        "chat_breaches",
        "email_breaches",
        "voice_breaches",
        "social_breaches",
    ]

    metrics[breach_columns] = metrics[breach_columns].fillna(0)

    # ---------------------------------------------------------
    # OVERALL RATES
    # ---------------------------------------------------------

    metrics["csat_response_rate"] = (
        metrics["csat_responses"] / metrics["tickets"]
    )

    metrics["replacement_rate"] = (
        metrics["replacements"] / metrics["tickets"]
    )

    metrics["sla_breach_rate"] = (
        metrics["sla_breaches"] / metrics["tickets"]
    )

    # ---------------------------------------------------------
    # CHANNEL-SPECIFIC SLA RATES
    # ---------------------------------------------------------

    metrics["chat_breach_rate"] = (
        metrics["chat_breaches"]
        / metrics["chat_tickets"].replace(0, pd.NA)
    )

    metrics["email_breach_rate"] = (
        metrics["email_breaches"]
        / metrics["email_tickets"].replace(0, pd.NA)
    )

    metrics["voice_breach_rate"] = (
        metrics["voice_breaches"]
        / metrics["voice_tickets"].replace(0, pd.NA)
    )
    metrics["social_breach_rate"] = (
        metrics["social_breaches"]
        / metrics["social_tickets"].replace(0, pd.NA)
    )

    # ---------------------------------------------------------
    # TEAM-RELATIVE PERFORMANCE
    # ---------------------------------------------------------

    team_baseline = (
        metrics
        .groupby("team")
        .agg(
            team_avg_csat=("csat", "mean"),
            team_avg_sla_breach_rate=("sla_breach_rate", "mean"),
            team_avg_replacement_rate=("replacement_rate", "mean"),
        )
        .reset_index()
    )

    metrics = metrics.merge(
        team_baseline,
        on="team",
        how="left"
    )

    metrics["csat_gap_vs_team"] = (
        metrics["csat"] - metrics["team_avg_csat"]
    )

    metrics["sla_gap_vs_team"] = (
        metrics["sla_breach_rate"]
        - metrics["team_avg_sla_breach_rate"]
    )

    metrics["replacement_gap_vs_team"] = (
        metrics["replacement_rate"]
        - metrics["team_avg_replacement_rate"]
    )

    return metrics

SLA_TARGET_MINUTES = {
    "chat": 15,
    "voice": 120,
    "social": 240,
    "email": 480,
}


def calculate_sla_metrics(tickets):
    tickets = tickets.copy()

    tickets["first_response_minutes"] = (
        tickets["first_response_at"] - tickets["created_at"]
    ).dt.total_seconds() / 60

    tickets["sla_target_minutes"] = tickets["channel"].map(
        SLA_TARGET_MINUTES
    )

    tickets["sla_breach"] = (
        tickets["first_response_minutes"]
        > tickets["sla_target_minutes"]
    )

    return tickets

HARDWARE_CATEGORIES = {
    "Charging & Battery",
    "Warranty & Repair",
    "Returns & Refunds",
}


def calculate_adjusted_csat_ranking(
    tickets,
    min_csat_responses=30,
):
    """
    Rank Tier 1 agents by CSAT relative to the CSAT expected
    from their hardware/non-hardware workload mix.

    The expected CSAT is calculated from the agent's team,
    excluding the agent themselves (leave-one-agent-out benchmark).

    Returns one row per eligible Tier 1 agent.
    """

    required_columns = {
        "agent_id",
        "name",
        "team",
        "tier",
        "status",
        "csat_score",
        "category",
    }

    missing = required_columns - set(tickets.columns)

    if missing:
        raise ValueError(
            f"Missing columns for adjusted CSAT ranking: {sorted(missing)}"
        )

    data = tickets.copy()

    # Only completed tickets can have a valid completed-ticket CSAT.
    data = data[
        data["status"].isin(["resolved", "closed"])
    ].copy()

    # CSAT is only meaningful when a customer actually responded.
    data = data[data["csat_score"].notna()].copy()

    # Tier 2 must not be compared with Tier 1.
    data = data[data["tier"] == 1].copy()

    data["hardware_related"] = data["category"].isin(
        HARDWARE_CATEGORIES
    )

    results = []

    for agent_id, agent_data in data.groupby("agent_id"):

        if len(agent_data) < min_csat_responses:
            continue

        name = agent_data["name"].iloc[0]
        team = agent_data["team"].iloc[0]

        # Team benchmark excluding this agent.
        benchmark = data[
            (data["team"] == team)
            & (data["agent_id"] != agent_id)
        ].copy()

        hardware_benchmark = benchmark[
            benchmark["hardware_related"]
        ]

        non_hardware_benchmark = benchmark[
            ~benchmark["hardware_related"]
        ]

        # We need both groups to calculate a workload-adjusted
        # expectation.
        if (
            hardware_benchmark.empty
            or non_hardware_benchmark.empty
        ):
            continue

        actual_csat = agent_data["csat_score"].mean()
        csat_responses = len(agent_data)

        # Use the agent's CSAT-response mix rather than raw ticket mix.
        # This keeps the expected score aligned with the observations
        # used to calculate actual CSAT.
        hardware_share = agent_data["hardware_related"].mean()

        team_hardware_csat = (
            hardware_benchmark["csat_score"].mean()
        )

        team_non_hardware_csat = (
            non_hardware_benchmark["csat_score"].mean()
        )

        expected_csat = (
            hardware_share * team_hardware_csat
            + (1 - hardware_share) * team_non_hardware_csat
        )

        adjusted_gap = actual_csat - expected_csat

        results.append({
            "agent_id": agent_id,
            "name": name,
            "team": team,
            "csat_responses": csat_responses,
            "actual_csat": actual_csat,
            "hardware_share": hardware_share,
            "team_hardware_csat": team_hardware_csat,
            "team_non_hardware_csat": team_non_hardware_csat,
            "expected_csat": expected_csat,
            "adjusted_csat_gap": adjusted_gap,
        })

    ranking = pd.DataFrame(results)

    if ranking.empty:
        return ranking

    ranking = ranking.sort_values(
        "adjusted_csat_gap",
        ascending=True,
    ).reset_index(drop=True)

    ranking["review_rank"] = ranking.index + 1

    return ranking

def build_review_table(tickets, products, min_csat_responses=30):
    """
    Build the final Tier 1 review table.

    Ranking is determined by workload-adjusted CSAT gap.
    Other operational metrics are included as context only.
    """

    adjusted = calculate_adjusted_csat_ranking(
        tickets,
        min_csat_responses=min_csat_responses,
    )

    if adjusted.empty:
        return adjusted

    data = tickets.copy()

    completed = data[
        data["status"].isin(["resolved", "closed"])
    ].copy()

    completed["handle_time_minutes"] = (
        pd.to_datetime(completed["resolved_at"], errors="coerce")
        - pd.to_datetime(completed["first_response_at"], errors="coerce")
    ).dt.total_seconds() / 60

    completed["first_response_minutes"] = (
        pd.to_datetime(completed["first_response_at"], errors="coerce")
        - pd.to_datetime(completed["created_at"], errors="coerce")
    ).dt.total_seconds() / 60

    completed["sla_target_minutes"] = completed["channel"].map(
        SLA_TARGET_MINUTES
    )

    completed["sla_breach"] = (
        completed["first_response_minutes"].notna()
        & completed["sla_target_minutes"].notna()
        & (
            completed["first_response_minutes"]
            > completed["sla_target_minutes"]
        )
    )

    completed["hardware_related"] = completed["category"].isin(
        HARDWARE_CATEGORIES
    )

    # Product unit cost is required for the policy-defined
    # replacement cost calculation.
    product_costs = products[["sku", "unit_cost_inr"]].copy()

    completed = completed.merge(
        product_costs,
        left_on="product_sku",
        right_on="sku",
        how="left",
    )

    completed["replacement_cost_exposure"] = 0.0

    replacement_mask = completed["replacement_issued"].eq("Y")

    completed.loc[replacement_mask, "replacement_cost_exposure"] = (
        completed.loc[replacement_mask, "unit_cost_inr"] + 340
    )

    # Operational metrics.
    operational = (
        completed[completed["tier"] == 1]
        .groupby(["agent_id", "name", "team"])
        .agg(
            tickets=("ticket_id", "count"),
            median_handle_minutes=(
                "handle_time_minutes",
                "median",
            ),
            p90_handle_minutes=(
                "handle_time_minutes",
                lambda x: x.quantile(0.90),
            ),
            sla_breaches=("sla_breach", "sum"),
            sla_breach_rate=("sla_breach", "mean"),
            replacements=(
                "replacement_issued",
                lambda x: (x == "Y").sum(),
            ),
            replacement_rate=(
                "replacement_issued",
                lambda x: (x == "Y").mean(),
            ),
            transfers=("transfers", "sum"),
            hardware_ticket_pct=(
                "hardware_related",
                "mean",
            ),
            replacement_cost_exposure=(
                "replacement_cost_exposure",
                "sum",
            ),
        )
        .reset_index()
    )

    result = adjusted.merge(
        operational,
        on=["agent_id", "name", "team"],
        how="left",
    )

    result["hardware_ticket_pct"] *= 100

    # Keep the table readable for the dashboard.
    result["actual_csat"] = result["actual_csat"].round(2)
    result["expected_csat"] = result["expected_csat"].round(2)
    result["adjusted_csat_gap"] = result["adjusted_csat_gap"].round(2)
    result["hardware_ticket_pct"] = result["hardware_ticket_pct"].round(1)
    result["sla_breach_rate"] = (
        result["sla_breach_rate"] * 100
    ).round(1)
    result["replacement_rate"] = (
        result["replacement_rate"] * 100
    ).round(1)
    result["median_handle_minutes"] = (
        result["median_handle_minutes"].round(0)
    )
    result["p90_handle_minutes"] = (
        result["p90_handle_minutes"].round(0)
    )
    result["replacement_cost_exposure"] = (
        result["replacement_cost_exposure"].round(0)
    )

    return result.head(10)

def calculate_work_type_diagnostics(
    tickets,
    review_agents=None,
    min_responses=10,
):
    required_columns = {
        "agent_id",
        "name",
        "team",
        "tier",
        "status",
        "csat_score",
        "category",
    }

    missing = required_columns - set(tickets.columns)
    if missing:
        raise ValueError(
            f"Missing columns for work-type diagnostics: {sorted(missing)}"
        )

    # ---------------------------------------------------------
    # 1. Build the FULL eligible Tier 1 population first.
    #    Do NOT filter to review_agents yet.
    # ---------------------------------------------------------
    data = tickets.copy()

    data = data[
        data["status"].isin(["resolved", "closed"])
        & data["csat_score"].notna()
        & (data["tier"] == 1)
    ].copy()

    # Same workload definition used by the ranking.
    data["work_type"] = data["category"].isin(
        HARDWARE_CATEGORIES
    ).map({
        True: "hardware",
        False: "non_hardware",
    })

    # ---------------------------------------------------------
    # 2. Calculate each agent's performance within each
    #    work type.
    # ---------------------------------------------------------
    results = []

    # These are the agents we actually want to display.
    agents_to_review = (
        set(review_agents)
        if review_agents is not None
        else set(data["agent_id"].unique())
    )

    for agent_id in agents_to_review:

        agent_data = data[data["agent_id"] == agent_id]

        if agent_data.empty:
            continue

        name = agent_data["name"].iloc[0]
        team = agent_data["team"].iloc[0]

        for work_type in ["hardware", "non_hardware"]:

            # The selected agent's performance in this work type
            agent_work = agent_data[
                agent_data["work_type"] == work_type
            ]

            if len(agent_work) < min_responses:
                continue

            # -------------------------------------------------
            # IMPORTANT:
            # Benchmark against the FULL eligible population
            # in the same team/work type, excluding this agent.
            # -------------------------------------------------
            benchmark = data[
                (data["team"] == team)
                & (data["agent_id"] != agent_id)
                & (data["work_type"] == work_type)
            ]

            if benchmark.empty:
                continue

            actual_csat = agent_work["csat_score"].mean()
            team_csat = benchmark["csat_score"].mean()

            results.append({
                "agent_id": agent_id,
                "name": name,
                "team": team,
                "work_type": work_type,
                "csat_responses": len(agent_work),
                "actual_csat": actual_csat,
                "team_csat": team_csat,
                "csat_gap_vs_team": actual_csat - team_csat,
            })

    diagnostics = pd.DataFrame(results)

    if diagnostics.empty:
        return diagnostics

    diagnostics = diagnostics.sort_values(
        ["agent_id", "work_type"]
    ).reset_index(drop=True)

    return diagnostics


def build_population_comparison(tickets, min_csat_responses=30):
    """
    Build the full Tier 1 agent population using the same
    adjusted-CSAT methodology as the review ranking.

    This is for visualization only; it does not change
    the review ranking.
    """
    ranking = calculate_adjusted_csat_ranking(
        tickets,
        min_csat_responses=min_csat_responses,
    )

    if ranking.empty:
        return ranking

    population = ranking.copy()

    population["review_candidate"] = population["review_rank"] <= 10

    population = population.sort_values(
        "adjusted_csat_gap",
        ascending=True,
    ).reset_index(drop=True)

    return population