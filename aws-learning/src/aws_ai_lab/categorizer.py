"""AWS adapter: Amazon Bedrock (Converse API) for the shared j4 categorizer.

Run from ai-learning/aws-learning:
    uv run python -m aws_ai_lab.categorizer "Swiggy 450, UPI-RAMESH 500"
"""
from __future__ import annotations

import argparse
import json
from functools import lru_cache

import boto3
from botocore.exceptions import (
    ClientError,
    SSOTokenLoadError,
    TokenRetrievalError,
    UnauthorizedSSOTokenError,
)

from j4_common import (
    REPO_ROOT, ContractError, ModelReply, categorize_with, print_result, response_json_schema,
)

__all__ = ["DEFAULT_MODEL", "REPO_ROOT", "categorize"]   # REPO_ROOT kept for evals.py

REGION = "us-east-1"
DEFAULT_MODEL = "amazon.nova-micro-v1:0"  # in-region us-east-1; eval winner

# Approximate on-demand prices, USD per 1M tokens (input, output). Verify on the pricing page.
PRICES_USD_PER_M = {
    "amazon.nova-micro-v1:0": (0.035, 0.14),
    "amazon.nova-lite-v1:0": (0.06, 0.24),
    "amazon.nova-pro-v1:0": (0.80, 3.20),
}


@lru_cache(maxsize=1)
def get_client():
    """Create the Bedrock client ONCE and reuse it (connection + credentials cached)."""
    return boto3.client("bedrock-runtime", region_name=REGION)


TOOL_NAME = "record_transactions"
TOOL_CONFIG_BASE = {
    "tools": [{
        "toolSpec": {
            "name": TOOL_NAME,
            "description": "Record the categorized transactions, one item per input line, in order.",
            "inputSchema": {"json": response_json_schema()},   # generated from the Pydantic contract
        }
    }]
}


def bedrock_call(model: str, system_prompt: str, user_text: str) -> ModelReply:
    """The ONLY AWS-specific part. Structured output on Bedrock = a FORCED tool call:
    the model must fill the tool's JSON schema instead of writing free text."""
    request = dict(
        modelId=model,
        system=[{"text": system_prompt}],
        messages=[{"role": "user", "content": [{"text": user_text}]}],
        inferenceConfig={"maxTokens": 1000, "temperature": 0},
    )
    try:
        response = get_client().converse(
            **request, toolConfig={**TOOL_CONFIG_BASE, "toolChoice": {"tool": {"name": TOOL_NAME}}})
    except ClientError as err:
        if "toolChoice" not in str(err):
            raise
        # Some models only support "any tool" - with a single tool that is equivalent.
        response = get_client().converse(**request, toolConfig={**TOOL_CONFIG_BASE, "toolChoice": {"any": {}}})

    blocks = response["output"]["message"]["content"]
    tool_inputs = [b["toolUse"]["input"] for b in blocks if "toolUse" in b]
    text = json.dumps(tool_inputs[0]) if tool_inputs else "".join(b.get("text", "") for b in blocks)
    return ModelReply(
        text=text,
        input_tokens=response["usage"]["inputTokens"],
        output_tokens=response["usage"]["outputTokens"],
    )


def categorize(text: str, model_id: str = DEFAULT_MODEL, prompt_version: str = "v3") -> dict:
    return categorize_with(bedrock_call, model_id, text, prompt_version, PRICES_USD_PER_M)


def main() -> None:
    parser = argparse.ArgumentParser(description="Categorize bank transactions with Amazon Bedrock")
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
    except ContractError as err:
        raise SystemExit(f"❌ {err}")
    print_result(out)


if __name__ == "__main__":
    main()
