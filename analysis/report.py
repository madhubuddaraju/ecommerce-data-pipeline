"""
Build the analytics report from the warehouse marts.

Outputs:
    reports/figures/*.png   charts used in the README
    reports/insights.md     key metrics and findings, regenerated on every run

Usage:
    python analysis/report.py
"""

from __future__ import annotations

import sys
from pathlib import Path

import duckdb
import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import matplotlib.ticker as mtick  # noqa: E402
import pandas as pd  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
WAREHOUSE = ROOT / "data" / "warehouse.duckdb"
FIG_DIR = ROOT / "reports" / "figures"

# palette
BLUE, ORANGE, AQUA = "#2a78d6", "#eb6834", "#1baf7a"
INK, INK_2, GRID = "#0b0b0b", "#52514e", "#e6e5e1"

plt.rcParams.update({
    "figure.dpi": 130, "savefig.bbox": "tight", "font.size": 10,
    "axes.edgecolor": GRID, "axes.labelcolor": INK_2, "axes.titleweight": "bold",
    "axes.titlesize": 12, "axes.titlecolor": INK, "axes.spines.top": False,
    "axes.spines.right": False, "axes.grid": True, "axes.axisbelow": True, "grid.color": GRID, "grid.linewidth": 0.8,
    "xtick.color": INK_2, "ytick.color": INK_2, "legend.frameon": False,
})


def q(con, sql: str) -> pd.DataFrame:
    return con.execute(sql).df()


def money(x: float) -> str:
    return f"${x / 1e6:.2f}M" if x >= 1e6 else f"${x / 1e3:.1f}K"


def fig_monthly_revenue(df: pd.DataFrame) -> None:
    fig, ax = plt.subplots(figsize=(9, 4))
    x = pd.to_datetime(df["month"])
    ax.bar(x, df["new_customer_revenue"], width=22, color=ORANGE, label="New customers")
    ax.bar(x, df["returning_customer_revenue"], width=22, bottom=df["new_customer_revenue"],
           color=BLUE, label="Returning customers", edgecolor="white", linewidth=1)
    ax.yaxis.set_major_formatter(mtick.FuncFormatter(lambda v, _: money(v) if v else "0"))
    ax.set_title("Monthly revenue: new vs returning customers")
    ax.legend(loc="upper left")
    ax.grid(axis="x", visible=False)
    fig.savefig(FIG_DIR / "monthly_revenue.png")
    plt.close(fig)


def fig_cohort_heatmap(df: pd.DataFrame) -> None:
    pivot = df[df["months_since_first"] <= 12].pivot(
        index="cohort_month", columns="months_since_first", values="retention_rate")
    pivot.index = pd.to_datetime(pivot.index).strftime("%Y-%m")
    fig, ax = plt.subplots(figsize=(10, 7))
    im = ax.imshow(pivot.values, cmap="Blues", vmin=0, vmax=0.7, aspect="auto")
    ax.set_xticks(range(pivot.shape[1]), pivot.columns)
    ax.set_yticks(range(pivot.shape[0]), pivot.index)
    ax.set_xlabel("Months since first purchase")
    ax.set_title("Cohort retention (share of customers active)")
    ax.grid(False)
    for (i, j), v in pd.DataFrame(pivot.values).stack().items():
        if j > 0 and pd.notna(v):
            ax.text(j, i, f"{v:.0%}", ha="center", va="center", fontsize=7,
                    color="white" if v > 0.45 else INK)
    fig.colorbar(im, ax=ax, format=mtick.PercentFormatter(1.0), shrink=0.7)
    fig.savefig(FIG_DIR / "cohort_retention.png")
    plt.close(fig)


def fig_rfm_segments(df: pd.DataFrame) -> None:
    df = df.sort_values("revenue")
    fig, ax = plt.subplots(figsize=(8, 4))
    ax.barh(df["segment"], df["revenue"], color=BLUE, height=0.6)
    for y, (rev, share, n) in enumerate(zip(df["revenue"], df["revenue_share"], df["customers"], strict=False)):
        ax.text(rev, y, f"  {share:.0%} of revenue · {n:,} customers", va="center", color=INK_2, fontsize=9)
    ax.xaxis.set_major_formatter(mtick.FuncFormatter(lambda v, _: money(v) if v else "0"))
    ax.set_xlim(0, df["revenue"].max() * 1.6)
    ax.set_title("Revenue by RFM customer segment")
    ax.grid(axis="y", visible=False)
    fig.savefig(FIG_DIR / "rfm_segments.png")
    plt.close(fig)


def fig_channels(df: pd.DataFrame) -> None:
    df = df.sort_values("revenue_per_customer")
    fig, ax = plt.subplots(figsize=(8, 3.6))
    ax.barh(df["acquisition_channel"], df["revenue_per_customer"], color=AQUA, height=0.6)
    for y, (v, conv) in enumerate(zip(df["revenue_per_customer"], df["conversion_rate"], strict=False)):
        ax.text(v, y, f"  ${v:,.0f} · {conv:.0%} convert", va="center", color=INK_2, fontsize=9)
    ax.set_xlim(0, df["revenue_per_customer"].max() * 1.45)
    ax.xaxis.set_major_formatter(mtick.StrMethodFormatter("${x:,.0f}"))
    ax.set_title("Revenue per acquired customer by channel")
    ax.grid(axis="y", visible=False)
    fig.savefig(FIG_DIR / "channel_value.png")
    plt.close(fig)


def build(warehouse: Path = WAREHOUSE) -> str:
    if not warehouse.exists():
        sys.exit("warehouse not found - run `make pipeline` first")
    FIG_DIR.mkdir(parents=True, exist_ok=True)
    con = duckdb.connect(str(warehouse), read_only=True)

    monthly = q(con, "SELECT * FROM marts.monthly_revenue ORDER BY month")
    cohorts = q(con, "SELECT * FROM marts.cohort_retention")
    channels = q(con, "SELECT * FROM marts.channel_performance")
    segments = q(con, """
        SELECT segment, count(*) AS customers, sum(monetary) AS revenue,
               sum(monetary) / sum(sum(monetary)) OVER () AS revenue_share,
               avg(recency_days) AS avg_recency
        FROM marts.customer_rfm GROUP BY segment""")
    categories = q(con, """
        SELECT category, sum(revenue) AS revenue, sum(gross_profit) / sum(revenue) AS margin,
               avg(return_rate) AS return_rate
        FROM marts.product_performance GROUP BY category ORDER BY revenue DESC""")
    totals = q(con, """
        SELECT sum(net_amount) AS revenue, count(*) AS orders, count(DISTINCT customer_id) AS buyers,
               avg(net_amount) AS aov, sum(gross_profit) / sum(net_amount) AS margin
        FROM core.fct_orders WHERE status = 'completed'""").iloc[0]
    dq = q(con, "SELECT count(*) AS n, sum(passed::INT) AS passed FROM audit.dq_results").iloc[0]
    rejects = q(con, "SELECT reason, count(*) AS n FROM audit.rejects GROUP BY 1 ORDER BY 2 DESC")
    con.close()

    fig_monthly_revenue(monthly)
    fig_cohort_heatmap(cohorts)
    fig_rfm_segments(segments)
    fig_channels(channels)

    y = monthly.assign(year=pd.to_datetime(monthly["month"]).dt.year).groupby("year")["revenue"].sum()
    yoy = y.iloc[-1] / y.iloc[0] - 1
    is_holiday = pd.to_datetime(monthly["month"]).dt.month.isin([11, 12])
    q4_share = monthly.loc[is_holiday, "revenue"].sum() / monthly["revenue"].sum()
    ret = cohorts.groupby("months_since_first")["retention_rate"].mean()
    ret_m1, ret_m6 = ret.get(1, float("nan")), ret.get(6, float("nan"))
    seg = segments.set_index("segment")
    champ = seg.loc["Champions"]
    champ_share = champ.customers / seg.customers.sum()
    at_risk = seg.loc["At Risk"]
    best_ch = channels.sort_values("revenue_per_customer").iloc[-1]
    worst_ch = channels.sort_values("revenue_per_customer").iloc[0]
    top_cat = categories.iloc[0]

    md = f"""# Insights report

_Generated by `analysis/report.py` from the DuckDB warehouse. Numbers refresh on every pipeline run._

## Headline metrics

| Metric | Value |
|---|---|
| Revenue (completed orders) | {money(totals.revenue)} |
| Orders | {int(totals.orders):,} |
| Buying customers | {int(totals.buyers):,} |
| Average order value | ${totals.aov:,.2f} |
| Gross margin | {totals.margin:.1%} |
| Revenue growth {y.index[-1]} vs {y.index[0]} | {yoy:+.0%} |
| Data quality checks passed | {int(dq.passed)}/{int(dq.n)} |

## Key findings

1. **Growth is strong and seasonal.** Revenue grew {yoy:.0%} year over year, and November-December
   alone account for {q4_share:.0%} of all revenue. Inventory and marketing budgets should be front-loaded into Q4.
2. **Retention decays steadily after the first purchase.** On average {ret_m1:.0%} of a cohort
   buys again in month 1, falling to {ret_m6:.0%} by month 6. A post-purchase onboarding flow
   (days 7-30) is the biggest retention lever.
3. **Champions carry the business.** {int(champ.customers):,} Champions ({champ_share:.0%} of buyers)
   generate {champ.revenue_share:.0%} of revenue. A loyalty tier would protect this base.
4. **{int(at_risk.customers):,} high-value customers are At Risk**
   (avg {at_risk.avg_recency:.0f} days since last order), holding {money(at_risk.revenue)} of historical spend -
   the best target for a win-back campaign.
5. **Channel quality varies {best_ch.revenue_per_customer / worst_ch.revenue_per_customer:.1f}x.** A
   {best_ch.acquisition_channel} customer is worth ${best_ch.revenue_per_customer:,.0f} vs
   ${worst_ch.revenue_per_customer:,.0f} for {worst_ch.acquisition_channel}; budget should shift toward
   {best_ch.acquisition_channel} and away from low-converting {worst_ch.acquisition_channel} spend.
6. **{top_cat.category} leads revenue** ({money(top_cat.revenue)}, {top_cat.margin:.0%} margin).

## Revenue by category

| Category | Revenue | Gross margin | Avg return rate |
|---|---|---|---|
""" + "\n".join(f"| {r.category} | {money(r.revenue)} | {r.margin:.1%} | {r.return_rate:.1%} |"
                for r in categories.itertuples()) + """

## Data cleaning summary

| Rejected reason | Rows |
|---|---|
""" + ("\n".join(f"| {r.reason} | {r.n:,} |" for r in rejects.itertuples()) or "| none | 0 |") + """

## Charts

![Monthly revenue](figures/monthly_revenue.png)
![Cohort retention](figures/cohort_retention.png)
![RFM segments](figures/rfm_segments.png)
![Channel value](figures/channel_value.png)
"""
    out = ROOT / "reports" / "insights.md"
    out.write_text(md)
    print(f"wrote {out.relative_to(ROOT)} and {len(list(FIG_DIR.glob('*.png')))} figures")
    return md


if __name__ == "__main__":
    build()
