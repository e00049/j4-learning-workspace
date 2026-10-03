"""Cloud-neutral eval runner (A9).

Scores any cloud's categorize() against the golden answer key, prints a scorecard,
and saves a results file to shared/evals/results/ so j4_common.report can merge clouds.
Each cloud project wraps this in a 10-line evals.py that passes its own adapter.
"""
from __future__ import annotations

import argparse
import json
import re
import statistics
import sys
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable

from j4_common.contract import CONTRACT_VERSION
from j4_common.paths import EVALS_DIR
from j4_common.runner import ContractError

GOLDEN_DEFAULT = EVALS_DIR / "categorizer-golden-v1.json"
RESULTS_DIR = EVALS_DIR / "results"
FIELDS = ("merchant", "amount", "type", "category")


def _merchants(value) -> list[str]:
    """Golden merchants may list several acceptable spellings (messy statement lines)."""
    names = value if isinstance(value, list) else [value]
    return [n.strip().lower() for n in names]


def field_problems(exp: dict, act: dict) -> list[tuple[str, object, object]]:
    """(field, expected, got) for every field that does not match.
    merchant: case-insensitive, any listed alias is fine. amount: within 1 paisa.
    type / category: strict - these drive the business numbers."""
    problems = []
    if act["merchant"].strip().lower() not in _merchants(exp["merchant"]):
        problems.append(("merchant", exp["merchant"], act["merchant"]))
    if abs(float(exp["amount"]) - float(act["amount"])) > 0.01:
        problems.append(("amount", float(exp["amount"]), float(act["amount"])))
    for field in ("type", "category"):
        if exp[field] != act[field]:
            problems.append((field, exp[field], act[field]))
    return problems


def normalise(txn: dict) -> tuple:
    """Fingerprint of a model answer, used for the consistency check."""
    return (txn["merchant"].strip().lower(), round(float(txn["amount"]), 2), txn["type"], txn["category"])


def mismatches(expected: list[dict], actual: list[dict]) -> list[str]:
    problems = []
    if len(expected) != len(actual):
        problems.append(f"expected {len(expected)} transactions, got {len(actual)}")
    for i, (exp, act) in enumerate(zip(expected, actual), start=1):
        for field, e, a in field_problems(exp, act):
            problems.append(f"txn {i} {field}: expected {e!r}, got {a!r}")
    return problems


def run_model(categorize_fn: Callable, model: str, cases: list[dict], runs: int, prompt: str) -> dict:
    s = {"txn_total": 0, "txn_ok": 0, "calls": 0, "cost": 0.0, "cost_known": True,
         "latencies": [], "failures": [], "outputs": defaultdict(set),
         "field_errors": {f: 0 for f in FIELDS}, "amount_fixes": 0, "retries": 0}
    for run in range(1, runs + 1):
        for case in cases:
            expected = case["expected"]
            s["txn_total"] += len(expected)
            s["calls"] += 1
            try:
                out = categorize_fn(case["input"], model, prompt)
            except ContractError:
                s["failures"].append(f"run {run} · {case['id']}: invalid output (contract)")
                s["outputs"][case["id"]].add("INVALID")
                continue
            s["amount_fixes"] += out.get("amount_fixes", 0)
            s["retries"] += out["attempts"] - 1
            actual = [t.model_dump() for t in out["result"].transactions]
            for e, a in zip(expected, actual):
                problems = field_problems(e, a)
                s["txn_ok"] += not problems
                for field, _, _ in problems:
                    s["field_errors"][field] += 1
            s["outputs"][case["id"]].add(tuple(normalise(a) for a in actual))
            s["latencies"].append(out["latency_ms"])
            if out["cost_inr"] is None:
                s["cost_known"] = False
            else:
                s["cost"] += out["cost_inr"]
            s["failures"] += [f"run {run} · {case['id']}: {p}" for p in mismatches(expected, actual)]
    return s


def summarise(provider: str, model: str, s: dict, n_cases: int, args) -> dict:
    lat = s["latencies"]
    return {
        "provider": provider,
        "model": model,
        "prompt": args.prompt,
        "contract": CONTRACT_VERSION,
        "golden": args.golden.name,
        "runs": args.runs,
        "cases": n_cases,
        "calls": s["calls"],
        "txn_ok": s["txn_ok"],
        "txn_total": s["txn_total"],
        "accuracy": round(100 * s["txn_ok"] / s["txn_total"], 1) if s["txn_total"] else 0.0,
        "stable_cases": sum(1 for o in s["outputs"].values() if len(o) == 1),
        "consistency": round(100 * sum(1 for o in s["outputs"].values() if len(o) == 1) / n_cases, 1),
        "avg_ms": round(statistics.mean(lat)) if lat else None,
        "p50_ms": round(statistics.median(lat)) if lat else None,
        "max_ms": max(lat) if lat else None,
        "cost_inr_total": round(s["cost"], 6) if s["cost_known"] else None,
        "cost_inr_per_call": round(s["cost"] / s["calls"], 8) if s["cost_known"] and s["calls"] else None,
        "field_errors": s["field_errors"],
        "amount_fixes": s["amount_fixes"],
        "retries": s["retries"],
        "failures": s["failures"][:20],
        "timestamp": datetime.now(timezone.utc).isoformat(timespec="seconds"),
    }


def save(summary: dict) -> Path:
    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    safe_model = re.sub(r"[^A-Za-z0-9.-]+", "-", summary["model"])
    path = RESULTS_DIR / f"{summary['provider']}__{safe_model}.json"
    path.write_text(json.dumps(summary, indent=2) + "\n")
    return path


def run_cli(
    categorize_fn: Callable,
    provider: str,
    default_model: str,
    auth_errors: tuple = (),
    auth_hint: str = "🔑 Login expired.",
) -> None:
    parser = argparse.ArgumentParser(description=f"Evaluate the {provider} categorizer against the golden set")
    parser.add_argument("--models", default=default_model, help="comma-separated model IDs / deployment names")
    parser.add_argument("--runs", type=int, default=3, help="repeat each case N times")
    parser.add_argument("--prompt", default="v3", help="prompt version in shared/prompts")
    parser.add_argument("--golden", type=Path, default=GOLDEN_DEFAULT)
    parser.add_argument("--min-accuracy", type=float, default=100.0, help="exit 1 below this (CI gate)")
    parser.add_argument("--no-save", action="store_true", help="don't write shared/evals/results/")
    args = parser.parse_args()

    cases = json.loads(args.golden.read_text())
    models = [m.strip() for m in args.models.split(",") if m.strip()]
    print(f"🧪 [{provider}] {len(cases)} cases × {args.runs} runs × {len(models)} model(s) "
          f"= {len(cases) * args.runs * len(models)} calls | prompt {args.prompt}\n")

    summaries = []
    try:
        for model in models:
            print(f"▶ {model} …", flush=True)
            stats = run_model(categorize_fn, model, cases, args.runs, args.prompt)
            summaries.append(summarise(provider, model, stats, len(cases), args))
    except auth_errors:
        raise SystemExit(auth_hint)

    print(f"\n{'Model':<28} {'Accuracy':>15} {'Consistency':>13} {'Avg ms':>7} {'P50 ms':>7} {'₹/1K calls':>11}")
    print("-" * 86)
    gate_failed = False
    for r in summaries:
        per_k = f"{r['cost_inr_per_call'] * 1000:.2f}" if r["cost_inr_per_call"] is not None else "n/a"
        print(f"{r['model']:<28} {r['txn_ok']:>3}/{r['txn_total']:<3} {r['accuracy']:5.1f}% "
              f"{r['stable_cases']:>3}/{r['cases']:<2} {r['consistency']:5.1f}% "
              f"{r['avg_ms'] or 0:>7} {r['p50_ms'] or 0:>7} {per_k:>11}")
        gate_failed |= r["accuracy"] < args.min_accuracy

    for r in summaries:
        print(f"\n🛡️  {r['model']}: retries={r['retries']}, amounts corrected by code={r['amount_fixes']}")
    for r in summaries:
        errs = {f: n for f, n in r["field_errors"].items() if n}
        if errs:
            print(f"\n🔎 {r['model']} errors by field: " + ", ".join(f"{f}={n}" for f, n in errs.items()))
    for r in summaries:
        if r["failures"]:
            print(f"\n❌ {r['model']}")
            for line in r["failures"][:10]:
                print(f"   {line}")

    if not args.no_save:
        print()
        for r in summaries:
            print(f"💾 saved {save(r).relative_to(EVALS_DIR.parent.parent)}")

    print("\n✅ GATE PASSED" if not gate_failed else f"\n🚫 GATE FAILED (min accuracy {args.min_accuracy}%)")
    sys.exit(1 if gate_failed else 0)
