from pathlib import Path

import pandas as pd


DATA_DIR = Path(__file__).parent / "data"


def load_data():
    tickets = pd.read_csv(DATA_DIR / "tickets.csv")
    agents = pd.read_csv(DATA_DIR / "agents.csv")
    orders = pd.read_csv(DATA_DIR / "orders.csv")
    customers = pd.read_csv(DATA_DIR / "customers.csv")
    products = pd.read_csv(DATA_DIR / "products.csv")

    return tickets, agents, orders, customers, products

def validate_data(tickets, agents, orders, customers, products):
    errors = []

    # Ticket IDs should be unique
    if tickets["ticket_id"].duplicated().any():
        errors.append("Duplicate ticket_id values found.")

    # Agent IDs referenced by tickets must exist in roster
    unknown_agents = set(tickets["agent_id"].dropna()) - set(agents["agent_id"])
    if unknown_agents:
        errors.append(
            f"Tickets reference unknown agents: {sorted(unknown_agents)}"
        )

    # Customer IDs
    unknown_customers = (
        set(tickets["customer_id"].dropna())
        - set(customers["customer_id"])
    )
    if unknown_customers:
        errors.append(
            f"Tickets reference unknown customers: {sorted(unknown_customers)}"
        )

    # Product SKUs
    unknown_products = (
        set(tickets["product_sku"].dropna())
        - set(products["sku"])
    )
    if unknown_products:
        errors.append(
            f"Tickets reference unknown products: {sorted(unknown_products)}"
        )

    if errors:
        raise ValueError("\n".join(errors))

    return True

def normalize_timestamps(tickets):
    time_columns = [
        "created_at",
        "first_response_at",
        "resolved_at",
    ]

    for column in time_columns:
        tickets[column] = pd.to_datetime(
            tickets[column],
            errors="coerce"
        )

    # Legacy resolution timestamps are stored in UTC,
    # while the other exported timestamps are displayed in IST.
    legacy_mask = tickets["source_system"].eq("legacy_fd")

    tickets.loc[legacy_mask, "resolved_at"] = (
        tickets.loc[legacy_mask, "resolved_at"]
        + pd.Timedelta(hours=5, minutes=30)
    )

    return tickets

def attach_agent_roster(tickets, agents):
    tickets = tickets.copy()
    agents = agents.copy()

    tickets["resolved_at"] = pd.to_datetime(
        tickets["resolved_at"],
        errors="coerce"
    )

    agents["from_date"] = pd.to_datetime(
        agents["from_date"],
        errors="coerce"
    )

    agents["to_date"] = pd.to_datetime(
        agents["to_date"],
        errors="coerce"
    )

    # Temporary identifier so we can verify that each completed
    # ticket matched exactly one roster assignment.
    tickets["_ticket_row"] = range(len(tickets))

    roster_columns = [
        "agent_id",
        "name",
        "site",
        "team",
        "shift",
        "tier",
        "from_date",
        "to_date",
    ]

    merged = tickets.merge(
        agents[roster_columns],
        on="agent_id",
        how="left",
        suffixes=("", "_roster"),
    )

    # Only completed tickets have a resolution timestamp and therefore
    # can be matched to the roster assignment active at resolution.
    completed_mask = merged["status"].isin(["resolved", "closed"])

    active_roster = (
        (merged["resolved_at"] >= merged["from_date"])
        & (
            merged["to_date"].isna()
            | (merged["resolved_at"] <= merged["to_date"])
        )
    )

    valid = completed_mask & active_roster

    matched = merged[valid].copy()

    # Every completed ticket should match exactly one roster assignment.
    counts = matched["_ticket_row"].value_counts()

    duplicate_matches = counts[counts > 1]

    if not duplicate_matches.empty:
        raise ValueError(
            "Some completed tickets matched multiple active roster assignments: "
            f"{duplicate_matches.index.tolist()[:10]}"
        )

    completed_rows = set(
        merged.loc[completed_mask, "_ticket_row"]
    )

    matched_rows = set(matched["_ticket_row"])

    missing_completed = completed_rows - matched_rows

    if missing_completed:
        raise ValueError(
            f"{len(missing_completed)} completed tickets did not "
            "match an active roster assignment."
        )

    # For open/pending tickets there is no resolution date, so roster
    # assignment at resolution cannot be determined. Keep them in the
    # dataset with blank roster fields.
    roster_fields = [
        "name",
        "site",
        "team",
        "shift",
        "tier",
        "from_date",
        "to_date",
    ]

    roster_lookup = (
        matched[
            ["_ticket_row"] + roster_fields
        ]
        .drop_duplicates("_ticket_row")
    )

    result = merged.drop(
        columns=roster_fields,
        errors="ignore"
    ).merge(
        roster_lookup,
        on="_ticket_row",
        how="left",
    )

    result = result.drop(columns=["_ticket_row"])

    return result