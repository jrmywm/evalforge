# Portfolio benchmark: the better average that should not ship

## Decision

EvalForge blocks the candidate even though it improves aggregate field accuracy
from `0.90` to `0.967` and increases fully passing cases from 14/20 to 18/20.
The candidate newly fails two cases that the baseline handled correctly, so the
configured `new_failure_count.maximum: 0` policy rejects it.

This deterministic scenario demonstrates the release decision and evidence
workflow. It is not a measured claim about a real model.

## Why the decision matters

An average-only policy would approve this candidate: schema validity remains
perfect, field accuracy rises by 0.067, and six former failures are fixed. A
case-transition policy reveals the hidden cost:

- `invoice-adv-019` contains instruction-like text embedded in an invoice;
- `invoice-adv-020` contains draft and finalized values where the final total is
  authoritative.

Both cases are tagged `critical`. The report retains their inputs, expected and
actual values, field-level mismatches, and the complete gate reason.

## Reproduce it

```bash
uv run evalforge run examples/invoice/portfolio.yaml \
  --artifact-root artifacts \
  --run-id portfolio-tradeoff
```

The expected exit status is `1`. Inspect
`artifacts/portfolio-tradeoff/report.md`, or start the API and dashboard to walk
from the release decision to each failed field. Offline replay verifies the
decision without invoking a provider:

```bash
uv run evalforge replay portfolio-tradeoff
```

## Dataset coverage

The 20-case versioned fixture includes OCR noise, localized decimal and thousands
separators, negative credits, duplicate identifiers, distracting monetary values,
zero balances, Unicode identifiers, ambiguous dates, embedded instruction text,
and draft-versus-final values. The mock profile creates stable model behavior so
the regression policy can be tested in CI without credentials or network access.

## Demo narrative

1. Start with the candidate's improved 18/20 pass count and `0.967` accuracy.
2. Show that all aggregate quality thresholds pass.
3. Reveal the failed `new_failure_count` gate and its observed value of `2`.
4. Open `invoice-adv-019` and `invoice-adv-020` to inspect the exact total-field
   mismatches.
5. Replay the stored run to show that the decision derives from immutable
   evidence rather than another model call.
6. Run `examples/invoice/portfolio-fixed.yaml` to show the corrected candidate
   passing 20/20 cases with zero newly failing cases under the same policy.
