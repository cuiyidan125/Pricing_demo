"""Vehicle detail — demo beats 2 and 3.

The screen where the recommendation has to be trusted, so the price, the reason, the
floor, and the refusal all appear together rather than the price alone.
"""

from __future__ import annotations

from datetime import datetime, timezone

import pandas as pd
import plotly.graph_objects as go
import streamlit as st
import streamlit.components.v1 as components

from pricing_agent.agents import extract, intent_of
from pricing_agent.config import load_config
from pricing_agent.llm import credentials_present, explain
from pricing_agent.mcp_clients import MockTransport, VautoClient
from pricing_agent.policy.price_floor import can_publish
from pricing_agent.skills.single_vehicle import analyze

import ui_components

AS_OF = datetime(2026, 7, 21, 14, 0, tzinfo=timezone.utc)

st.set_page_config(page_title="Vehicle Detail", page_icon="🚗", layout="wide")

SEVERITY_STYLE = {
    "BLOCKING": ("🚫", "error"),
    "CRITICAL": ("🔴", "error"),
    "HIGH": ("🟠", "warning"),
    "MEDIUM": ("🟡", "warning"),
    "LOW": ("⚪", "info"),
    "INFO": ("ℹ️", "info"),
}


def md(text: str) -> str:
    """Escape dollar signs for Streamlit markdown.

    Streamlit reads `$...$` as LaTeX math, so any string quoting two dollar amounts —
    which is most warning messages, since every one reports an observed value against a
    threshold — silently loses both signs and italicises the text between them. Every
    money-bearing string rendered as markdown must go through this.
    """
    return text.replace("$", r"\$")


@st.cache_data(show_spinner=False)
def load_inventory(as_of: datetime) -> list[dict]:
    return VautoClient(MockTransport(as_of=as_of)).get_dealer_inventory().data


@st.cache_data(show_spinner=False)
def analyze_vehicle(vehicle_id: str, as_of: datetime) -> dict:
    return analyze(vehicle_id, MockTransport(as_of=as_of))


inventory = load_inventory(AS_OF)
labels = {
    f"{v['vehicle_id']} · {v['year']} {v['make']} {v['model']} · {v['days_in_inventory']}d": v[
        "vehicle_id"
    ]
    for v in inventory
}

choice = st.sidebar.selectbox("Vehicle", list(labels), index=0)
vehicle_id = labels[choice]

with st.spinner("Analyzing…"):
    result = analyze_vehicle(vehicle_id, AS_OF)

vehicle = result["vehicle"]
valuation = result["valuation"]
break_even = result["break_even_analysis"]
sales = result["sales_outcome_distribution"]
headroom = result["promotional_headroom"]
recommended_strategy = result["recommended_strategy"]["strategy"]
scenario = next(s for s in result["pricing_scenarios"] if s["strategy"] == recommended_strategy)

image_column, title_column = st.columns([1, 3], vertical_alignment="center")

with image_column:
    if vehicle.get("image_url"):
        # st.image defaults width to 'content' (original size), so unlike the dataframe
        # and chart calls this one genuinely needs the value stated.
        st.image(vehicle["image_url"], width="stretch")
    else:
        # No image source in the prototype. A generated silhouette reads as a deliberate
        # placeholder; a broken image icon reads as a bug.
        #
        # components.html, not st.html: Streamlit's sanitizer strips <svg> and leaves the
        # wrapper behind, which renders as an empty bar rather than failing visibly.
        components.html(
            ui_components.vehicle_silhouette_svg(
                vehicle.get("segment"), vehicle.get("model")
            ),
            height=120,
        )
        st.caption(
            f"No photo on file · {ui_components.body_style(vehicle.get('segment'), vehicle.get('model')).title()}"
        )

with title_column:
    st.title(
        f"{vehicle['year']} {vehicle['make']} {vehicle['model']} {vehicle['trim'] or ''}".strip()
    )
    st.caption(
        f"{vehicle['vehicle_id']} · {vehicle['mileage']:,} miles · "
        f"{vehicle['days_in_inventory']} days in inventory · {vehicle['condition'].title()}"
    )

# --- natural-language intake (§4.2) ---------------------------------------------------

with st.expander("Ask in plain English", expanded=False):
    st.caption(
        "The model reads the request into validated JSON and hands it to the engine. It "
        "never produces a number — the extraction schema has no property for one."
    )
    question = st.text_area(
        "Request",
        value=(
            "Analyze this 2022 Toyota RAV4 XLE with 42,000 miles. We paid $23,500 and "
            "spent $1,200 on reconditioning. It has been in inventory for 37 days. Tell "
            "me what it is worth, how much discount room we have, and the expected P50 "
            "and P90 sales time."
        ),
        height=110,
        label_visibility="collapsed",
    )
    if st.button("Extract"):
        request, llm_result, errors = extract(question, as_of=AS_OF)
        badge = "🟢 live model" if llm_result.live else "🟡 recorded fallback"
        st.caption(f"{badge} · routed to `{intent_of(llm_result)}`"
                   + (f" · {llm_result.note}" if llm_result.note else ""))

        if errors:
            st.error(
                "Extraction did not validate, so it was not passed to any tool (§4.2):\n\n"
                + "\n".join(f"- {e}" for e in errors)
            )
        else:
            st.success("Schema-valid — safe to pass to the pricing engine.", icon="✅")

        left, right = st.columns(2)
        left.markdown("**Extracted request**")
        left.json({k: v for k, v in request.items() if k not in ("extraction_provenance",)})
        right.markdown("**Field provenance**")
        right.dataframe(
            pd.DataFrame(request["extraction_provenance"]),
            hide_index=True,
        )
        st.caption(
            "Note what is absent: no price, no valuation, no days-to-sale. Those fields "
            "do not exist in the extraction schema, which is the structural half of §4.1."
        )

# --- the refusal, before anything else ------------------------------------------------

publishable, reasons = can_publish(result["warnings"], [])
if not publishable:
    st.error(
        md(
            "**This price cannot be published.**\n\n"
            + "\n".join(f"- {reason}" for reason in reasons)
        ),
        icon="🚫",
    )

# --- headline -------------------------------------------------------------------------

c1, c2, c3, c4 = st.columns(4)
current = vehicle["current_list_price"]
recommended = scenario["proposed_list_price"]

c1.metric(
    "Recommended price",
    f"${recommended:,.0f}",
    f"${recommended - current:+,.0f} vs current" if current else None,
)
c2.metric("Market value", f"${valuation['market_value']:,.0f}", valuation["anchor"].title())
c3.metric(
    "P50 gross",
    f"${scenario['expected_front_end_gross']['p50']:,.0f}",
    f"P10 ${scenario['expected_front_end_gross']['p10']:,.0f}",
    delta_color="off",
)
c4.metric(
    "Days to sell",
    f"{scenario['additional_days_to_sale']['p50']:.0f}",
    f"P90 {scenario['additional_days_to_sale']['p90']:.0f} days",
    delta_color="off",
)

st.caption(
    f"Strategy **{recommended_strategy.replace('_', ' ').title()}** · "
    + " · ".join(f"`{c}`" for c in result["recommended_strategy"]["rationale_codes"])
)

# --- narration, constrained to the allow-list -----------------------------------------

narrative = explain(result["explanation_inputs"], result["warnings"])
with st.container(border=True):
    st.markdown(md(narrative.text))
    caption = f"Explanation source: **{narrative.source_label}**"
    if not credentials_present():
        caption += " — no API key set, so the deterministic template is used."
    st.caption(caption)

    if narrative.rejected:
        # The model cited something the engine never published, so its prose was
        # discarded. Showing that this happened is more valuable than hiding it.
        st.warning(
            md(
                "The generated explanation was **rejected** and replaced with the "
                "template. It cited figures the engine never produced: "
                + ", ".join(narrative.rejected)
            ),
            icon="🛡️",
        )

# --- aging timeline -------------------------------------------------------------------

st.subheader("Where this car is in its life on the lot")
st.plotly_chart(
    ui_components.aging_timeline(
        days_in_inventory=vehicle["days_in_inventory"],
        additional_p50=scenario["additional_days_to_sale"]["p50"],
        additional_p90=scenario["additional_days_to_sale"]["p90"],
    )
)
projected = sales["projected_total_inventory_age"]
st.caption(
    md(
        f"Median total age at sale **{projected['p50']:.0f} days**, "
        f"**{projected['p90']:.0f} days** in the adverse case. "
        f"P(over 90 days) is {sales['projected_age_exceedance']['over_90_days']:.0%}. "
        "The whisker is the point — a car whose median clears 90 days comfortably can "
        "still carry a tail well past it, and the tail is the real exposure."
    )
)

# --- warnings -------------------------------------------------------------------------

if result["warnings"]:
    st.subheader("Warnings")
    for warning in result["warnings"]:
        icon, kind = SEVERITY_STYLE.get(warning["severity"], ("•", "info"))
        margin = ""
        if warning["observed"] is not None and warning["threshold"] is not None:
            margin = (
                f"  \nObserved **{warning['observed']:,.2f}** against a threshold of "
                f"**{warning['threshold']:,.2f}** ({warning['unit'].lower()})."
            )
        body = f"{icon} **{warning['severity']} · {warning['code']}**  \n{warning['message']}{margin}"
        if warning["remediation"]:
            body += f"  \n_{warning['remediation']}_"
        getattr(st, kind)(md(body))

if result["approvals_required"]:
    st.warning(
        "**Manager approval required:** "
        + ", ".join(a["approval_type"].replace("_", " ").title() for a in result["approvals_required"]),
        icon="✋",
    )

st.divider()

# --- strategies -----------------------------------------------------------------------

left, right = st.columns([3, 2])

with left:
    st.subheader("Gross against turn")
    st.caption(
        "Three strategies from one simulation sharing a seed, so the differences are the "
        "price change and not sampling noise."
    )

    figure = go.Figure()
    for item in result["pricing_scenarios"]:
        is_recommended = item["strategy"] == recommended_strategy
        figure.add_trace(
            go.Scatter(
                x=[item["additional_days_to_sale"]["p50"]],
                y=[item["expected_front_end_gross"]["p50"]],
                mode="markers+text",
                text=[item["strategy"].replace("_", " ").title()],
                textposition="top center",
                marker=dict(size=22 if is_recommended else 14,
                            symbol="star" if is_recommended else "circle"),
                error_x=dict(
                    type="data",
                    symmetric=False,
                    array=[item["additional_days_to_sale"]["p90"] - item["additional_days_to_sale"]["p50"]],
                    arrayminus=[item["additional_days_to_sale"]["p50"] - item["additional_days_to_sale"]["p10"]],
                    thickness=1,
                ),
                name=f"${item['proposed_list_price']:,.0f}",
            )
        )
    figure.add_hline(y=0, line_dash="dot", line_color="grey")
    figure.update_layout(
        xaxis_title="P50 days to sale (bars show P10–P90)",
        yaxis_title="P50 front-end gross ($)",
        height=380,
        margin=dict(t=20, b=10),
    )
    st.plotly_chart(figure)

    table = pd.DataFrame(
        [
            {
                "Strategy": s["strategy"].replace("_", " ").title(),
                "List price": s["proposed_list_price"],
                "Price to market": s["price_to_market_ratio"],
                "Deal rating": s["deal_rating"],
                "P50 days": s["additional_days_to_sale"]["p50"],
                # Whole percent: NumberColumn's "%%" format does not scale the value.
                "Sold in 30d": s["sale_probabilities"]["within_30_days"] * 100.0,
                "P50 gross": s["expected_front_end_gross"]["p50"],
                "P50 net value": s["expected_net_economic_value"]["p50"],
                "P10 net value": s["expected_net_economic_value"]["p10"],
            }
            for s in result["pricing_scenarios"]
        ]
    )
    st.dataframe(
        table,
        hide_index=True,
        column_config={
            "List price": st.column_config.NumberColumn(format="$%d"),
            "Price to market": st.column_config.NumberColumn(format="%.3f"),
            "P50 days": st.column_config.NumberColumn(format="%d"),
            "Sold in 30d": st.column_config.NumberColumn(format="%.0f%%"),
            "P50 gross": st.column_config.NumberColumn(format="$%d"),
            "P50 net value": st.column_config.NumberColumn(format="$%d"),
            "P10 net value": st.column_config.NumberColumn(format="$%d"),
        },
    )

with right:
    st.subheader("Where the floor is")
    floors = break_even["floors"]
    st.metric("Break-even", f"${break_even['current_accounting_break_even']:,.0f}")
    st.metric("Minimum safe list price", f"${break_even['minimum_safe_list_price']:,.0f}")
    st.caption(
        f"Binding constraint: **{floors['binding_constraint'].replace('_', ' ').title()}** · "
        f"assumes {break_even['expected_discount_rate_used']:.1%} negotiation off list."
    )

    crossover = break_even["market_value_crossover_risk"]
    if crossover["break_even_exceeds_market_value_now"]:
        st.error(
            md(
                f"Break-even of **${break_even['current_accounting_break_even']:,.0f}** exceeds "
                f"market value of **${valuation['market_value']:,.0f}**. "
                "This vehicle cannot be sold at a profit today."
            ),
            icon="🔴",
        )
    elif crossover["estimated_crossover_days"]:
        st.warning(
            f"Break-even overtakes market value in about "
            f"**{crossover['estimated_crossover_days']} days**.",
            icon="⏳",
        )

    st.metric("Maximum safe discount", f"${headroom['max_safe_discount']:,.0f}")
    st.caption(
        md(
            f"Negotiation ${headroom['reserves']['negotiation_reserve']:,.0f} · "
            f"Event ${headroom['reserves']['event_promotion_reserve']:,.0f} · "
            f"Emergency ${headroom['reserves']['emergency_markdown_reserve']:,.0f}"
        )
    )

# --- discount ladder ------------------------------------------------------------------

if headroom["ladder"]:
    st.subheader("Where discounting stops paying")
    st.caption(
        "Each rung is a separate simulation. The optimum is found by running them, not by "
        "formula — it depends on this vehicle's holding cost, depreciation, and price position."
    )
    ladder = pd.DataFrame(headroom["ladder"])
    ladder_figure = go.Figure()
    ladder_figure.add_trace(
        go.Scatter(
            x=ladder["discount"],
            y=ladder["p50_net_economic_value"],
            mode="lines+markers",
            name="P50 net economic value",
        )
    )
    ladder_figure.add_vline(
        x=headroom["economically_sensible_discount"],
        line_dash="dash",
        annotation_text=f"Optimum ${headroom['economically_sensible_discount']:,.0f}",
    )
    ladder_figure.update_layout(
        xaxis_title="Discount off list ($)",
        yaxis_title="P50 net economic value ($)",
        height=320,
        margin=dict(t=20, b=10),
    )
    st.plotly_chart(ladder_figure)

# --- comparables ----------------------------------------------------------------------

st.subheader("Comparable listings")
included = [c for c in result["comparables"] if c["included"]]
excluded = [c for c in result["comparables"] if not c["included"]]

if included:
    comps_figure = go.Figure()
    comps_figure.add_trace(
        go.Scatter(
            x=[c["mileage"] for c in included],
            y=[c["list_price"] for c in included],
            mode="markers",
            name="Comparable listings",
            text=[c["listing_id"] for c in included],
            marker=dict(size=10, opacity=0.65),
        )
    )
    comps_figure.add_trace(
        go.Scatter(
            x=[vehicle["mileage"]],
            y=[recommended],
            mode="markers+text",
            name="This vehicle at recommended price",
            text=["This vehicle"],
            textposition="top center",
            marker=dict(size=20, symbol="star"),
        )
    )
    comps_figure.update_layout(
        xaxis_title="Mileage", yaxis_title="List price ($)", height=360,
        margin=dict(t=20, b=10),
    )
    st.plotly_chart(comps_figure)

st.caption(
    md(
        f"{len(included)} comparables used, {len(excluded)} excluded. "
        f"Internal estimate: "
        + (
            f"${valuation['internal_estimate']:,.0f}"
            if valuation["internal_estimate"]
            else "not computed — too few comparables to form a second opinion"
        )
        + (
            f" · differs from the external anchor by {valuation['divergence']:.1%}"
            if valuation["divergence"] is not None
            else ""
        )
    )
)

with st.expander(f"Excluded comparables ({len(excluded)})"):
    if excluded:
        st.dataframe(
            pd.DataFrame(
                [
                    {
                        "Listing": c["listing_id"],
                        "Vehicle": f"{c['year']} {c['make']} {c['model']} {c['trim'] or ''}",
                        "Mileage": c["mileage"],
                        "Price": c["list_price"],
                        "Distance": c["distance_miles"],
                        "Reason": c["exclusion_reason"],
                    }
                    for c in excluded
                ]
            ),
            hide_index=True,
        )
    else:
        st.write("None.")

# --- receipts -------------------------------------------------------------------------

with st.expander("Assumptions and audit trail"):
    audit = result["audit"]
    st.write(
        f"**Simulation** — {audit['simulation']['draw_count']:,} draws, seed "
        f"`{audit['simulation']['seed']}`, label `{audit['simulation']['model_label']}`"
    )
    st.write(
        f"**Versions** — config `{audit['config_version']}`, assumptions "
        f"`{audit['assumption_version']}`, percentile convention "
        f"`{audit['percentile_convention']}`"
    )
    st.write(
        f"**Valuation source** — anchor `{audit['valuation_source']['anchor']}`, "
        f"internal check computed: {audit['valuation_source']['internal_check_computed']}"
    )
    st.write("**MCP tools called**")
    st.dataframe(
        pd.DataFrame(audit["mcp_tools_called"]), hide_index=True
    )
    st.write("**Values the explanation layer may cite**")
    allow_list = pd.DataFrame(result["explanation_inputs"]["values"])
    # The allow-list is genuinely mixed by design — labels like MAXIMIZE_GROSS sit
    # alongside figures like 29195 in one column — so Arrow cannot infer a type and
    # throws on every render. Streamlit recovers, but noisily. Rendering the column as
    # text is the honest fix: this table is for reading, not arithmetic.
    def _cell(value) -> str:
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            return str(value)
        # Dollars and day counts are integral; ratios are not, and need their decimals.
        return f"{value:,.0f}" if float(value).is_integer() else f"{value:,.4g}"

    if "value" in allow_list.columns:
        allow_list["value"] = allow_list["value"].map(_cell)
    st.dataframe(allow_list, hide_index=True)
    st.caption(
        "The narration layer receives only this table. A currency figure in generated "
        "prose that does not appear here fails the response rather than reaching you."
    )
