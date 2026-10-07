from pathlib import Path
import pandas as pd
from mcp.server.fastmcp import FastMCP

CSV = Path(__file__).resolve().parent.parent / "data" / "transactions_sep2026.csv"
mcp = FastMCP("wallettracker")

def df():
    return pd.read_csv(CSV)

@mcp.tool()
def get_total_spend() -> int:
    """Total spend in INR for the user's current statement (September 2026). Use this for any 'total spend' or 'this month' question."""

@mcp.tool()
def get_total_spend() -> int:
    """Total spend in INR for September 2026."""
    return int(df()["amount_inr"].sum())

@mcp.tool()
def spend_by_category(exclude: list[str] = []) -> dict:
    """Spend in INR per category, highest first. Optionally exclude categories, e.g. ["Rent", "Investment"]."""
    d = df()
    d = d[~d["category"].isin(exclude)]
    return {k: int(v) for k, v in d.groupby("category")["amount_inr"].sum().sort_values(ascending=False).items()}

@mcp.tool()
def merchant_spend(merchants: list[str]) -> dict:
    """Spend in INR for the given merchants, e.g. ["Swiggy", "Zomato"], plus the combined total."""
    d = df()
    out = {m: int(d.loc[d["merchant"] == m, "amount_inr"].sum()) for m in merchants}
    out["total"] = sum(out.values())
    return out

if __name__ == "__main__":
    mcp.run()

