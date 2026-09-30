"""Eval runner: score the categorizer against a golden answer key (Phase 0, Step 5b).

Run from ai-learning/aws-learning:
    uv run python -m aws_ai_lab.evals --runs 3 \
        --models us.amazon.nova-micro-v1:0,us.amazon.nova-lite-v1:0,us.amazon.nova-2-lite-v1:0
"""
from __future__ import annotations

import argparse
import json
import sys
from collections import defaultdict
from pathlib import Path

from botocore.exceptions import SSOTokenLoadError, TokenRetrievalError, UnauthorizedSSOTokenError

from aws_ai_lab.categorizer import DEFAULT_MODEL, REPO_ROOT, categorize

GOLDEN_DEFAULT = REPO_ROOT / "shared" / "evals" / "categorizer-golden-v1.json"
FIELDS = ("merchant", "amount", "type", "category")


def normalise(txn: dict) -> tuple:
    """Make comparison fair: merchant is case-insensitive, amount is a float."""
    return (txn["merchant"].strip().lower(), float(txn["amount"]), txn["type"], txn["category"])


def mismatches(expected: list[dict], actual: list[dict]) -> list[str]:
    """Human-readable differences between the answer key and the model output."""
    problems = []
    if len(expected) != len(actual):
        problems.append(f"expected {len(expected)} transactions, got {len(actual)}")
    for i, (exp, act) in enumerate(zip(expected, actual), start=1):
        for field, e, a in zip(FIELDS, normalise(exp), normalise(act)):
            if e != a:
                problems.append(f"txn {i} {field}: expected {e!r}, got {a!r}")
    return problems


def run_model(model: str, cases: list[dict], runs: int, prompt: str) -> dict:
    stats = {
        "txn_total": 0, "txn_ok": 0, "cost": 0.0, "cost_known": True,
        "latencies": [], "failures": [], "outputs": defaultdict(set),
    }
    for run in range(1, runs + 1):
        for case in cases:
            expected = case["expected"]
            stats["txn_total"] += len(expected)
            try:
                out = categorize(case["input"], model, prompt)
            except RuntimeError:                       # output failed Pydantic validation twice
                stats["failures"].append(f"run {run} · {case['id']}: invalid output (validation)")
                stats["outputs"][case["id"]].add("INVALID")
                continue

            actual = [t.model_dump() for t in out["result"].transactions]
            stats["txn_ok"] += sum(normalise(e) == normalise(a) for e, a in zip(expected, actual))
            stats["outputs"][case["id"]].add(tuple(normalise(a) for a in actual))
            stats["latencies"].append(out["latency_ms"])
            if out["cost_inr"] is None:
                stats["cost_known"] = False
            else:
                stats["cost"] += out["cost_inr"]
            for problem in mismatches(expected, actual):
                stats["failures"].append(f"run {run} · {case['id']}: {problem}")
    return stats


def main() -> None:
    parser = argparse.ArgumentParser(description="Evaluate the categorizer against a golden set")
    parser.add_argument("--models", default=DEFAULT_MODEL, help="comma-separated model IDs")
    parser.add_argument("--runs", type=int, default=3, help="repeat each case N times")
    parser.add_argument("--prompt", default="v3", help="prompt version in shared/prompts")
    parser.add_argument("--golden", type=Path, default=GOLDEN_DEFAULT)
    parser.add_argument("--min-accuracy", type=float, default=100.0,
                        help="exit 1 if any model scores below this (CI gate)")
    args = parser.parse_args()

    cases = json.loads(args.golden.read_text())
    models = [m.strip() for m in args.models.split(",") if m.strip()]
    calls = len(models) * len(cases) * args.runs
    print(f"🧪 {len(cases)} cases × {args.runs} runs × {len(models)} model(s) = {calls} calls "
          f"| prompt {args.prompt}\n")

    results = {}
    try:
        for model in models:
            print(f"▶ {model} …", flush=True)
            results[model] = run_model(model, cases, args.runs, args.prompt)
    except (UnauthorizedSSOTokenError, TokenRetrievalError, SSOTokenLoadError):
        raise SystemExit("🔑 SSO session expired. Run: aws sso login --use-device-code")

    # ---------------- summary table ----------------
    print(f"\n{'Model':<32} {'Accuracy':>14} {'Consistency':>13} {'Avg ms':>8} {'Cost ₹':>9}")
    print("-" * 80)
    gate_failed = False
    for model, s in results.items():
        acc = 100 * s["txn_ok"] / s["txn_total"] if s["txn_total"] else 0.0
        stable = sum(1 for outs in s["outputs"].values() if len(outs) == 1)
        cons = 100 * stable / len(cases)
        avg_ms = sum(s["latencies"]) / len(s["latencies"]) if s["latencies"] else 0
        cost = f"{s['cost']:.4f}" if s["cost_known"] else "n/a"
        print(f"{model:<32} {s['txn_ok']:>3}/{s['txn_total']:<3} {acc:5.1f}% "
              f"{stable:>3}/{len(cases):<2} {cons:5.1f}% {avg_ms:>8.0f} {cost:>9}")
        gate_failed |= acc < args.min_accuracy

    # ---------------- failure details ----------------
    for model, s in results.items():
        if s["failures"]:
            print(f"\n❌ {model}")
            for line in s["failures"][:10]:
                print(f"   {line}")
            if len(s["failures"]) > 10:
                print(f"   … {len(s['failures']) - 10} more")

    print("\n✅ GATE PASSED" if not gate_failed else f"\n🚫 GATE FAILED (min accuracy {args.min_accuracy}%)")
    sys.exit(1 if gate_failed else 0)


if __name__ == "__main__":
    main()
    