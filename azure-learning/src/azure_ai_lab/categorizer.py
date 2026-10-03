"""Azure adapter: Microsoft Foundry (Azure OpenAI v1 API, Entra ID auth) for the shared j4 categorizer.

Run from ai-learning/azure-learning:
    uv run python -m azure_ai_lab.categorizer "Swiggy 450, UPI-RAMESH 500"
"""
from __future__ import annotations

import argparse
import os
from functools import lru_cache

from azure.core.exceptions import ClientAuthenticationError
from azure.identity import CredentialUnavailableError, DefaultAzureCredential, get_bearer_token_provider
from openai import APIError, AuthenticationError, NotFoundError, OpenAI, PermissionDeniedError

from j4_common import (
    REPO_ROOT, ContractError, ModelReply, categorize_with, print_result, response_json_schema,
)

__all__ = ["DEFAULT_MODEL", "REPO_ROOT", "categorize"]

# Use the custom-domain endpoint the CLI reports (the one with -sid), not the portal sticker.
ENDPOINT = os.getenv(
    "AZURE_OPENAI_ENDPOINT", "https://aif-j4-ai-learning-sid.openai.azure.com/openai/v1/"
)
TOKEN_SCOPE = "https://cognitiveservices.azure.com/.default"
DEFAULT_MODEL = "gpt-4.1-mini"  # = the DEPLOYMENT name (Standard, eastus2)

# Approximate prices, USD per 1M tokens (input, output). Regional Standard can differ
# from Global - verify on the Azure OpenAI pricing page.
PRICES_USD_PER_M = {
    "gpt-4.1-mini": (0.40, 1.60),
}


@lru_cache(maxsize=1)
def get_client() -> OpenAI:
    """Keyless client: Entra ID token (from `az login` here, managed identity on AKS later)."""
    token_provider = get_bearer_token_provider(DefaultAzureCredential(), TOKEN_SCOPE)
    return OpenAI(base_url=ENDPOINT, api_key=token_provider)


def azure_call(model: str, system_prompt: str, user_text: str) -> ModelReply:
    """The ONLY Azure-specific part: send one request to the deployment."""
    response = get_client().chat.completions.create(
        model=model,
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_text},
        ],
        temperature=0,
        max_tokens=1000,
        # Structured output: the service enforces this JSON schema (generated from Pydantic).
        response_format={
            "type": "json_schema",
            "json_schema": {"name": "categorize_result", "strict": True, "schema": response_json_schema()},
        },
    )
    return ModelReply(
        text=response.choices[0].message.content or "",
        input_tokens=response.usage.prompt_tokens,
        output_tokens=response.usage.completion_tokens,
    )


def categorize(text: str, model_id: str = DEFAULT_MODEL, prompt_version: str = "v3") -> dict:
    return categorize_with(azure_call, model_id, text, prompt_version, PRICES_USD_PER_M)


def main() -> None:
    parser = argparse.ArgumentParser(description="Categorize bank transactions with Microsoft Foundry")
    parser.add_argument("text", help='e.g. "Swiggy 450, Uber 230"')
    parser.add_argument("--model", default=DEFAULT_MODEL, help="Azure deployment name")
    parser.add_argument("--prompt", default="v3", help="prompt version in shared/prompts")
    args = parser.parse_args()

    try:
        out = categorize(args.text, args.model, args.prompt)
    except (CredentialUnavailableError, ClientAuthenticationError):
        raise SystemExit("🔑 No Azure login found. Run: az login --use-device-code")
    except (AuthenticationError, PermissionDeniedError) as err:
        raise SystemExit(f"🚫 Access denied ({err.status_code}). Check the "
                         "'Cognitive Services OpenAI User' role on the resource.")
    except NotFoundError:
        raise SystemExit(f"❓ Deployment '{args.model}' not found. "
                         "List them: az cognitiveservices account deployment list ...")
    except APIError as err:
        raise SystemExit(f"❌ Azure OpenAI error: {err}")
    except ContractError as err:
        raise SystemExit(f"❌ {err}")
    print_result(out)


if __name__ == "__main__":
    main()
