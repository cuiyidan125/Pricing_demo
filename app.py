"""Inventory dashboard — the demo's opening screen.

Written for a used-vehicle manager, so it leads with dollars and days rather than
architecture. Renders only; every number comes from the skill layer.
"""

from __future__ import annotations

from datetime import datetime, timezone

import pandas as pd
import streamlit as st

from pricing_agent.config import load_config
from pricing_agent.mcp_clients import CapacityClient, MockTransport, VautoClient
from pricing_agent.skills.single_vehicle import analyze

AS_OF = datetime(2026, 7, 21, 14, 0, tzinfo=timezone.utc)

st.set_page_config(
    page_title="Used Vehicle Pricing Advisor",
    page_icon="🚗",
    layout="wide",
)


@st.cache_data(show_spinner=False)
def load_inventory(as_of: datetime) -> list[dict]:
    return VautoClient(MockTransport(as_of=as_of)).get_dealer_inventory().data


@st.cache_data(show_spinner=False)
def load_capacity(as_of: datetime) -> dict:
    return CapacityClient(MockTransport(as_of=as_of)).get_dealer_capacity().data


@st.cache_data(show_spinner=False)
def analyze_vehicle(vehicle_id: str, as_of: datetime) -> dict:
    """Cached per vehicle. Without this, every widget interaction re-runs the
    simulation and the page feels broken."""
    return analyze(vehicle_id, MockTransport(as_of=as_of))


def severity_rank(warnings: list[dict]) -> int:
    order = ["INFO", "LOW", "MEDIUM", "HIGH", "CRITICAL", "BLOCKING"]
    return max((order.index(w["severity"]) for w in warnings), default=-1)


def flag_label(result: dict) -> str:
    codes = {w["code"] for w in result["warnings"]}
    if "BREAK_EVEN_EXCEEDS_MARKET_VALUE" in codes:
        return "🔴 Underwater"
    if any(c.startswith("P50_PROJECTED_INVENTORY_AGE_OVER_120") for c in codes):
        return "🟠 Severely aged"
    if "LOW_VALUATION_CONFIDENCE" in codes:
        return "🟡 Thin comps"
    if "CURRENT_PRICE_POOR_DEAL" in codes:
        return "🟡 Overpriced"
    if any(c.startswith("P50_PROJECTED_INVENTORY_AGE_OVER_90") for c in codes):
        return "🟡 Aging"
    return "🟢 Healthy"


# --- header ---------------------------------------------------------------------------

config = load_config()
st.title("Used Vehicle Pricing Advisor")
st.caption(
    f"DEALER-1001 · as of {AS_OF:%d %b %Y %H:%M} UTC · "
    f"assumptions `{config.assumption_version}` · model `{config.model_version}`"
)

inventory = load_inventory(AS_OF)
capacity = load_capacity(AS_OF)

with st.spinner(f"Pricing {len(inventory)} vehicles…"):
    results = {v["vehicle_id"]: analyze_vehicle(v["vehicle_id"], AS_OF) for v in inventory}

# --- KPI row --------------------------------------------------------------------------

slots = capacity["total_physical_slots"]
units = capacity["current_inventory"]
utilization = units / slots

aged = sum(1 for v in inventory if v["days_in_inventory"] > 90)
underwater = sum(
    1
    for r in results.values()
    if any(w["code"] == "BREAK_EVEN_EXCEEDS_MARKET_VALUE" for w in r["warnings"])
)
cash_tied_up = sum(
    r["break_even_analysis"]["cost_components"]["acquisition_cost"]
    + r["break_even_analysis"]["cost_components"]["reconditioning_cost"]
    + r["break_even_analysis"]["cost_components"]["transportation_cost"]
    + r["break_even_analysis"]["cost_components"]["auction_fee"]
    for r in results.values()
)
blocked = sum(
    1 for r in results.values() if any(w["blocks_publication"] for w in r["warnings"])
)

c1, c2, c3, c4, c5 = st.columns(5)
c1.metric("Units on lot", f"{units}", f"{slots - units} open slots")
c2.metric(
    "Utilization",
    f"{utilization:.0%}",
    f"{utilization - capacity['target_utilization']:+.0%} vs target",
    delta_color="inverse",
)
# delta_color="off" on the text deltas: Streamlit infers direction from a leading sign,
# so a bare string renders as a green up-arrow and makes bad news read as good.
c3.metric("Over 90 days", f"{aged}", f"{aged / len(inventory):.0%} of lot", delta_color="off")
c4.metric("Cash tied up", f"${cash_tied_up:,.0f}")
c5.metric("Cannot publish", f"{blocked}", "policy blocked", delta_color="off")

if underwater:
    st.error(
        f"**{underwater} vehicle(s) are underwater** — break-even exceeds market value. "
        "These cannot be sold at a profit today and need a loss-minimization decision.",
        icon="⚠️",
    )

st.divider()

# --- inventory table ------------------------------------------------------------------

rows = []
for vehicle in inventory:
    vid = vehicle["vehicle_id"]
    result = results[vid]
    scenario = next(
        s
        for s in result["pricing_scenarios"]
        if s["strategy"] == result["recommended_strategy"]["strategy"]
    )
    current = vehicle.get("current_list_price")
    recommended = scenario["proposed_list_price"]

    rows.append(
        {
            "Flag": flag_label(result),
            "Stock": vid,
            "Vehicle": f"{vehicle['year']} {vehicle['make']} {vehicle['model']}",
            "Days": vehicle["days_in_inventory"],
            "Current": current,
            "Recommended": recommended,
            "Δ Price": (recommended - current) if current else None,
            "Strategy": result["recommended_strategy"]["strategy"].replace("_", " ").title(),
            "P50 days to sell": scenario["additional_days_to_sale"]["p50"],
            "P50 gross": scenario["expected_front_end_gross"]["p50"],
            "Sold in 30d": scenario["sale_probabilities"]["within_30_days"],
            "_rank": severity_rank(result["warnings"]),
        }
    )

frame = pd.DataFrame(rows).sort_values("_rank", ascending=False).drop(columns=["_rank"])

st.subheader("Inventory")
st.caption("Sorted by exception severity. Open a vehicle from the sidebar for the full analysis.")

st.dataframe(
    frame,
    use_container_width=True,
    hide_index=True,
    column_config={
        "Current": st.column_config.NumberColumn(format="$%d"),
        "Recommended": st.column_config.NumberColumn(format="$%d"),
        "Δ Price": st.column_config.NumberColumn(format="$%d"),
        "P50 days to sell": st.column_config.NumberColumn(format="%d"),
        "P50 gross": st.column_config.NumberColumn(format="$%d"),
        "Sold in 30d": st.column_config.ProgressColumn(
            format="%.0f%%", min_value=0, max_value=1
        ),
    },
)

st.info(
    "Forecasts are a **configured prototype simulation**, not a trained prediction. "
    "Every assumption behind these numbers is in `config/assumptions/` and shown in the "
    "Assumptions panel on each vehicle.",
    icon="ℹ️",
)
