"""Cloud-neutral flow: call model -> validate against the contract -> retry WITH feedback."""
from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Callable

from pydantic import ValidationError

from j4_common.amounts import enforce_amounts
from j4_common.contract import CategorizeResult, strip_fences
from j4_common.cost import estimate_cost_inr
from j4_common.paths import load_prompt


@dataclass
class ModelReply:
    text: str
    input_tokens: int
    output_tokens: int


# Every cloud adapter provides one of these: (model, system_prompt, user_text) -> ModelReply
CallFn = Callable[[str, str, str], ModelReply]


class ContractError(RuntimeError):
    """The model's output broke the contract on every attempt."""


def categorize_with(
    call: CallFn,
    model: str,
    text: str,
    prompt_version: str = "v3",
    prices_usd_per_m: dict | None = None,
    max_attempts: int = 2,
) -> dict:
    system_prompt = load_prompt(prompt_version)
    user_text = text
    total_in = total_out = 0
    last_error: Exception | None = None
    started = time.perf_counter()

    for attempt in range(1, max_attempts + 1):
        reply = call(model, system_prompt, user_text)
        total_in += reply.input_tokens
        total_out += reply.output_tokens
        try:
            result = CategorizeResult.model_validate_json(strip_fences(reply.text))
            break
        except ValidationError as err:
            last_error = err
            print(f"⚠️  attempt {attempt}: output broke the contract")
            print(f"    raw: {reply.text[:160]}")
            # Retry WITH feedback: tell the model exactly what was wrong (a blind retry
            # at temperature 0 usually repeats the same mistake).
            problems = "; ".join(
                f"{'.'.join(str(p) for p in e['loc'])}: {e['msg']}" for e in err.errors()[:5]
            )
            user_text = (
                f"{text}\n\nYour previous answer was invalid ({problems}). "
                "Return ONLY JSON that matches the schema exactly."
            )
    else:
        raise ContractError(f"Output failed validation after {max_attempts} attempts:\n{last_error}")

    amount_fixes = enforce_amounts(text, result)   # code wins for numbers

    return {
        "result": result,
        "attempts": attempt,
        "amount_fixes": amount_fixes,
        "input_tokens": total_in,
        "output_tokens": total_out,
        "latency_ms": round((time.perf_counter() - started) * 1000),
        "cost_inr": estimate_cost_inr(prices_usd_per_m or {}, model, total_in, total_out),
    }


def print_result(out: dict) -> None:
    for txn in out["result"].transactions:
        print(f"{txn.merchant:<18} {txn.amount:>9.2f}  {txn.type:<9} {txn.category}")
    cost = f"₹{out['cost_inr']:.5f}" if out["cost_inr"] is not None else "n/a"
    print(
        f"\n📊 tokens in/out: {out['input_tokens']}/{out['output_tokens']} | "
        f"latency: {out['latency_ms']} ms | attempts: {out['attempts']} | cost: {cost}"
    )
    if out.get("amount_fixes"):
        print(f"🔢 code corrected {out['amount_fixes']} amount(s) the model got wrong")
