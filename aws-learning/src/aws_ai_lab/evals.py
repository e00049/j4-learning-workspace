"""AWS evals: the shared runner + the Bedrock adapter.

Run from ai-learning/aws-learning:
    uv run python -m aws_ai_lab.evals --runs 3 --models amazon.nova-micro-v1:0,amazon.nova-lite-v1:0
"""
from botocore.exceptions import SSOTokenLoadError, TokenRetrievalError, UnauthorizedSSOTokenError

from aws_ai_lab.categorizer import DEFAULT_MODEL, categorize
from j4_common.evals import run_cli


def main() -> None:
    run_cli(
        categorize,
        provider="aws",
        default_model=DEFAULT_MODEL,
        auth_errors=(UnauthorizedSSOTokenError, TokenRetrievalError, SSOTokenLoadError),
        auth_hint="🔑 SSO session expired. Run: aws sso login --use-device-code",
    )


if __name__ == "__main__":
    main()
