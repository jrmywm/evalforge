# EvalForge

EvalForge is a local-first evaluation tool for deciding whether a proposed LLM
configuration is better than a baseline without violating quality, latency, or
cost constraints.

The first release is intentionally narrow: it evaluates structured invoice
extraction from the command line using deterministic mock providers. The goal is
to prove the experiment, evaluation, regression, and quality-gate workflow before
adding infrastructure.

## Product promise

Given a versioned dataset, a baseline configuration, and a candidate
configuration, EvalForge produces a reproducible answer to:

> Should this candidate replace the baseline?

The answer includes aggregate metrics, regressions, a deployment decision, and
the individual cases responsible for failures.

## First demonstration

Run the passing fixture:

```bash
uv run evalforge run examples/invoice/pass.yaml
```

The deterministic mock demo prints concise artifact locations:

```text
Decision: PASS
Experiment: invoice-extraction-pass
JSON report: .../artifacts/<run-id>/experiment.json
Markdown report: .../artifacts/<run-id>/report.md
```

To demonstrate a blocked candidate, run the expected-failure fixture. It exits
with status `1` after writing complete reports:

```bash
uv run evalforge run examples/invoice/regression.yaml
```

The Markdown report includes the comparison table, every gate rule and reason,
newly failing cases, and field-level mismatch details.

### Local OpenAI-compatible inference

The provider-ready local fixture targets a llama.cpp-compatible server. It does
not download a runtime or model, and no real quality result is claimed until a
benchmark is captured:

```bash
llama-server -m /path/to/model.gguf --host 127.0.0.1 --port 8080
uv run evalforge run examples/invoice/local-openai.yaml --run-id local-demo
```

See [local benchmark capture](docs/LOCAL_BENCHMARK.md) for the reproducibility
fields and limitations to record. The local provider reads an optional API key
from an environment variable named in the manifest; the key itself is never
stored in manifests, reports, or error details.

Representative passing-report excerpt (quality values are stable; latency is
run-specific):

```markdown
**Decision:** `PASSED`

| Configuration | Provider | Model | Cases passed | Schema validity | Field accuracy | P95 latency (ms) |
| --- | --- | --- | ---: | ---: | ---: | ---: |
| baseline | mock | invoice-baseline-v1 | 20/20 | 1.0 | 1.0 | <run-specific value> |
| candidate | mock | invoice-candidate-v2 | 20/20 | 1.0 | 1.0 | <run-specific value> |
```

It will:

1. Load a small versioned invoice-extraction dataset.
2. Run baseline and candidate configurations through a deterministic provider.
3. Store normalized generation records.
4. Evaluate schema validity and field-level accuracy.
5. Compare the candidate with the baseline.
6. Apply configured quality gates.
7. Write JSON and Markdown reports.
8. Return a nonzero exit code when a gate fails.

No API key, database, web application, or paid model is required.

## Planning documents

- [Product vision](docs/VISION.md) — audience, problem, principles, and positioning.
- [MVP specification](docs/MVP.md) — exact first-release behavior, scope, and acceptance criteria.
- [Architecture](docs/ARCHITECTURE.md) — domain model, boundaries, execution flow, and technical decisions.
- [Implementation plan](docs/IMPLEMENTATION_PLAN.md) — sequenced build tasks and verification checkpoints.
- [Benchmark plan](docs/BENCHMARK_PLAN.md) — hypotheses, datasets, metrics, and reporting rules.
- [Roadmap](docs/ROADMAP.md) — capability order after the first release.

The original broad concept is retained in
[EvalForge_Portfolio_Plan.md](EvalForge_Portfolio_Plan.md), but the documents
above are authoritative when they differ.

## Getting started

### Installation & development setup

Prerequisites: Python 3.13+ and [uv](https://docs.astral.sh/uv/).

```bash
# Clone and sync dependencies
git clone https://github.com/jrmywm/evalforge.git
cd evalforge
uv sync --all-groups

# Run manifest validation dry run
uv run evalforge validate examples/invoice/eval.yaml

# Run tests and linting
uv run pytest
uv run ruff check .
uv run ruff format --check .
```

## Current status

Milestones 0 through 5 are complete, and the OpenAI-compatible local provider
stage is provider-ready pending a real runtime benchmark. The repository has a Python 3.13 CLI
scaffold, strict experiment-manifest and JSONL dataset contracts, deterministic
mock-provider execution, atomic generation/evaluation artifacts, offline
deterministic evaluators, configuration summaries, baseline/candidate regression
comparison, deterministic quality gates, and the complete mock-based run/report
workflow. The MVP remains local-only and requires no API key or external service.
