"""Display text derived from validated claims, never from model-authored prose.

The evaluator calls this only after every applicable check passes. This is an
output boundary, not a natural-language semantic judge.
"""

from decimal import Decimal

from .schemas import Case, Response


def render_answer(case: Case, response: Response) -> str:
    subject = f"Apple FY{case.target_fiscal_year} {case.target_metric.replace('_', ' ')}"
    if response.status == "insufficient_evidence":
        return f"Insufficient evidence for {subject} in the supplied packet."
    assert response.value is not None and response.period is not None
    number = format(Decimal(str(response.value)).normalize(), "f")
    unit = {"USD_millions": "USD millions", "USD_billions": "USD billions", "percent": "percent"}[response.unit]
    period = response.period
    return f"{subject}: {number} {unit} (fiscal period {period.start} to {period.end})."
