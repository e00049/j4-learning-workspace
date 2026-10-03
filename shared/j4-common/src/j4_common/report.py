"""Cross-cloud scorecard: merge every saved eval result into one table (A9).

Run from ANY cloud project (each has j4_common installed):
    uv run python -m j4_common.report
"""
from __future__ import annotations

import json

from j4_common.evals import RESULTS_DIR

CLOUD_ORDER = {"aws": 0, "azure": 1, "gcp": 2}
CLOUD_LABEL = {"aws": "AWS", "azure": "Azure", "gcp": "GCP"}


def main() -> None:
    files = sorted(RESULTS_DIR.glob("*.json"))
    if not files:
        raise SystemExit("No results yet. Run a cloud's evals command first.")
    rows = [json.loads(f.read_text()) for f in files]
    rows.sort(key=lambda r: (CLOUD_ORDER.get(r["provider"], 9), r["model"]))

    print(f"\n📊 Cross-cloud scorecard ({len(rows)} model(s))\n")
    print(f"{'Cloud':<6} {'Model':<26} {'Accuracy':>9} {'Consistency':>12} {'Avg ms':>7} "
          f"{'P50 ms':>7} {'₹/1K calls':>11}  {'Prompt':<6} {'Run at (UTC)':<20}")
    print("-" * 115)
    for r in rows:
        per_k = f"{r['cost_inr_per_call'] * 1000:.2f}" if r["cost_inr_per_call"] is not None else "n/a"
        print(f"{CLOUD_LABEL.get(r['provider'], r['provider']):<6} {r['model']:<26} "
              f"{r['accuracy']:>8.1f}% {r['consistency']:>11.1f}% {r['avg_ms'] or 0:>7} "
              f"{r['p50_ms'] or 0:>7} {per_k:>11}  {r['prompt']:<6} {r['timestamp'][:19]:<20}")

    # Fairness check: only compare like with like.
    setups = {(r["prompt"], r["golden"], r["runs"], r.get("contract", "1")) for r in rows}
    if len(setups) > 1:
        print("\n⚠️  NOT a fair comparison - results use different setups (prompt, golden, runs, contract):")
        for s in sorted(setups):
            print(f"   {s}")

    passing = [r for r in rows
               if r["accuracy"] == 100 and r["consistency"] == 100 and r["cost_inr_per_call"] is not None]
    if passing:
        best = min(passing, key=lambda r: r["cost_inr_per_call"])
        priciest = max(passing, key=lambda r: r["cost_inr_per_call"])
        print(f"\n🏆 Recommended: {CLOUD_LABEL.get(best['provider'])} {best['model']} "
              f"- cheapest model that passes 100% accuracy and consistency")
        if priciest is not best:
            ratio = priciest["cost_inr_per_call"] / best["cost_inr_per_call"]
            print(f"   {ratio:.1f}× cheaper than {CLOUD_LABEL.get(priciest['provider'])} {priciest['model']} "
                  f"for the same result")
    else:
        print("\n🚫 No model passed 100% accuracy and consistency.")
        scored = [r for r in rows if r["cost_inr_per_call"] is not None]
        if scored:
            top = max(scored, key=lambda r: (r["accuracy"], r["consistency"], -r["cost_inr_per_call"]))
            print(f"   Best so far: {CLOUD_LABEL.get(top['provider'])} {top['model']} "
                  f"({top['accuracy']}% accuracy, {top['consistency']}% consistency)")

    weak = {r["model"]: r.get("field_errors", {}) for r in rows if any(r.get("field_errors", {}).values())}
    if weak:
        print("\n🔎 Errors by field (where models struggle):")
        for model, errs in weak.items():
            print(f"   {model:<26} " + ", ".join(f"{f}={n}" for f, n in errs.items() if n))


if __name__ == "__main__":
    main()
