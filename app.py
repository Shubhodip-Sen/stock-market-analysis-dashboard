"""Stock Market Analysis in SQL: Streamlit dashboard.

Run:  streamlit run app.py
Everything on screen comes from SQL in queries.py, run against data/stocks.db
(built automatically from the CSVs in data/ on first start).
"""
from pathlib import Path

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

import build_db
import queries

ROOT = Path(__file__).parent
DB = ROOT / "data" / "stocks.db"

COLORS = {"Bajaj Auto": "#1f77b4", "Eicher Motors": "#d62728", "Hero Motocorp": "#7f7f7f",
          "Infosys": "#2ca02c", "TCS": "#9467bd", "TVS Motors": "#ff7f0e"}
STOCK_NAMES = [n for n, _ in queries.STOCKS]
TASK_BY_ID = {t["id"]: t for t in queries.TASKS}

st.set_page_config(page_title="Stock Market Analysis in SQL", layout="wide")


# ------------------------------------------------------------------ data
@st.cache_resource
def get_conn():
    if not DB.exists():
        build_db.build(ROOT)
    return build_db.connect(DB, readonly=True)


@st.cache_data(show_spinner=False)
def run(sql, params=()):
    return pd.read_sql_query(sql, get_conn(), params=params)


def prices(adjusted):
    table = "prices_adj" if adjusted else "prices_raw"  # fixed whitelist, not user text
    df = run(f"SELECT stock, date, close_price FROM {table} ORDER BY stock, date")
    df["date"] = pd.to_datetime(df["date"])
    return df


def signals(stock, adjusted):
    table = "signals_adj" if adjusted else "signals_raw"
    df = run(f"SELECT date, close_price, ma20, ma50, signal FROM {table} "
             f"WHERE stock = ? ORDER BY date", params=(stock,))
    df["date"] = pd.to_datetime(df["date"])
    return df


def pct_change_table(adjusted):
    table = "prices_adj" if adjusted else "prices_raw"
    return run(f"""
        WITH ends AS (SELECT stock, MIN(date) AS d0, MAX(date) AS d1 FROM {table} GROUP BY stock)
        SELECT e.stock, f.close_price AS first_close, l.close_price AS last_close,
               ROUND(100.0 * (l.close_price - f.close_price) / f.close_price, 1) AS pct_change
        FROM ends e
        JOIN {table} f ON f.stock = e.stock AND f.date = e.d0
        JOIN {table} l ON l.stock = e.stock AND l.date = e.d1
        ORDER BY pct_change DESC""")


def adjust_toggle(key, default=True):
    return st.toggle("Adjust TCS and Infosys for their 1:1 bonus issues", value=default, key=key,
                     help="Divides every close before the ex-date by 2 (TCS 2018-05-31, "
                          "Infosys 2015-06-15). The other four stocks are unchanged.")


def style_fig(fig, height=420):
    fig.update_layout(height=height, margin=dict(l=10, r=10, t=40, b=10),
                      legend=dict(orientation="h", y=1.08, x=0), hovermode="x unified")
    return fig


# ------------------------------------------------------------------ pages
def page_overview():
    st.title("Stock Market Analysis in SQL")
    st.caption("Six NSE stocks, 1 Jan 2015 to 31 Jul 2018, 889 trading days each. "
               "Every number comes from a SQL query (see the SQL Explorer page).")
    adjusted = adjust_toggle("ov_adj")
    pc = pct_change_table(adjusted).set_index("stock")

    cols = st.columns(6)
    for col, name in zip(cols, STOCK_NAMES):
        col.metric(name, f"{pc.loc[name, 'last_close']:,.2f}", f"{pc.loc[name, 'pct_change']:+.1f}%")
    st.caption("Metric = last close (31 Jul 2018) and change since 1 Jan 2015.")

    if not adjusted:
        st.warning("Raw prices: TCS shows -23.8% and Infosys -30.9% only because each had a 1:1 bonus "
                   "issue that halved the price overnight. Switch the adjustment on to see the real picture.")
    else:
        st.info("Adjusted: TCS +52.4% and Infosys +38.2% (raw prices say -23.8% and -30.9%). "
                "See the Data Trap page for how this was found.")

    df = prices(adjusted)
    df["rebased"] = 100 * df["close_price"] / df.groupby("stock")["close_price"].transform("first")
    fig = go.Figure()
    for name in STOCK_NAMES:
        d = df[df["stock"] == name]
        fig.add_scatter(x=d["date"], y=d["rebased"], name=name, mode="lines",
                        line=dict(color=COLORS[name], width=1.6))
    fig.add_hline(y=100, line_width=1, line_color="#888")
    fig.update_yaxes(title="Close, rebased to 100 on 2015-01-01")
    st.plotly_chart(style_fig(fig, 450), width="stretch")

    st.subheader("Signal summary (adjusted prices)")
    s = run(queries.SUMMARY_SQL)
    view = s[["stock", "pct_change_adj", "buys", "sells", "last_signal", "last_signal_date",
              "winners", "round_trips", "whipsaws", "follow_signals_pct"]].rename(columns={
        "stock": "Stock", "pct_change_adj": "Price change %", "buys": "Buys", "sells": "Sells",
        "last_signal": "Latest signal", "last_signal_date": "Signal date", "winners": "Winning trips",
        "round_trips": "Round trips", "whipsaws": "Whipsaws", "follow_signals_pct": "Follow signals %"})
    st.dataframe(view, hide_index=True, width="stretch")
    st.caption("Round trip = a Buy closed by the next Sell. Whipsaw = round trip closed within 30 days. "
               "Follow signals % compounds every round trip (plus any open Buy marked to 31 Jul 2018); "
               "long-only, no costs or dividends.")


def page_prices():
    st.title("Price Explorer")
    c1, c2 = st.columns([2, 1])
    chosen = c1.multiselect("Stocks", STOCK_NAMES, default=["Bajaj Auto", "TCS"])
    adjusted = c2.toggle("Adjusted for bonus issues", value=True, key="px_adj")
    df = prices(adjusted)
    lo, hi = df["date"].min().date(), df["date"].max().date()
    start, end = st.slider("Date range", min_value=lo, max_value=hi, value=(lo, hi))
    mode = st.radio("Scale", ["Price", "Rebased to 100"], horizontal=True)
    if not chosen:
        st.info("Pick at least one stock.")
        return
    d = df[(df["stock"].isin(chosen)) & (df["date"].dt.date >= start) & (df["date"].dt.date <= end)].copy()
    if mode.startswith("Rebased"):
        d["y"] = 100 * d["close_price"] / d.groupby("stock")["close_price"].transform("first")
    else:
        d["y"] = d["close_price"]
    fig = go.Figure()
    for name in chosen:
        x = d[d["stock"] == name]
        fig.add_scatter(x=x["date"], y=x["y"], name=name, line=dict(color=COLORS[name], width=1.6))
    st.plotly_chart(style_fig(fig, 430), width="stretch")
    if mode == "Price" and len(chosen) > 1:
        st.caption("Prices differ by orders of magnitude (Eicher is above 15,000, TVS below 600). "
                   "Use 'Rebased to 100' to compare them.")

    stats = d.groupby("stock")["close_price"].agg(
        Days="count", Low="min", High="max", Average="mean", First="first", Last="last").round(2)
    stats["Change %"] = (100 * (stats["Last"] / stats["First"] - 1)).round(1)
    st.dataframe(stats, width="stretch")


def page_signals():
    st.title("Golden-Cross Signals")
    c1, c2 = st.columns([2, 1])
    stock = c1.selectbox("Stock", STOCK_NAMES, index=0)
    adjusted = c2.toggle("Adjusted for bonus issues", value=True, key="sg_adj")
    d = signals(stock, adjusted)
    buys, sells = d[d["signal"] == "Buy"], d[d["signal"] == "Sell"]

    fig = go.Figure()
    fig.add_scatter(x=d["date"], y=d["close_price"], name="Close", line=dict(color="#777", width=1))
    fig.add_scatter(x=d["date"], y=d["ma20"], name="20-day average", line=dict(color="#1f77b4", width=1.6))
    fig.add_scatter(x=d["date"], y=d["ma50"], name="50-day average", line=dict(color="#e67e22", width=1.6))
    fig.add_scatter(x=buys["date"], y=buys["close_price"], mode="markers", name=f"Buy ({len(buys)})",
                    marker=dict(symbol="triangle-up", size=11, color="#27ae60"))
    fig.add_scatter(x=sells["date"], y=sells["close_price"], mode="markers", name=f"Sell ({len(sells)})",
                    marker=dict(symbol="triangle-down", size=11, color="#c0392b"))
    st.plotly_chart(style_fig(fig, 470), width="stretch")

    if not adjusted and stock in queries.BONUS_EVENTS:
        st.warning(f"{stock} raw prices include a bonus-issue cliff on {queries.BONUS_EVENTS[stock]}. "
                   "Signals around it are partly artefacts. Turn the adjustment on to compare.")

    last = d[d["signal"] != "Hold"].iloc[-1]
    m1, m2, m3, m4 = st.columns(4)
    m1.metric("Buy signals", len(buys))
    m2.metric("Sell signals", len(sells))
    m3.metric("Latest signal", f"{last['signal']}", last["date"].strftime("%d %b %Y"), delta_color="off")
    m4.metric("Hold days", int((d["signal"] == "Hold").sum()))

    left, right = st.columns(2)
    with left:
        st.subheader("Every Buy and Sell")
        t = d[d["signal"] != "Hold"][["date", "close_price", "ma20", "ma50", "signal"]].copy()
        t["date"] = t["date"].dt.strftime("%Y-%m-%d")
        st.dataframe(t.round(2), hide_index=True, width="stretch", height=360)
    with right:
        st.subheader("Signal on a given day")
        pick = st.date_input("Date", value=pd.Timestamp("2018-06-21").date(),
                             min_value=d["date"].min().date(), max_value=d["date"].max().date())
        row = d[d["date"].dt.date == pick]
        if row.empty:
            st.info(f"{pick} is not a trading day in the data, so there is no signal (NULL).")
        else:
            r = row.iloc[0]
            st.success(f"{pick}: **{r['signal']}**  (close {r['close_price']:,.2f})")
        st.caption("Buy = 20-day average crosses above the 50-day today (it was at or below yesterday). "
                   "Sell = the mirror image. Hold = everything else, including the first weeks when an "
                   "average does not exist yet.")


def page_trap():
    st.title("The Data Trap: Bonus Issues")
    st.write("Task 12 asks for each stock's single worst day. Four are between -6% and -10%. Two are "
             "about -50%. A large profitable company does not lose half its value in a day, so these "
             "were checked against corporate-action records: both were **1:1 bonus issues** (one free "
             "share per share held), which double the share count and halve the price with no change "
             "in value. NSE ex-dates: TCS 31 May 2018, Infosys 15 June 2015.")
    st.subheader("Worst day per stock (raw prices, Task 12)")
    st.dataframe(run(TASK_BY_ID["Task 12"]["sql"]), hide_index=True, width="stretch")

    st.subheader("Raw versus adjusted close")
    raw, adj = prices(False), prices(True)
    cols = st.columns(2)
    for col, name in zip(cols, ["TCS", "Infosys"]):
        r, a = raw[raw["stock"] == name], adj[adj["stock"] == name]
        fig = go.Figure()
        fig.add_scatter(x=r["date"], y=r["close_price"], name="Raw close", line=dict(color="#c0392b", width=1.4))
        fig.add_scatter(x=a["date"], y=a["close_price"], name="Adjusted close", line=dict(color="#1f4e79", width=1.4))
        ev = queries.BONUS_EVENTS[name]
        fig.add_vline(x=pd.Timestamp(ev).timestamp() * 1000, line_dash="dash", line_color="#333")
        fig.update_layout(title=f"{name}: ex-date {ev}")
        col.plotly_chart(style_fig(fig, 340), width="stretch")

    st.subheader("What the adjustment changes")
    pr, pa = pct_change_table(False), pct_change_table(True)
    comp = pr[["stock", "pct_change"]].merge(pa[["stock", "pct_change"]], on="stock",
                                             suffixes=(" raw", " adjusted"))
    comp["swing (points)"] = (comp["pct_change adjusted"] - comp["pct_change raw"]).round(1)
    comp = comp.sort_values("pct_change adjusted", ascending=False).rename(columns={
        "stock": "Stock", "pct_change raw": "Change % (raw)", "pct_change adjusted": "Change % (adjusted)",
        "swing (points)": "Swing (points)"})
    st.dataframe(comp, hide_index=True, width="stretch")

    st.subheader("Signals that exist in only one version")
    diff = run("""
        SELECT r.stock, 'raw only' AS version, r.date, r.signal
        FROM signals_raw r
        LEFT JOIN signals_adj a ON a.stock = r.stock AND a.date = r.date AND a.signal = r.signal
        WHERE r.signal <> 'Hold' AND a.date IS NULL
        UNION ALL
        SELECT a.stock, 'adjusted only', a.date, a.signal
        FROM signals_adj a
        LEFT JOIN signals_raw r ON r.stock = a.stock AND r.date = a.date AND r.signal = a.signal
        WHERE a.signal <> 'Hold' AND r.date IS NULL
        ORDER BY 1, 3""")
    st.dataframe(diff, hide_index=True, width="stretch")
    st.caption("TCS loses its raw Sell on 2018-06-05 (created purely by the price cliff), so its latest "
               "signal becomes a Buy on 2018-04-20. Infosys gains three signals and loses one in mid-2015. "
               "The other four stocks are identical in both versions.")


def page_strategy():
    st.title("Did the Rule Work?")
    st.caption("Adjusted prices. Long-only, one unit per trade, no brokerage, taxes or dividends. "
               "This describes what happened on this data, not what the rule will do.")
    s = run(queries.SUMMARY_SQL)
    fig = go.Figure()
    fig.add_bar(x=s["stock"], y=s["pct_change_adj"], name="Buy and hold", marker_color="#7f8fa6")
    fig.add_bar(x=s["stock"], y=s["follow_signals_pct"], name="Follow the signals", marker_color="#1f4e79")
    fig.update_layout(barmode="group", yaxis_title="Return over the period, %")
    st.plotly_chart(style_fig(fig, 400), width="stretch")
    st.write("Following the Buy-to-Sell signals returned less than simply holding on **all six** stocks. "
             "It came close for TVS Motors and Eicher Motors and lost money outright on Bajaj Auto, "
             "Hero Motocorp and TCS.")

    st.subheader("Round trips and whipsaws")
    t = s[["stock", "round_trips", "winners", "whipsaws", "whipsaw_return_sum",
           "open_buy_date", "open_ret_pct", "ma20_last", "ma50_last"]].rename(columns={
        "stock": "Stock", "round_trips": "Round trips", "winners": "Winners", "whipsaws": "Whipsaws (30 days or less)",
        "whipsaw_return_sum": "Whipsaw sum %", "open_buy_date": "Open Buy since",
        "open_ret_pct": "Open Buy return %", "ma20_last": "20-day avg (last)", "ma50_last": "50-day avg (last)"})
    st.dataframe(t, hide_index=True, width="stretch")

    st.subheader("Every whipsaw (Part 4b)")
    st.dataframe(run(queries.WHIPSAW_SQL), hide_index=True, width="stretch")

    with st.expander("Not in this data"):
        st.markdown("- Dividends and trading costs (each whipsaw would pay brokerage twice)\n"
                    "- A market index, so stock moves cannot be separated from market moves\n"
                    "- News and fundamentals\n"
                    "- Out-of-sample testing: six stocks over 3.6 years, judged on the same data")


def page_sql():
    st.title("SQL Explorer")
    st.caption("Every task from the guide with its query, the expected result, and a Run button. "
               "The full file is at sql/Stock_Market_Analysis.sql.")
    with st.expander("Setup tables built when the database is created"):
        for name, sql in queries.SETUP:
            st.markdown(f"**{name}**")
            st.code(sql, language="sql")
    labels = [f"{t['id']}: {t['title']}" for t in queries.TASKS]
    pick = st.selectbox("Task", labels)
    t = queries.TASKS[labels.index(pick)]
    st.write(t["description"])
    st.markdown(f"**Expected:** {t['expected']}")
    if t["build"]:
        st.markdown("Creates a table (already run during setup):")
        st.code(t["build"], language="sql")
    st.code(t["sql"], language="sql")
    if st.button("Run query", type="primary"):
        res = run(t["sql"])
        st.caption(f"{len(res)} rows")
        st.dataframe(res, hide_index=True, width="stretch")

    st.divider()
    st.subheader("Try your own query (read-only)")
    sql = st.text_area("SQL", height=140, value="SELECT stock, COUNT(*) AS days\nFROM signals_adj\nGROUP BY stock;")
    if st.button("Run my query"):
        body = sql.strip().rstrip(";")
        if not body.lower().startswith(("select", "with")) or ";" in body:
            st.error("Only a single SELECT or WITH query is allowed here.")
        else:
            try:
                res = run(body)
                st.caption(f"{len(res)} rows")
                st.dataframe(res, hide_index=True, width="stretch")
            except Exception as e:  # shows the SQL error to the user
                st.error(f"SQL error: {e}")
    st.caption("Tables: bajaj_auto, eicher_motors, hero_motocorp, infosys, tcs, tvs_motors, bajaj1, bajaj2, "
               "master_table, prices_raw, prices_adj, signals_raw, signals_adj.")


def page_quality():
    st.title("Data Check")
    st.subheader("Rows and date range per table (should be 889 each)")
    union = "\nUNION ALL\n".join(
        f"SELECT '{n}' AS stock, COUNT(*) AS rows_, MIN(date) AS first_day, MAX(date) AS last_day, "
        f"SUM(deliverable_qty IS NULL) AS missing_deliverable_qty FROM {t}" for n, t in queries.STOCKS)
    st.dataframe(run(union).rename(columns={"rows_": "rows"}), hide_index=True, width="stretch")
    st.subheader("Missing deliverable quantity (Task 4)")
    st.dataframe(run(TASK_BY_ID["Task 4"]["sql"]), hide_index=True, width="stretch")
    st.caption("Six rows on only two dates (2015-12-09 and 2017-08-31), the same dates across unrelated "
               "companies, which points to the data source rather than the companies. The analysis uses "
               "close prices only, so it is unaffected.")


PAGES = {"Overview": page_overview, "Price Explorer": page_prices, "Signals": page_signals,
         "Data Trap": page_trap, "Did the Rule Work?": page_strategy, "SQL Explorer": page_sql,
         "Data Check": page_quality}

with st.sidebar:
    st.header("Stock Market Analysis")
    page = st.radio("Page", list(PAGES), label_visibility="collapsed")
    st.caption("SQLite + Streamlit. TCS and Infosys are adjusted for 1:1 bonus issues unless a page says otherwise.")

PAGES[page]()
