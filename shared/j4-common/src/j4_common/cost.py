"""Token -> rupee cost. Prices are passed in by each cloud adapter."""
import os

USD_TO_INR = float(os.getenv("USD_TO_INR", "95.92"))  # override: export USD_TO_INR=96.5


def estimate_cost_inr(prices_usd_per_m: dict, model: str, tokens_in: int, tokens_out: int) -> float | None:
    price = prices_usd_per_m.get(model)
    if price is None:
        return None
    usd = tokens_in / 1e6 * price[0] + tokens_out / 1e6 * price[1]
    return usd * USD_TO_INR
