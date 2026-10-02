"""GCP evals: the shared runner + the Vertex AI adapter.

Run from ai-learning/gcp-learning:
    uv run python -m gcp_ai_lab.evals --runs 3 --models gemini-2.5-flash-lite,gemini-2.5-flash
"""
from google.auth.exceptions import DefaultCredentialsError, RefreshError

from gcp_ai_lab.categorizer import DEFAULT_MODEL, categorize
from j4_common.evals import run_cli


def main() -> None:
    run_cli(
        categorize,
        provider="gcp",
        default_model=DEFAULT_MODEL,
        auth_errors=(DefaultCredentialsError, RefreshError),
        auth_hint="🔑 No valid ADC. Run: gcloud auth application-default login --no-launch-browser",
    )


if __name__ == "__main__":
    main()
