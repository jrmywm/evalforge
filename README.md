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

The intended command is:

```bash
evalforge run examples/invoice/eval.yaml
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

Milestones 0 and 1 are complete: the repository has a Python 3.13 CLI scaffold,
quality tooling, strict experiment-manifest validation, JSONL dataset loading,
content digests, and a 20-case invoice example. Next is Milestone 2: deterministic
mock-provider execution and generation artifacts.
