"""
Interactive dashboard on top of the warehouse marts.

    streamlit run dashboard/app.py
"""

from pathlib import Path

import duckdb
import pandas as pd
import plotly.express as px
import streamlit as st

WAREHOUSE = Path(__file__).resolve().parents[1] / "data" / "warehouse.duckdb"
BLUE, ORANGE, AQUA = "#2a78d6", "#eb6834", "#1baf7a"

st.set_page_config(page_title="E-commerce Analytics", layout="wide")


@st.cache_data
def load(sql: str) -> pd.DataFrame:
    with duckdb.connect(str(WAREHOUSE), read_only=True) as con:
        return con.execute(sql).df()


if not WAREHOUSE.exists():
    st.error("Warehouse not found. Run `make pipeline` first.")
    st.stop()

st.title("E-commerce Analytics")

monthly = load("SELECT * FROM marts.monthly_revenue ORDER BY month")
monthly["month"] = pd.to_datetime(monthly["month"])

# ---- filters -----------------------------------------------------------------
c1, c2 = st.columns([3, 1])
months = monthly["month"].dt.date.tolist()
start, end = c1.select_slider("Period", options=months, value=(months[0], months[-1]),
                              format_func=lambda d: d.strftime("%b %Y"))
countries = load("SELECT DISTINCT country FROM core.dim_customers ORDER BY 1")["country"].tolist()
country = c2.selectbox("Country", ["All"] + countries)

where = f"order_date BETWEEN DATE '{start}' AND last_day(DATE '{end}') AND status = 'completed'"
if country != "All":
    where += f" AND customer_id IN (SELECT customer_id FROM core.dim_customers WHERE country = '{country}')"

kpi = load(f"""SELECT sum(net_amount) rev, count(*) orders, count(DISTINCT customer_id) buyers,
                      avg(net_amount) aov, sum(gross_profit) / sum(net_amount) margin
               FROM core.fct_orders WHERE {where}""").iloc[0]

k = st.columns(5)
k[0].metric("Revenue", f"${(kpi.rev or 0):,.0f}")
k[1].metric("Orders", f"{int(kpi.orders):,}")
k[2].metric("Customers", f"{int(kpi.buyers):,}")
k[3].metric("Avg order value", f"${(kpi.aov or 0):,.2f}")
k[4].metric("Gross margin", f"{(kpi.margin or 0):.1%}")

# ---- revenue trend --------------------------------------------------------------
trend = load(f"""SELECT date_trunc('month', order_date) AS month,
                        sum(net_amount) FILTER (WHERE is_first_order)     AS "New customers",
                        sum(net_amount) FILTER (WHERE NOT is_first_order) AS "Returning customers"
                 FROM core.fct_orders WHERE {where} GROUP BY 1 ORDER BY 1""")
fig = px.bar(trend, x="month", y=["New customers", "Returning customers"],
             color_discrete_sequence=[ORANGE, BLUE], title="Monthly revenue")
fig.update_layout(legend_title_text="", yaxis_title="Revenue ($)", xaxis_title="")
st.plotly_chart(fig, use_container_width=True)

left, right = st.columns(2)

# ---- category ---------------------------------------------------------------
cat = load(f"""SELECT p.category, sum(i.net_amount) AS revenue
               FROM core.fct_order_items i JOIN core.dim_products p USING (product_id)
               WHERE {where.replace('customer_id', 'i.customer_id')}
               GROUP BY 1 ORDER BY 2""")
fig = px.bar(cat, x="revenue", y="category", orientation="h", title="Revenue by category",
             color_discrete_sequence=[BLUE])
fig.update_layout(xaxis_title="Revenue ($)", yaxis_title="")
left.plotly_chart(fig, use_container_width=True)

# ---- channels -----------------------------------------------------------------
ch = load("SELECT * FROM marts.channel_performance ORDER BY revenue_per_customer")
fig = px.bar(ch, x="revenue_per_customer", y="acquisition_channel", orientation="h",
             title="Revenue per acquired customer (all time)", color_discrete_sequence=[AQUA],
             hover_data={"conversion_rate": ":.1%", "repeat_purchase_rate": ":.1%"})
fig.update_layout(xaxis_title="Revenue per customer ($)", yaxis_title="")
right.plotly_chart(fig, use_container_width=True)

# ---- cohorts ---------------------------------------------------------------------
st.subheader("Cohort retention")
coh = load("SELECT * FROM marts.cohort_retention WHERE months_since_first BETWEEN 1 AND 12")
pivot = coh.pivot(index="cohort_month", columns="months_since_first", values="retention_rate")
pivot.index = pd.to_datetime(pivot.index).strftime("%Y-%m")
fig = px.imshow(pivot, color_continuous_scale="Blues", aspect="auto", text_auto=".0%",
                labels={"x": "Months since first purchase", "y": "Cohort", "color": "Retention"})
st.plotly_chart(fig, use_container_width=True)

# ---- RFM -----------------------------------------------------------------------------
st.subheader("Customer segments (RFM)")
rfm = load("""SELECT segment, count(*) AS customers, round(sum(monetary)) AS revenue,
                     round(avg(recency_days)) AS avg_recency_days, round(avg(frequency), 1) AS avg_orders
              FROM marts.customer_rfm GROUP BY 1 ORDER BY revenue DESC""")
st.dataframe(rfm, use_container_width=True, hide_index=True)

with st.expander("Top products"):
    st.dataframe(load("SELECT sku, product_name, category, units_sold, revenue, margin_pct, return_rate "
                      "FROM marts.product_performance LIMIT 25"),
                 use_container_width=True, hide_index=True)

with st.expander("Pipeline health"):
    st.dataframe(load("SELECT * FROM audit.pipeline_runs ORDER BY started_at DESC LIMIT 10"),
                 use_container_width=True, hide_index=True)
    st.dataframe(load("SELECT check_name, severity, failing_rows, passed FROM audit.dq_results"),
                 use_container_width=True, hide_index=True)
