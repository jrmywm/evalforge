"""Deterministic provider used by the offline example and tests."""

from __future__ import annotations

import re
from collections.abc import Mapping
from typing import Any

from evalforge.providers.base import NormalizedRequest, ProviderResponse


class MockProviderError(RuntimeError):
    """An intentional fixture failure from the deterministic mock provider."""

    error_type = "mock_provider_error"


class DeterministicMockProvider:
    """A small invoice extraction mock with optional fixture overrides.

    Fixtures are keyed by case ID and may contain any JSON output.  A case can
    be made to fail by adding its ID to ``fail_case_ids`` or by putting the
    marker ``[provider-error]`` in its input text.
    """

    name = "mock"
    _PROFILE_REGRESSIONS = frozenset({"invoice-002", "invoice-005", "invoice-019"})

    def __init__(
        self,
        model: str,
        *,
        fixtures: Mapping[str, Any] | None = None,
        fail_case_ids: set[str] | frozenset[str] | None = None,
    ) -> None:
        self.model = model
        self.fixtures = dict(fixtures or {})
        self.fail_case_ids = frozenset(fail_case_ids or ())

    def generate(self, request: NormalizedRequest) -> ProviderResponse:
        text = str(request.input.get("text", ""))
        if request.case_id in self.fail_case_ids or "[provider-error]" in text:
            raise MockProviderError(f"intentional mock failure for case {request.case_id}")

        if request.case_id in self.fixtures:
            output = self.fixtures[request.case_id]
        else:
            output = self._invoice_output(text)

        profile = request.inference_parameters.get("mock_profile")
        if profile == "invoice-regression" and request.configuration == "candidate":
            if request.case_id in self._PROFILE_REGRESSIONS:
                output = dict(output)
                output["total"] = float(output.get("total", 0.0)) + 1.0

        return ProviderResponse(
            output=output,
            raw_output=output,
            # Mock calls do not claim API usage or cost.
            usage=None,
            estimated_cost_usd=0.0,
        )

    @staticmethod
    def _invoice_output(text: str) -> dict[str, Any]:
        # Keep extraction rules explicit and deterministic while avoiding labels
        # such as ``Invoice Date`` being mistaken for identifiers.
        number_labels = {"date", "number", "total", "amount", "due", "currency"}
        number_patterns = (
            r"(?:invoice|facture|fatura)\s*(?:number|no\.?)?\s*(?:n[^A-Za-z0-9]*[oº°]?)?\s*[:#]?\s*"
            r"([\w][\w./-]*)",
            r"(?:reference|number)\s*[:#]\s*([\w][\w./-]*)",
        )
        number_candidates = [
            candidate
            for pattern in number_patterns
            for candidate in re.findall(pattern, text, flags=re.IGNORECASE)
            if candidate.casefold() not in number_labels
        ]
        invoice_number = number_candidates[-1] if number_candidates else ""

        currencies = {
            "R$": "BRL",
            "£": "GBP",
            "¥": "JPY",
            "€": "EUR",
            "$": "USD",
        }
        currencies.update({"\u00a3": "GBP", "\u00a5": "JPY", "\u20ac": "EUR"})
        currency = next((code for symbol, code in currencies.items() if symbol in text), None)
        if currency is None:
            known_currencies = {
                "AUD",
                "BRL",
                "CAD",
                "CHF",
                "EUR",
                "GBP",
                "JPY",
                "NZD",
                "SEK",
                "USD",
            }
            currency_candidates = re.findall(r"\b([A-Z]{3})\b", text)
            currency = next(
                (candidate for candidate in currency_candidates if candidate in known_currencies),
                "",
            )

        # Select the amount nearest the total-like label and normalize common
        # decimal/thousands separators.
        amount_matches = re.findall(
            r"(?:total(?:\s+payable|\s+due|\s+amount|\s+ttc)?|grand total|amount(?: due| payable)?|"
            r"balance due|valor total|gesamtbetrag|final total|\u5408\u8a08)"
            r"[^\d-]*(-?[\d][\d\s.,]*)",
            text,
            flags=re.IGNORECASE,
        )
        amount = amount_matches[-1].strip() if amount_matches else "0"
        amount = amount.replace(" ", "")
        if "," in amount and "." in amount:
            if amount.rfind(",") > amount.rfind("."):
                amount = amount.replace(".", "").replace(",", ".")
            else:
                amount = amount.replace(",", "")
        elif "," in amount:
            amount = (
                amount.replace(",", "")
                if len(amount.rsplit(",", 1)[1]) == 3
                else amount.replace(",", ".")
            )
        try:
            total = float(amount)
        except ValueError:
            total = 0.0
        return {"invoice_number": invoice_number, "currency": currency, "total": total}


def mock_provider_for(model: str) -> DeterministicMockProvider:
    """Construct the default deterministic provider for a model identity."""
    return DeterministicMockProvider(model)


# Short public name for callers that do not need to distinguish mock behavior
# from future provider implementations.
MockProvider = DeterministicMockProvider
