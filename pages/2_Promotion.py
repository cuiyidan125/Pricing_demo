"""Event promotion planner — demo beat 4.

Leads with feasibility, because that is the question actually being asked. Reports mean
and P90 incremental units alongside P50: unit sales are integers, so a real effect
smaller than one car is invisible at the median.
"""

from __future__ import annotations

from datetime import datetime, timezone

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from pricing_agent.mcp_clients import EventClient, MockTransport
from pricing_agent.skills.promotion_planner import plan_event

AS_OF = datetime(2026, 7, 21, 14, 0, tzinfo=timezone.utc)

st.set_page_config(page_title="Promotion Planner", page_icon="🏷️", layout="wide")


def md(text: str) -> str:
    return text.replace("$", r"\$")


@st.cache_data(show_spinner=False)
def events(as_of: datetime) -> list[dict]:
    return EventClient(MockTransport(as_of=as_of)).get_sales_event_calendar().data


@st.cache_data(show_spinner=False)
def plan(as_of: datetime, event_id: str, target: float) -> dict:
    return plan_event(MockTransport(as_of=as_of), event_id, target)


FEASIBILITY_STYLE = {
    "ACHIEVABLE": ("success", "✅"),
    "ACHIEVABLE_WITH_MARGIN_COST": ("warning", "⚠️"),
    "AT_RISK": ("warning", "⚠️"),
    "NOT_ACHIEVABLE": ("error", "🚫"),
}

catalog = events(AS_OF)
labels = {f"{e['event_name']} ({e['start_date']} → {e['end_date']})": e["event_id"] for e in catalog}

st.title("Event promotion planner")

choice = st.sidebar.selectbox("Event", list(labels))
event_id = labels[choice]
# Whole percent: Streamlit's "%%" format does not scale, so a 0.70 float slider would
# render as "1%".
target_pct = st.sidebar.slider("Target utilization", 40, 100, 70, 5, format="%d%%")
target = target_pct / 100.0

with st.spinner("Planning…"):
    result = plan(AS_OF, event_id, float(target))

objective = result["promotion_objective"]
target_block = result["inventory_target_calculation"]
feasibility = result["feasibility"]
plans = {p["plan_type"]: p for p in result["plans"]}
recommended = result["recommended_plan"]

st.caption(
    f"{objective['event']['event_name']} · {objective['event']['start_date']} to "
    f"{objective['event']['end_date']} · dates resolved from "
    f"`{objective['event']['date_source']}`"
)

# --- feasibility first ----------------------------------------------------------------

kind, icon = FEASIBILITY_STYLE.get(feasibility["status"], ("info", "•"))
getattr(st, kind)(
    md(
        f"**{feasibility['status'].replace('_', ' ').title()}** — "
        f"the target needs **{feasibility['required_incremental_units']} incremental sale(s)** "
        f"inside a {feasibility['event_duration_days']}-day window. The most aggressive safe "
        f"plan delivers **{plans['CAPACITY_FIRST']['outcomes']['incremental_units_sold']['mean']:.1f} "
        f"on average**, and hits the target in "
        f"**{feasibility['probability_target_achieved']:.0%}** of simulated outcomes."
    ),
    icon=icon,
)

c1, c2, c3, c4 = st.columns(4)
c1.metric("Target ending inventory", target_block["target_ending_inventory"],
          f"{target:.0%} of {target_block['total_physical_slots']} slots", delta_color="off")
c2.metric("Projected without promotion",
          f"{target_block['projected_inventory_without_promotion']['p50']:.0f}",
          "P50", delta_color="off")
c3.metric("Incremental sales required", target_block["incremental_promotional_sales_required"])
c4.metric("Eligible candidates", feasibility["max_safe_candidate_pool"],
          f"{len(result['excluded_vehicles'])} excluded", delta_color="off")

with st.expander("How the target was calculated"):
    st.markdown(md(
        f"""
```
target ending inventory   = {target_block['total_physical_slots']} slots x {target:.0%}
                          = {target_block['target_ending_inventory']}

projected without promo   = {target_block['current_inventory']} on lot
                          + {target_block['confirmed_inbound']} confirmed inbound
                          - {target_block['baseline_expected_sales']['p50']:.0f} baseline sales (P50)
                          - {target_block['other_expected_exits']} other exits
                          = {target_block['projected_inventory_without_promotion']['p50']:.0f}

incremental required      = {target_block['incremental_promotional_sales_required']}
```
Only `confirmed_inbound` enters the flow. `reserved_slots` is a superset of it
({target_block['reserved_not_inbound']} reserved beyond inbound), so counting both would
inflate the requirement by the entire inbound volume.

`other_expected_exits` has no data source and is assumed zero, which makes the
requirement a conservative overestimate.
"""
    ))

st.divider()

# --- plans ----------------------------------------------------------------------------

st.subheader("Three plans")
st.caption(
    "All three share the baseline's seed, so the difference between a plan and doing "
    "nothing is the price change rather than sampling noise. Unit sales are integers, so "
    "the mean matters as much as the median for effects smaller than one car."
)

columns = st.columns(3)
for column, plan_type in zip(columns, ("MARGIN_PROTECT", "BALANCED", "CAPACITY_FIRST")):
    item = plans[plan_type]
    outcomes = item["outcomes"]
    is_recommended = plan_type == recommended["plan_type"]

    with column.container(border=True):
        st.markdown(
            f"**{plan_type.replace('_', ' ').title()}**"
            + ("  ⭐ recommended" if is_recommended else "")
        )
        st.metric("Vehicles promoted", item["totals"]["vehicle_count"])
        st.metric("Dealer-funded discount", f"${item['totals']['total_dealer_funded']:,.0f}")
        st.metric(
            "Incremental units",
            f"{outcomes['incremental_units_sold']['mean']:.2f} avg",
            f"P90 {outcomes['incremental_units_sold']['p90']:.0f}",
            delta_color="off",
        )
        st.metric(
            "Gross impact (P50)",
            f"${outcomes['gross_impact']['p50']:,.0f}",
            delta_color="off",
        )
        st.metric("P(target achieved)", f"{outcomes['probability_target_achieved']:.0%}")
        st.caption(
            f"Ending utilization P50 {outcomes['ending_utilization']['p50']:.0%} · "
            f"{'within budget' if item['totals']['within_budget'] else 'over budget'}"
        )

if plans["MARGIN_PROTECT"]["totals"]["vehicle_count"] == 0:
    st.info(
        "Margin Protect promotes nothing here. It respects the net-value optimum, and on "
        "this lot discounting destroys more gross than it saves in carrying cost — so the "
        "honest margin-protecting answer is *do not discount*. The other two plans show "
        "what the capacity target costs.",
        icon="💡",
    )

figure = go.Figure()
for plan_type in ("MARGIN_PROTECT", "BALANCED", "CAPACITY_FIRST"):
    outcomes = plans[plan_type]["outcomes"]
    figure.add_trace(
        go.Bar(
            name=plan_type.replace("_", " ").title(),
            x=["Incremental units (mean)", "Gross impact ($100s)", "P(target) %"],
            y=[
                outcomes["incremental_units_sold"]["mean"],
                outcomes["gross_impact"]["p50"] / 100.0,
                outcomes["probability_target_achieved"] * 100.0,
            ],
        )
    )
figure.update_layout(barmode="group", height=320, margin=dict(t=20, b=10))
st.plotly_chart(figure)

# --- alternatives ---------------------------------------------------------------------

if feasibility["alternatives"]:
    st.subheader("If the target is not reachable")
    st.caption("Quantified, because 'not achievable' on its own leaves you where you started.")
    st.dataframe(
        pd.DataFrame(
            [
                {
                    "Option": a["option"].replace("_", " ").title(),
                    "Change required": a["quantified_change"],
                    "Unit": a["unit"].title(),
                    "Resulting P(target)": a["resulting_probability_target_achieved"] * 100.0,
                }
                for a in feasibility["alternatives"]
            ]
        ),
        hide_index=True,
        column_config={
            "Resulting P(target)": st.column_config.NumberColumn(format="%.0f%%"),
        },
    )

# --- promote / protect / exclude ------------------------------------------------------

st.subheader("Per-vehicle actions")
promote_tab, protect_tab, exclude_tab = st.tabs(["Promote", "Protect price", "Excluded"])
actions = result["per_vehicle_actions"]
chosen_plan = plans[recommended["plan_type"]]
prices = {v["vehicle_id"]: v for v in chosen_plan["vehicles_selected"]}

with promote_tab:
    rows = [
        {
            "Stock": a["vehicle_id"],
            "Current": prices[a["vehicle_id"]]["current_list_price"],
            "Promotion price": a["promotion_price"],
            "Discount": prices[a["vehicle_id"]]["discount"],
            "Min safe list": prices[a["vehicle_id"]]["minimum_safe_list_price"],
        }
        for a in actions
        if a["action"] == "PROMOTE"
    ]
    if rows:
        st.dataframe(
            pd.DataFrame(rows), hide_index=True,
            column_config={
                c: st.column_config.NumberColumn(format="$%d")
                for c in ("Current", "Promotion price", "Discount", "Min safe list")
            },
        )
        st.caption("No promotion price falls below its minimum safe list price.")
    else:
        st.write("This plan promotes no vehicles.")

with protect_tab:
    rows = [{"Stock": a["vehicle_id"], "Why": a["reason"]} for a in actions if a["action"] == "PROTECT_PRICE"]
    st.dataframe(pd.DataFrame(rows) if rows else pd.DataFrame([{"Stock": "—", "Why": "none"}]),
                 hide_index=True)

with exclude_tab:
    rows = [{"Stock": a["vehicle_id"], "Reason": a["reason"]} for a in actions if a["action"] == "EXCLUDE"]
    st.dataframe(pd.DataFrame(rows), hide_index=True)
    st.caption(
        "Every exclusion carries a reason — a plan is not reviewable if you cannot see "
        "what was left out. `NO_SAFE_HEADROOM` means the vehicle is already at or below "
        "its floor, which is common for aged and underwater units: the cars you most want "
        "to move are often the ones you cannot legally discount."
    )

# --- warnings -------------------------------------------------------------------------

if result["warnings"]:
    st.subheader("Warnings")
    for warning in result["warnings"]:
        st.markdown(md(f"`{warning['severity']}` **{warning['code']}** — {warning['message']}"))

with st.expander("Audit"):
    st.write(
        f"Simulation seed `{result['audit']['simulation']['seed']}`, "
        f"{result['audit']['simulation']['draw_count']:,} draws, "
        f"label `{result['audit']['simulation']['model_label']}`"
    )
    st.caption(
        f"Event lift: {feasibility['lift_source']}"
        + (
            f" ({feasibility['historical_event_lift']}x from prior events)"
            if feasibility["historical_event_lift"]
            else " — no validated history, configured default used"
        )
    )
