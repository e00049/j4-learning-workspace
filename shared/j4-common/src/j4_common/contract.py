"""The contract: what a valid categorizer answer MUST look like, on every cloud."""
from typing import Literal

from pydantic import BaseModel, model_validator

CONTRACT_VERSION = "2"   # bump whenever the fields or allowed values change

TxnType = Literal["expense", "refund", "transfer", "income"]
Category = Literal[
    "Food", "Transport", "Entertainment", "Health", "Shopping", "Bills",
    "Education", "Transfer", "Investment", "Income", "Cash", "Other",
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


def strip_fences(text: str) -> str:
    """Defensive: remove ```json ... ``` if a model adds markdown anyway."""
    text = text.strip()
    if text.startswith("```"):
        text = text.split("\n", 1)[1] if "\n" in text else ""
        text = text.rsplit("```", 1)[0]
    return text.strip()


# ---------------------------------------------------------------------------
# Single source of truth: build the prompt's schema line FROM this contract,
# so the prompt and the validator can never drift apart.
# ---------------------------------------------------------------------------
_TYPE_NAMES = {str: "string", float: "number", int: "number", bool: "boolean"}


def _field_type(annotation) -> str:
    from typing import get_args, get_origin

    if get_origin(annotation) is Literal:
        return '"' + "|".join(get_args(annotation)) + '"'
    return _TYPE_NAMES.get(annotation, "string")


def schema_from_contract() -> str:
    """Compact schema text, e.g. {"transactions":[{"merchant":string,...}]}"""
    fields = ",".join(
        f'"{name}":{_field_type(info.annotation)}' for name, info in Transaction.model_fields.items()
    )
    return '{"transactions":[{' + fields + "}]}"
