"""Transaction categorizer on Amazon Bedrock (Phase 0, Step 5).

Run from ai-learning/aws-learning:
    uv run python -m aws_ai_lab.categorizer "Swiggy 450, UPI-RAMESH 500"
"""
from __future__ import annotations

import argparse
import os
import time
from functools import lru_cache
from pathlib import Path
from typing import Literal

import boto3
from botocore.exceptions import (
    ClientError,
    SSOTokenLoadError,
    TokenRetrievalError,
    UnauthorizedSSOTokenError,
)
from pydantic import BaseModel, ValidationError, model_validator

# ---------------------------------------------------------------------------
# Settings
# ---------------------------------------------------------------------------
REPO_ROOT = Path(__file__).resolve().parents[3]          # .../ai-learning
PROMPTS_DIR = REPO_ROOT / "shared" / "prompts"

DEFAULT_MODEL = "us.amazon.nova-lite-v1:0"
REGION = "us-east-1"
MAX_ATTEMPTS = 2

# Approximate on-demand prices, USD per 1M tokens (input, output).
# Verify on the Amazon Bedrock pricing page before trusting these numbers.
PRICES_USD_PER_M = {
    "us.amazon.nova-micro-v1:0": (0.035, 0.14),
    "us.amazon.nova-lite-v1:0": (0.06, 0.24),
    "us.amazon.nova-pro-v1:0": (0.80, 3.20),
}
USD_TO_INR = float(os.getenv("USD_TO_INR", "95.92"))  # override: export USD_TO_INR=96.5

# ---------------------------------------------------------------------------
# The contract: what a valid answer MUST look like
# ---------------------------------------------------------------------------
TxnType = Literal["expense", "refund", "transfer"]
Category = Literal[
    "Food", "Transport", "Entertainment", "Health",
    "Shopping", "Bills", "Transfer", "Other",
]


class Transaction(BaseModel):
    merchant: str
    amount: float
    type: TxnType
    category: Category

    @model_validator(mode="after")
    def tidy(self) -> "Transaction":
        # Rule-based clean-up belongs in code, not in the prompt.
        # Only person names are title-cased, so brands like BESCOM stay intact.
        if self.type == "transfer":
            self.merchant = self.merchant.title()      # RAMESH -> Ramesh
        return self


class CategorizeResult(BaseModel):
    transactions: list[Transaction]


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def load_prompt(version: str) -> str:
    return (PROMPTS_DIR / f"categorizer-{version}.txt").read_text().strip()


def strip_fences(text: str) -> str:
    """Defensive: remove ```json ... ``` if the model adds markdown anyway."""
    text = text.strip()
    if text.startswith("```"):
        text = text.split("\n", 1)[1] if "\n" in text else ""
        text = text.rsplit("```", 1)[0]
    return text.strip()


@lru_cache(maxsize=1)
def get_client():
    """Create the Bedrock client ONCE and reuse it (connection + credentials cached)."""
    return boto3.client("bedrock-runtime", region_name=REGION)


def estimate_cost_inr(model_id: str, tokens_in: int, tokens_out: int) -> float | None:
    price = PRICES_USD_PER_M.get(model_id)
    if price is None:
        return None
    usd = tokens_in / 1e6 * price[0] + tokens_out / 1e6 * price[1]
    return usd * USD_TO_INR


# ---------------------------------------------------------------------------
# Core: call Bedrock, validate, retry once if the output breaks the contract
# ---------------------------------------------------------------------------
def categorize(text: str, model_id: str = DEFAULT_MODEL, prompt_version: str = "v3") -> dict:
    client = get_client()
    system_prompt = load_prompt(prompt_version)
    total_in = total_out = 0
    last_error: Exception | None = None
    started = time.perf_counter()

    for attempt in range(1, MAX_ATTEMPTS + 1):
        response = client.converse(
            modelId=model_id,
            system=[{"text": system_prompt}],
            messages=[{"role": "user", "content": [{"text": text}]}],
            inferenceConfig={"maxTokens": 400, "temperature": 0},
        )
        total_in += response["usage"]["inputTokens"]
        total_out += response["usage"]["outputTokens"]
        raw = response["output"]["message"]["content"][0]["text"]

        try:
            result = CategorizeResult.model_validate_json(strip_fences(raw))
            break
        except ValidationError as err:
            last_error = err
            print(f"⚠️  attempt {attempt}: output broke the contract")
            print(f"    raw: {raw[:160]}")
    else:
        raise RuntimeError(
            f"Output failed validation after {MAX_ATTEMPTS} attempts:\n{last_error}"
        )

    return {
        "result": result,
        "attempts": attempt,
        "input_tokens": total_in,
        "output_tokens": total_out,
        "latency_ms": round((time.perf_counter() - started) * 1000),
        "cost_inr": estimate_cost_inr(model_id, total_in, total_out),
    }


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------
def main() -> None:
    parser = argparse.ArgumentParser(description="Categorize bank transactions with Bedrock")
    parser.add_argument("text", help='e.g. "Swiggy 450, Uber 230"')
    parser.add_argument("--model", default=DEFAULT_MODEL)
    parser.add_argument("--prompt", default="v3", help="prompt version in shared/prompts")
    args = parser.parse_args()

    try:
        out = categorize(args.text, args.model, args.prompt)
    except (UnauthorizedSSOTokenError, TokenRetrievalError, SSOTokenLoadError):
        raise SystemExit("🔑 SSO session expired. Run: aws sso login --use-device-code")
    except ClientError as err:
        raise SystemExit(f"❌ Bedrock error: {err.response['Error']['Message']}")
    except RuntimeError as err:
        raise SystemExit(f"❌ {err}")

    for txn in out["result"].transactions:
        print(f"{txn.merchant:<18} {txn.amount:>9.2f}  {txn.type:<9} {txn.category}")

    cost = f"₹{out['cost_inr']:.5f}" if out["cost_inr"] is not None else "n/a"
    print(
        f"\n📊 tokens in/out: {out['input_tokens']}/{out['output_tokens']} | "
        f"latency: {out['latency_ms']} ms | attempts: {out['attempts']} | cost: {cost}"
    )


if __name__ == "__main__":
    main()