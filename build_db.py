"""Builds data/stocks.db from the six CSV files in data/ (relative paths only).

Run directly (python build_db.py) or let app.py call build() on first start.
"""
import math
import sqlite3
from datetime import datetime
from pathlib import Path

import pandas as pd

import queries

COLUMNS = ["date", "open_price", "high_price", "low_price", "close_price", "wap",
           "no_of_shares", "no_of_trades", "total_turnover", "deliverable_qty",
           "pct_deli_qty", "spread_high_low", "spread_close_open"]
CSV_NAMES = {"bajaj_auto": "Bajaj Auto.csv", "eicher_motors": "Eicher Motors.csv",
             "hero_motocorp": "Hero Motocorp.csv", "infosys": "Infosys.csv",
             "tcs": "TCS.csv", "tvs_motors": "TVS Motors.csv"}


def connect(db_path, readonly=False):
    """SQLite connection with LN/EXP registered so older SQLite builds work too."""
    if readonly:
        con = sqlite3.connect(f"file:{Path(db_path).as_posix()}?mode=ro", uri=True,
                              check_same_thread=False)
    else:
        con = sqlite3.connect(db_path, check_same_thread=False)
    con.create_function("LN", 1, lambda x: None if x is None or x <= 0 else math.log(x),
                        deterministic=True)
    con.create_function("EXP", 1, lambda x: None if x is None else math.exp(x),
                        deterministic=True)
    return con


def build(root=None):
    root = Path(root) if root else Path(__file__).parent
    data = root / "data"
    db_path = data / "stocks.db"
    if db_path.exists():
        db_path.unlink()
    con = connect(db_path)
    for table, fname in CSV_NAMES.items():
        df = pd.read_csv(data / fname)
        df.columns = COLUMNS
        df["date"] = df["date"].astype(str).str.strip().map(
            lambda s: datetime.strptime(s, "%d-%B-%Y").strftime("%Y-%m-%d"))
        df = df.sort_values("date")
        df.to_sql(table, con, index=False)
        con.execute(f"CREATE UNIQUE INDEX idx_{table}_date ON {table}(date)")
    for _, sql in queries.SETUP:
        con.executescript(sql)
    for t in queries.TASKS:
        if t["build"]:
            con.executescript(t["build"])
    con.commit()
    con.close()
    (root / "sql").mkdir(exist_ok=True)
    queries.write_sql_file(root / "sql" / "Stock_Market_Analysis.sql")
    return db_path


if __name__ == "__main__":
    p = build()
    print(f"Built {p}")
