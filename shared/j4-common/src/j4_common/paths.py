"""Where the shared assets live, resolved from this file's location."""
from pathlib import Path

# .../ai-learning/shared/j4-common/src/j4_common/paths.py
SHARED_DIR = Path(__file__).resolve().parents[3]     # .../ai-learning/shared
REPO_ROOT = SHARED_DIR.parent                        # .../ai-learning
PROMPTS_DIR = SHARED_DIR / "prompts"
EVALS_DIR = SHARED_DIR / "evals"


def load_prompt(version: str) -> str:
    """Load a prompt file. Templates (v4+) contain {SCHEMA}, filled from the Pydantic contract."""
    text = (PROMPTS_DIR / f"categorizer-{version}.txt").read_text().strip()
    if "{SCHEMA}" in text:
        from j4_common.contract import schema_from_contract   # local import avoids a cycle
        text = text.replace("{SCHEMA}", schema_from_contract())
    return text
