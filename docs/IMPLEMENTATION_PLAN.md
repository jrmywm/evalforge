# EvalForge Implementation Plan

## Status

- Milestone 0 — complete on 2026-08-28.
- Milestone 1 — complete on 2026-08-28.
- Milestone 2 — next.

## Working method

Build in small checkpoints. Every milestone ends with a runnable behavior and
tests. Do not begin the next milestone while the current verification checkpoint
is failing.

## Milestone 0 — Repository foundation

### Tasks

- Initialize Git and add an appropriate Python `.gitignore`.
- Create the `uv` project and `src` package layout.
- Configure Python 3.13, Ruff, and pytest.
- Add CLI entry point with `evalforge --help` and `evalforge --version`.
- Add a GitHub Actions workflow for lint and tests.
- Document setup and test commands.

### Verification checkpoint

```bash
uv sync
uv run evalforge --help
uv run ruff check .
uv run pytest
```

All commands must succeed on a clean local checkout.

## Milestone 1 — Configuration and dataset contracts

### Tasks

- Define strict Pydantic models for experiment configuration and test cases.
- Implement YAML manifest loading with paths resolved relative to the manifest.
- Implement JSON Lines dataset loading.
- Validate stable unique case IDs and required expected fields.
- Calculate dataset and configuration content digests.
- Create the initial 20-case invoice dataset.
- Add clear error messages for invalid manifests and records.

### Verification checkpoint

- A valid example loads and prints a concise dry-run summary.
- Unknown manifest fields fail validation.
- Duplicate case IDs fail validation.
- Invalid JSON Lines reports the record location.
- Relative paths behave independently of the caller's working directory.

## Milestone 2 — Provider boundary and generation artifacts

### Tasks

- Define the provider protocol around normalized requests and responses.
- Implement deterministic baseline and candidate mock behavior.
- Capture latency, usage metadata, status, and structured errors.
- Implement the experiment execution loop.
- Write manifest, dataset, and generation snapshots.
- Ensure one provider failure does not abort remaining cases.

### Verification checkpoint

- Both configurations execute against every case.
- Repeated runs yield equivalent mock outputs.
- An intentionally failing fixture creates a provider-error record.
- Generated artifacts can be parsed back into domain models.

## Milestone 3 — Deterministic evaluators

### Tasks

- Define the evaluator protocol and version identity.
- Implement JSON parsing and schema validation.
- Implement field-level accuracy with structured mismatches.
- Define treatment of missing values, optional fields, and numeric comparisons.
- Persist evaluation results independently of generations.

### Verification checkpoint

- Unit tests cover valid, malformed, missing, extra, and mistyped fields.
- Evaluating stored generations performs no provider calls.
- Evaluator failures are distinguishable from failed evaluations.

## Milestone 4 — Aggregation, regression, and quality gates

### Tasks

- Aggregate per-case results into configuration summaries.
- Calculate median and P95 latency using a documented method.
- Compare candidate with baseline.
- Identify newly failing and newly passing cases.
- Implement absolute minimum, absolute maximum, and maximum-regression gates.
- Collect every gate failure rather than stopping at the first.

### Verification checkpoint

- Tests cover boundary values and empty/error populations.
- A known candidate passes the configured policy.
- A known regressing candidate fails for the expected reasons.
- Gate outcomes are stable across repeated runs.

## Milestone 5 — Reports and CLI contract

### Tasks

- Write the full structured `experiment.json` report.
- Write a readable Markdown comparison report.
- Include failed cases, expected values, actual values, and mismatch reasons.
- Implement the documented exit codes `0`, `1`, and `2`.
- Add concise console output pointing to generated artifacts.
- Add an end-to-end test that invokes the CLI.

### Verification checkpoint

- Passing example returns `0`.
- Failing quality gate returns `1` and still writes a complete report.
- Invalid input returns `2` without a misleading experiment decision.
- JSON and Markdown reports agree because both use the same result model.

## Milestone 6 — Portfolio polish

### Tasks

- Replace illustrative README output with a real generated report.
- Add an architecture diagram and a short explanation of design tradeoffs.
- Document how to add a provider and evaluator.
- Record a short demo using both pass and fail scenarios.
- Review installation from a clean environment.
- Tag the CLI MVP release.

### Verification checkpoint

A reviewer unfamiliar with the repository can install it, run the demo, explain
the decision, and find the failing cases without assistance.

## Implementation rules

- Do not add an HTTP API during these milestones.
- Do not add persistence beyond portable filesystem artifacts.
- Do not add a live model provider before the mock workflow is complete.
- Do not create abstractions without at least two concrete needs or a clear test
  seam.
- Keep business logic callable without invoking Typer.
- Treat error taxonomy and report semantics as product behavior, not incidental
  implementation details.

## First build session

The first session should complete Milestone 0 and begin only the configuration
models from Milestone 1. Its deliverable is a healthy repository foundation, not
a partially implemented evaluation engine.
