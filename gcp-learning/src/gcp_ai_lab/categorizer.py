"""GCP adapter: Vertex AI (Gemini, google-genai SDK, ADC auth) for the shared j4 categorizer.

Run from ai-learning/gcp-learning:
    uv run python -m gcp_ai_lab.categorizer "Swiggy 450, UPI-RAMESH 500"
"""
from __future__ import annotations

import argparse
import os
from functools import lru_cache

from google import genai
from google.auth.exceptions import DefaultCredentialsError, RefreshError
from google.genai import errors, types

from j4_common import (
    REPO_ROOT, ContractError, ModelReply, categorize_with, print_result, response_json_schema,
)

__all__ = ["DEFAULT_MODEL", "REPO_ROOT", "categorize"]

PROJECT = os.getenv("GOOGLE_CLOUD_PROJECT", "")
LOCATION = os.getenv("GOOGLE_CLOUD_LOCATION", "us-east4")   # regional endpoint, not "global"
DEFAULT_MODEL = "gemini-2.5-flash-lite"

# Billing labels on every request -> filter AI spend inside the shared project.
LABELS = {"project": "j4", "purpose": "ai-learning"}

# Approximate prices, USD per 1M tokens (input, output). Verify on the Vertex AI pricing page.
PRICES_USD_PER_M = {
    "gemini-2.5-flash-lite": (0.10, 0.40),
    "gemini-2.5-flash": (0.30, 2.50),
}


@lru_cache(maxsize=1)
def get_client() -> genai.Client:
    """Keyless client: Application Default Credentials (gcloud ADC here, workload identity on GKE later)."""
    if not PROJECT:
        raise RuntimeError("GOOGLE_CLOUD_PROJECT is not set (export it or source ~/.bashrc)")
    return genai.Client(vertexai=True, project=PROJECT, location=LOCATION)


def vertex_call(model: str, system_prompt: str, user_text: str) -> ModelReply:
    """The ONLY GCP-specific part: send one request to Gemini on Vertex AI."""
    response = get_client().models.generate_content(
        model=model,
        contents=user_text,
        config=types.GenerateContentConfig(
            system_instruction=system_prompt,
            temperature=0,
            max_output_tokens=1000,
            # Structured output: Gemini must return JSON matching this schema (generated from Pydantic).
            response_mime_type="application/json",
            response_json_schema=response_json_schema(),
            # 2.5 models can "think" before answering; thinking tokens are billed as output.
            # Turn it off so the comparison with Nova / gpt-4.1-mini is fair.
            thinking_config=types.ThinkingConfig(thinking_budget=0),
            labels=LABELS,
            automatic_function_calling=types.AutomaticFunctionCallingConfig(disable=True),
        ),
    )
    usage = response.usage_metadata
    output_tokens = (usage.candidates_token_count or 0) + (usage.thoughts_token_count or 0)
    return ModelReply(
        text=response.text or "",
        input_tokens=usage.prompt_token_count or 0,
        output_tokens=output_tokens,
    )


def categorize(text: str, model_id: str = DEFAULT_MODEL, prompt_version: str = "v3") -> dict:
    return categorize_with(vertex_call, model_id, text, prompt_version, PRICES_USD_PER_M)


def main() -> None:
    parser = argparse.ArgumentParser(description="Categorize bank transactions with Gemini on Vertex AI")
    parser.add_argument("text", help='e.g. "Swiggy 450, Uber 230"')
    parser.add_argument("--model", default=DEFAULT_MODEL)
    parser.add_argument("--prompt", default="v3", help="prompt version in shared/prompts")
    args = parser.parse_args()

    try:
        out = categorize(args.text, args.model, args.prompt)
    except (DefaultCredentialsError, RefreshError):
        raise SystemExit("🔑 No valid ADC. Run: gcloud auth application-default login --no-launch-browser")
    except errors.ClientError as err:
        hints = {403: "check Owner / roles/aiplatform.user on the project",
                 404: f"model '{args.model}' not available in {LOCATION}?"}
        raise SystemExit(f"❌ Vertex AI {err.code}: {hints.get(err.code, err.message)}")
    except errors.APIError as err:
        raise SystemExit(f"❌ Vertex AI error: {err}")
    except (ContractError, RuntimeError) as err:
        raise SystemExit(f"❌ {err}")
    print_result(out)


if __name__ == "__main__":
    main()
