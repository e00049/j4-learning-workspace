"""Azure evals: the shared runner + the Foundry adapter.

Run from ai-learning/azure-learning:
    uv run python -m azure_ai_lab.evals --runs 3 --models gpt-4.1-mini
"""
from azure.core.exceptions import ClientAuthenticationError
from azure.identity import CredentialUnavailableError
from openai import AuthenticationError, PermissionDeniedError

from azure_ai_lab.categorizer import DEFAULT_MODEL, categorize
from j4_common.evals import run_cli


def main() -> None:
    run_cli(
        categorize,
        provider="azure",
        default_model=DEFAULT_MODEL,
        auth_errors=(CredentialUnavailableError, ClientAuthenticationError,
                     AuthenticationError, PermissionDeniedError),
        auth_hint="🔑 Azure login/role problem. Run: az login --use-device-code (and check RBAC)",
    )


if __name__ == "__main__":
    main()
