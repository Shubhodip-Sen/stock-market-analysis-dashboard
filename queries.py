"""All SQL for the Stock Market Analysis project (SQLite dialect).

This module is the single source of truth: build_db.py runs the SETUP and
`build` statements, app.py shows and runs the `sql` queries, and
write_sql_file() exports everything to sql/Stock_Market_Analysis.sql.
"""

STOCKS = [  # (display name, table name)
    ("Bajaj Auto", "bajaj_auto"),
    ("Eicher Motors", "eicher_motors"),
    ("Hero Motocorp", "hero_motocorp"),
    ("Infosys", "infosys"),
    ("TCS", "tcs"),
    ("TVS Motors", "tvs_motors"),
]
# 1:1 bonus issues: closes BEFORE the ex-date are divided by 2
BONUS_EVENTS = {"TCS": "2018-05-31", "Infosys": "2015-06-15"}


def _union(select_expr):
    """UNION ALL of the six stock tables; select_expr(name, table) -> SELECT text."""
    return "\n    UNION ALL\n    ".join(select_expr(n, t) for n, t in STOCKS)


def _raw_select(n, t):
    return f"SELECT '{n}' AS stock, date, close_price FROM {t}"


def _adj_select(n, t):
    if n in BONUS_EVENTS:
        d = BONUS_EVENTS[n]
        return (f"SELECT '{n}' AS stock, date,\n"
                f"           CASE WHEN date < '{d}' THEN close_price / 2 ELSE close_price END AS close_price\n"
                f"    FROM {t}")
    return _raw_select(n, t)


PRICES_RAW_CTE = "prices AS (\n    " + _union(_raw_select) + "\n)"
PRICES_ADJ_CTE = "prices AS (\n    " + _union(_adj_select) + "\n)"

# One signal pipeline, used for raw and adjusted prices alike.
_SIGNALS_BODY = """ma AS (
    SELECT stock, date, close_price,
           CASE WHEN ROW_NUMBER() OVER (PARTITION BY stock ORDER BY date) >= 20
                THEN AVG(close_price) OVER (PARTITION BY stock ORDER BY date
                                            ROWS BETWEEN 19 PRECEDING AND CURRENT ROW)
           END AS ma20,
           CASE WHEN ROW_NUMBER() OVER (PARTITION BY stock ORDER BY date) >= 50
                THEN AVG(close_price) OVER (PARTITION BY stock ORDER BY date
                                            ROWS BETWEEN 49 PRECEDING AND CURRENT ROW)
           END AS ma50
    FROM prices
),
lagged AS (
    SELECT stock, date, close_price, ma20, ma50,
           LAG(ma20) OVER (PARTITION BY stock ORDER BY date) AS prev_ma20,
           LAG(ma50) OVER (PARTITION BY stock ORDER BY date) AS prev_ma50
    FROM ma
),
sig AS (
    SELECT stock, date, close_price, ma20, ma50,
           CASE
               WHEN ma20 IS NULL OR ma50 IS NULL
                 OR prev_ma20 IS NULL OR prev_ma50 IS NULL THEN 'Hold'
               WHEN ma20 > ma50 AND prev_ma20 <= prev_ma50 THEN 'Buy'
               WHEN ma20 < ma50 AND prev_ma20 >= prev_ma50 THEN 'Sell'
               ELSE 'Hold'
           END AS signal
    FROM lagged
)"""

SETUP = [
    ("prices_raw", "DROP TABLE IF EXISTS prices_raw;\nCREATE TABLE prices_raw AS\n"
                   + _union(_raw_select).replace("\n    ", "\n") + ";"),
    ("prices_adj", "DROP TABLE IF EXISTS prices_adj;\nCREATE TABLE prices_adj AS\n"
                   + _union(_adj_select).replace("\n    ", "\n") + ";"),
    ("signals_raw", "DROP TABLE IF EXISTS signals_raw;\nCREATE TABLE signals_raw AS\n"
                    "WITH prices AS (SELECT stock, date, close_price FROM prices_raw),\n"
                    + _SIGNALS_BODY + "\nSELECT stock, date, close_price, ma20, ma50, signal FROM sig;"),
    ("signals_adj", "DROP TABLE IF EXISTS signals_adj;\nCREATE TABLE signals_adj AS\n"
                    "WITH prices AS (SELECT stock, date, close_price FROM prices_adj),\n"
                    + _SIGNALS_BODY + "\nSELECT stock, date, close_price, ma20, ma50, signal FROM sig;"),
]

# ---------------------------------------------------------------- tasks
TASKS = []


def task(id_, title, description, expected, sql, build=None):
    TASKS.append(dict(id=id_, title=title, description=description,
                      expected=expected, sql=sql.strip(), build=build.strip() if build else None))


task("Task 1", "How much history do we have?",
     "Trading days, first and last date for Bajaj Auto.",
     "889 trading days, 2015-01-01 to 2018-07-31",
     "SELECT COUNT(*) AS trading_days, MIN(date) AS first_day, MAX(date) AS last_day\nFROM bajaj_auto;")

task("Task 2", "Eicher's five best closes",
     "Top five closing prices for Eicher Motors.",
     "Top close 32,786.40 on 2017-09-07; all five dates in September 2017",
     "SELECT date, close_price\nFROM eicher_motors\nORDER BY close_price DESC\nLIMIT 5;")

task("Task 3", "TCS, year by year",
     "Average closing price per calendar year for TCS (prices before 31 May 2018 are pre-bonus, see Tasks 12 and 13).",
     "2015 2537.39 | 2016 2419.00 | 2017 2475.36 | 2018 2729.12",
     "SELECT strftime('%Y', date) AS year, ROUND(AVG(close_price), 2) AS avg_close\nFROM tcs\nGROUP BY year\nORDER BY year;")

task("Task 4", "Find the holes",
     "Rows with NULL deliverable_qty across all six tables.",
     "6 rows on only 2 dates: 2015-12-09 and 2017-08-31",
     _union(lambda n, t: f"SELECT '{t}' AS stock, date FROM {t} WHERE deliverable_qty IS NULL")
     .replace("\n    UNION ALL\n    ", "\nUNION ALL\n") + ";")

task("Task 5", "Moving averages for Bajaj Auto (table bajaj1)",
     "ma20 = today plus previous 19 closes; ma50 = today plus previous 49. NULL until a full window exists.",
     "889 rows; first ma20 2415.53 on 2015-01-29; first ma50 2283.80 on 2015-03-13; ma20 on 2018-07-31 = 2918.51",
     "SELECT * FROM bajaj1 ORDER BY date LIMIT 60;",
     build="""
DROP TABLE IF EXISTS bajaj1;
CREATE TABLE bajaj1 AS
SELECT date, close_price,
       CASE WHEN ROW_NUMBER() OVER (ORDER BY date) >= 20
            THEN ROUND(AVG(close_price) OVER (ORDER BY date ROWS BETWEEN 19 PRECEDING AND CURRENT ROW), 2)
       END AS ma20,
       CASE WHEN ROW_NUMBER() OVER (ORDER BY date) >= 50
            THEN ROUND(AVG(close_price) OVER (ORDER BY date ROWS BETWEEN 49 PRECEDING AND CURRENT ROW), 2)
       END AS ma50
FROM bajaj_auto;""")

task("Task 6", "Master table: one closing-price column per stock",
     "One row per date, joining all six stocks on date.",
     "889 rows, 7 columns, no NULLs; 2018-07-31: bajaj 2700.70, tvs 517.45",
     "SELECT * FROM master_table ORDER BY date DESC LIMIT 5;",
     build="""
DROP TABLE IF EXISTS master_table;
CREATE TABLE master_table AS
SELECT b.date,
       b.close_price AS bajaj, t.close_price AS tcs, v.close_price AS tvs,
       i.close_price AS infosys, e.close_price AS eicher, h.close_price AS hero
FROM bajaj_auto b
JOIN tcs t           ON t.date = b.date
JOIN tvs_motors v    ON v.date = b.date
JOIN infosys i       ON i.date = b.date
JOIN eicher_motors e ON e.date = b.date
JOIN hero_motocorp h ON h.date = b.date;""")

task("Task 7", "Golden-cross signals for Bajaj Auto (table bajaj2)",
     "Buy = ma20 crosses above ma50 today (yesterday ma20 <= ma50). Sell = crosses below. Hold otherwise, including NULL days.",
     "889 rows; first Buy 2015-05-18; first Sell 2015-08-24",
     "SELECT * FROM bajaj2 WHERE signal <> 'Hold' ORDER BY date;",
     build="""
DROP TABLE IF EXISTS bajaj2;
CREATE TABLE bajaj2 AS
WITH t AS (
    SELECT date, close_price, ma20, ma50,
           LAG(ma20) OVER (ORDER BY date) AS prev_ma20,
           LAG(ma50) OVER (ORDER BY date) AS prev_ma50
    FROM bajaj1
)
SELECT date, close_price,
       CASE
           WHEN ma20 IS NULL OR ma50 IS NULL
             OR prev_ma20 IS NULL OR prev_ma50 IS NULL THEN 'Hold'
           WHEN ma20 > ma50 AND prev_ma20 <= prev_ma50 THEN 'Buy'
           WHEN ma20 < ma50 AND prev_ma20 >= prev_ma50 THEN 'Sell'
           ELSE 'Hold'
       END AS signal
FROM t;""")

task("Task 8", "How often did it trigger?",
     "Count of Buy, Hold and Sell days for Bajaj Auto.",
     "Buy 12 | Hold 866 | Sell 11 (total 889)",
     "SELECT signal, COUNT(*) AS days\nFROM bajaj2\nGROUP BY signal\nORDER BY signal;")

task("Task 9", "Signal on a given day",
     "Looks the signal up by date. A non-trading day returns NULL. (MySQL would use a function; SQLite has none, so this is a lookup query. The dashboard has a date picker on the Signals page.)",
     "2018-06-21 Buy | 2015-05-18 Buy | 2016-01-04 Hold | 2018-06-24 (a Sunday) NULL",
     """
SELECT d.date, (SELECT signal FROM bajaj2 WHERE date = d.date) AS signal
FROM (SELECT '2018-06-21' AS date UNION ALL SELECT '2015-05-18'
      UNION ALL SELECT '2016-01-04' UNION ALL SELECT '2018-06-24') AS d;""")

_T10 = f"""
WITH {PRICES_RAW_CTE},
{_SIGNALS_BODY},
counts AS (
    SELECT stock,
           COUNT(CASE WHEN signal = 'Buy'  THEN 1 END) AS buys,
           COUNT(CASE WHEN signal = 'Sell' THEN 1 END) AS sells
    FROM sig
    GROUP BY stock
),
latest AS (
    SELECT stock, date, signal,
           ROW_NUMBER() OVER (PARTITION BY stock ORDER BY date DESC) AS rn
    FROM sig
    WHERE signal <> 'Hold'
)
SELECT c.stock, c.buys, c.sells, l.date AS last_signal_date, l.signal AS last_signal
FROM counts c
JOIN latest l ON l.stock = c.stock AND l.rn = 1
ORDER BY c.stock;"""
task("Task 10", "All six stocks in one query",
     "One query, no per-stock tables. Every window is PARTITIONed BY stock so one stock never leaks into the next. Averages are unrounded. Uses RAW prices.",
     "6 rows; 56 Buys and 57 Sells in total",
     _T10)

task("Task 11", "Who went up? (raw prices)",
     "First versus last trading day, percentage change, raw closes.",
     "TVS 86.9 | Eicher 82.6 | Bajaj 10.0 | Hero 6.0 | TCS -23.8 | Infosys -30.9",
     f"""
WITH {PRICES_RAW_CTE},
ends AS (SELECT stock, MIN(date) AS first_date, MAX(date) AS last_date FROM prices GROUP BY stock)
SELECT e.stock, f.close_price AS first_close, l.close_price AS last_close,
       ROUND(100.0 * (l.close_price - f.close_price) / f.close_price, 1) AS pct_change
FROM ends e
JOIN prices f ON f.stock = e.stock AND f.date = e.first_date
JOIN prices l ON l.stock = e.stock AND l.date = e.last_date
ORDER BY pct_change DESC;""")

task("Task 12", "The data trap: each stock's worst day",
     "Largest one-day fall per stock. TCS and Infosys show about -50%: not crashes, but 1:1 bonus issues (NSE ex-dates 31-May-2018 and 15-Jun-2015).",
     "TCS 2018-05-31 -50.4 | Infosys 2015-06-15 -49.9 | the other four between -6.2 and -9.7",
     f"""
WITH {PRICES_RAW_CTE},
moves AS (
    SELECT stock, date, close_price,
           100.0 * (close_price / LAG(close_price) OVER (PARTITION BY stock ORDER BY date) - 1) AS pct_move
    FROM prices
),
ranked AS (
    SELECT stock, date, close_price, pct_move,
           ROW_NUMBER() OVER (PARTITION BY stock ORDER BY pct_move ASC) AS rn
    FROM moves
    WHERE pct_move IS NOT NULL
)
SELECT stock, date, close_price, ROUND(pct_move, 1) AS pct_move
FROM ranked
WHERE rn = 1
ORDER BY pct_move;""")

task("Task 13", "Fix it: adjust TCS and Infosys for the bonus issues",
     "Divide every close BEFORE the event date by 2 (TCS 2018-05-31, Infosys 2015-06-15); later closes are unchanged.",
     "Infosys 38.2 | TCS 52.4",
     """
WITH adjusted AS (
    SELECT 'TCS' AS stock, date,
           CASE WHEN date < '2018-05-31' THEN close_price / 2 ELSE close_price END AS adj_close
    FROM tcs
    UNION ALL
    SELECT 'Infosys' AS stock, date,
           CASE WHEN date < '2015-06-15' THEN close_price / 2 ELSE close_price END AS adj_close
    FROM infosys
)
SELECT stock,
       ROUND(100.0 * (MAX(CASE WHEN date = '2018-07-31' THEN adj_close END)
                    / MAX(CASE WHEN date = '2015-01-01' THEN adj_close END) - 1), 1) AS adjusted_pct_change
FROM adjusted
GROUP BY stock
ORDER BY stock;""")

task("Stretch", "TCS signals: raw versus adjusted",
     "Signals that exist in only one of the two versions (tables signals_raw and signals_adj, built in the setup step).",
     "One raw-only Sell on 2018-06-05 (created by the price cliff); nothing new on adjusted. Counts 12/13 raw become 12/12.",
     """
SELECT 'raw only' AS version, r.date, r.signal
FROM signals_raw r
LEFT JOIN signals_adj a ON a.stock = r.stock AND a.date = r.date AND a.signal = r.signal
WHERE r.stock = 'TCS' AND r.signal <> 'Hold' AND a.date IS NULL
UNION ALL
SELECT 'adjusted only', a.date, a.signal
FROM signals_adj a
LEFT JOIN signals_raw r ON r.stock = a.stock AND r.date = a.date AND r.signal = a.signal
WHERE a.stock = 'TCS' AND a.signal <> 'Hold' AND r.date IS NULL
ORDER BY 2;""")

SUMMARY_SQL = """
WITH counts AS (
    SELECT stock,
           COUNT(CASE WHEN signal = 'Buy'  THEN 1 END) AS buys,
           COUNT(CASE WHEN signal = 'Sell' THEN 1 END) AS sells
    FROM signals_adj
    GROUP BY stock
),
nonhold AS (
    SELECT stock, date, close_price, signal,
           LEAD(signal)    OVER (PARTITION BY stock ORDER BY date)      AS next_signal,
           LEAD(date)      OVER (PARTITION BY stock ORDER BY date)      AS next_date,
           LEAD(close_price) OVER (PARTITION BY stock ORDER BY date)    AS next_close,
           ROW_NUMBER()    OVER (PARTITION BY stock ORDER BY date DESC) AS rn_desc
    FROM signals_adj
    WHERE signal <> 'Hold'
),
trips AS (
    SELECT stock, date AS buy_date, next_date AS sell_date,
           CAST(julianday(next_date) - julianday(date) AS INTEGER) AS days_held,
           100.0 * (next_close / close_price - 1) AS ret_pct
    FROM nonhold
    WHERE signal = 'Buy' AND next_signal = 'Sell'
),
trip_sum AS (
    SELECT stock,
           COUNT(*)                                    AS round_trips,
           COUNT(CASE WHEN ret_pct > 0 THEN 1 END)     AS winners,
           COUNT(CASE WHEN days_held <= 30 THEN 1 END) AS whipsaws,
           ROUND(SUM(CASE WHEN days_held <= 30 THEN ret_pct END), 1) AS whipsaw_return_sum,
           EXP(SUM(LN(1 + ret_pct / 100.0)))           AS growth
    FROM trips
    GROUP BY stock
),
open_pos AS (
    SELECT n.stock, n.date AS open_buy_date, p.close_price / n.close_price AS open_growth
    FROM nonhold n
    JOIN signals_adj p ON p.stock = n.stock AND p.date = '2018-07-31'
    WHERE n.rn_desc = 1 AND n.signal = 'Buy'
),
ends AS (SELECT stock, MIN(date) AS first_date, MAX(date) AS last_date FROM signals_adj GROUP BY stock),
latest AS (SELECT stock, date, signal FROM nonhold WHERE rn_desc = 1)
SELECT e.stock,
       f.close_price AS first_close_adj,
       l.close_price AS last_close,
       ROUND(100.0 * (l.close_price - f.close_price) / f.close_price, 1) AS pct_change_adj,
       c.buys, c.sells,
       la.date AS last_signal_date, la.signal AS last_signal,
       t.round_trips, t.winners, t.whipsaws, t.whipsaw_return_sum,
       o.open_buy_date,
       ROUND(100.0 * (o.open_growth - 1), 1) AS open_ret_pct,
       ROUND(100.0 * (t.growth * COALESCE(o.open_growth, 1) - 1), 1) AS follow_signals_pct,
       ROUND(l.ma20, 2) AS ma20_last,
       ROUND(l.ma50, 2) AS ma50_last
FROM ends e
JOIN signals_adj f ON f.stock = e.stock AND f.date = e.first_date
JOIN signals_adj l ON l.stock = e.stock AND l.date = e.last_date
JOIN counts c      ON c.stock = e.stock
JOIN latest la     ON la.stock = e.stock
JOIN trip_sum t    ON t.stock = e.stock
LEFT JOIN open_pos o ON o.stock = e.stock
ORDER BY e.stock;""".strip()

task("Part 4a", "Insights summary: one row per stock (adjusted prices)",
     "pct_change_adj, signal counts, latest signal, winning round trips, whipsaws (Buy closed by a Sell within 30 days), compounded return of following the signals, and the averages on the last day. Long-only, one unit per trade, no costs or dividends.",
     "Winners: Bajaj 4/11, Eicher 6/6, Hero 3/9, Infosys 3/9, TCS 2/11, TVS 3/8. follow_signals_pct: Bajaj -2.7, Eicher 76.5, Hero -16.3, Infosys 7.1, TCS -22.4, TVS 85.0",
     SUMMARY_SQL)

WHIPSAW_SQL = """
WITH nonhold AS (
    SELECT stock, date, close_price, signal,
           LEAD(signal)      OVER (PARTITION BY stock ORDER BY date) AS next_signal,
           LEAD(date)        OVER (PARTITION BY stock ORDER BY date) AS next_date,
           LEAD(close_price) OVER (PARTITION BY stock ORDER BY date) AS next_close
    FROM signals_adj
    WHERE signal <> 'Hold'
)
SELECT stock, date AS buy_date, next_date AS sell_date,
       CAST(julianday(next_date) - julianday(date) AS INTEGER) AS days_held,
       ROUND(100.0 * (next_close / close_price - 1), 1) AS ret_pct
FROM nonhold
WHERE signal = 'Buy' AND next_signal = 'Sell'
  AND julianday(next_date) - julianday(date) <= 30
ORDER BY stock, buy_date;""".strip()
task("Part 4b", "Every whipsaw (Buy closed by a Sell within 30 days)",
     "Short round trips on adjusted prices.",
     "11 rows: Bajaj 5, TVS 2, Infosys 2, Hero 1, TCS 1",
     WHIPSAW_SQL)


def write_sql_file(path):
    head = """-- =====================================================================
-- STOCK MARKET ANALYSIS IN SQL  (SQLite dialect)
-- Six NSE stocks, 01-Jan-2015 to 31-Jul-2018, 889 trading days each.
--
-- This file is GENERATED from queries.py (the same SQL the dashboard runs).
-- To run it by hand:   python build_db.py     (creates data/stocks.db from the CSVs)
--                      sqlite3 data/stocks.db < sql/Stock_Market_Analysis.sql
-- Needs SQLite 3.35+ (window functions, LN/EXP). The dashboard registers LN/EXP
-- itself, so it also works on older SQLite builds.
-- =====================================================================

"""
    parts = [head, "-- ---------- SETUP (run by build_db.py) ----------\n"]
    for name, sql in SETUP:
        parts.append(f"-- {name}\n{sql}\n")
    for t in TASKS:
        parts.append(f"\n-- ---------------------------------------------------------------------\n"
                     f"-- {t['id']}: {t['title']}\n-- {t['description']}\n-- Expected: {t['expected']}\n"
                     f"-- ---------------------------------------------------------------------\n")
        if t["build"]:
            parts.append(t["build"] + "\n\n")
        parts.append(t["sql"] + "\n")
    parts.append("\n-- END OF FILE\n")
    with open(path, "w", encoding="utf-8") as f:
        f.write("".join(parts))
