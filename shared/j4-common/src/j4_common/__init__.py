"""j4_common: everything that is the SAME on every cloud.

Cloud adapters (aws_ai_lab, azure_ai_lab, gcp_ai_lab) only implement one thing:
a function that sends (system prompt, user text) to their model and returns a ModelReply.
"""
from j4_common.amounts import enforce_amounts, parse_amount
from j4_common.contract import (
    CONTRACT_VERSION, CategorizeResult, Transaction, response_json_schema, strip_fences,
)
from j4_common.cost import USD_TO_INR, estimate_cost_inr
from j4_common.paths import EVALS_DIR, PROMPTS_DIR, REPO_ROOT, SHARED_DIR, load_prompt
from j4_common.runner import ContractError, ModelReply, categorize_with, print_result

__all__ = [
    "enforce_amounts", "parse_amount",
    "CONTRACT_VERSION", "CategorizeResult", "Transaction", "response_json_schema", "strip_fences",
    "USD_TO_INR", "estimate_cost_inr",
    "EVALS_DIR", "PROMPTS_DIR", "REPO_ROOT", "SHARED_DIR", "load_prompt",
    "ContractError", "ModelReply", "categorize_with", "print_result",
]
