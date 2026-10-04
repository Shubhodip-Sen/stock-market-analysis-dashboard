# Stock Market Analysis in SQL - Streamlit dashboard

Six NSE stocks (Bajaj Auto, Eicher Motors, Hero Motocorp, Infosys, TCS, TVS Motors),
1 Jan 2015 to 31 Jul 2018. SQLite + Streamlit; every number on screen comes from SQL.

## Run it

```bash
pip install -r requirements.txt
streamlit run app.py
```

On first start the app builds `data/stocks.db` from the six CSVs in `data/` (a few seconds).
To build it yourself: `python build_db.py`. Only relative paths are used, so the folder can live anywhere.

## Files

| File | What it is |
|---|---|
| `app.py` | The dashboard (7 pages) |
| `queries.py` | All SQL in one place: setup tables, Tasks 1-13, stretch challenge, insights queries |
| `build_db.py` | Loads the CSVs (converts `31-July-2018` dates to ISO, sorts by date) and builds the tables |
| `sql/Stock_Market_Analysis.sql` | The same SQL as a plain file, generated from `queries.py` |
| `data/` | The six CSVs (and `stocks.db` once built) |

## Pages

- **Overview**: last close and change per stock, rebased chart, signal summary. Adjustment toggle.
- **Price Explorer**: pick stocks and dates, price or rebased view, summary stats.
- **Signals**: 20/50-day averages with Buy/Sell markers, every signal, and a signal-on-a-date lookup (Task 9).
- **Data Trap**: worst day per stock, raw vs adjusted charts, effect of the bonus-issue adjustment.
- **Did the Rule Work?**: follow-the-signals vs buy-and-hold, round trips, whipsaws.
- **SQL Explorer**: every task with its query, expected result and a Run button, plus a read-only query box.
- **Data Check**: row counts, date ranges, missing deliverable quantity (Task 4).

## Key results

- TCS (31 May 2018) and Infosys (15 Jun 2015) each fall about 50% in one day: 1:1 bonus issues, not crashes.
  Adjusted, TCS is +52.4% (raw -23.8%) and Infosys +38.2% (raw -30.9%).
- Bajaj Auto: 12 Buys and 11 Sells; all six stocks together 56 Buys and 57 Sells on raw prices.
- Following the golden-cross signals returned less than buy-and-hold on all six stocks (long-only, no costs).
- These are findings about a rule on this data, not investment advice.

## Notes

- Needs SQLite 3.25+ (window functions). `LN`/`EXP` are registered in Python, so older builds work too.
- The query box on the SQL Explorer page opens the database read-only and accepts a single SELECT or WITH query.
