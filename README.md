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

The portfolio tradeoff fixture demonstrates the less obvious failure mode: the
candidate improves field accuracy from `0.90` to `0.967` and passes 18 rather
than 14 cases, but it newly breaks two previously working critical cases. The
`new_failure_count` gate blocks the release because aggregate improvement does
not erase individual regressions:

```bash
uv run evalforge run examples/invoice/portfolio.yaml
```

This is an expected-failure command and exits with status `1` after preserving
the complete evidence bundle.

The corrected follow-up retains the same dataset and policy, resolves both new
failures, and passes all 20 cases:

```bash
uv run evalforge run examples/invoice/portfolio-fixed.yaml
```

### Local OpenAI-compatible inference

The provider-ready local fixture targets a llama.cpp-compatible server. It does
not download a runtime or model. A first real CPU capture is documented in
[the benchmark evidence](docs/benchmarks/qwen25-05b-cpu-20260901.md); it is one
reproducibility datapoint, not a general quality claim:

```bash
llama-server -m /path/to/model.gguf --host 127.0.0.1 --port 8080
uv run evalforge run examples/invoice/local-openai.yaml --run-id local-demo
```

See [local benchmark capture](docs/LOCAL_BENCHMARK.md) for the reproducibility
fields and limitations to record. The local provider reads an optional API key
from an environment variable named in the manifest; the key itself is never
stored in manifests, reports, or error details.

With `json_response: true`, requests use strict OpenAI-compatible
`json_schema` response formatting with the manifest's output schema (and repeat
the schema in the prompt for partial implementations). The local invoice
fixture uses the same model, temperature `0`, fixed seed, and bounded
`max_tokens` for both configurations; the candidate prompt adds explicit ISO
currency, final-total, and prompt-injection handling. The captured run and its
limitations are recorded in the benchmark evidence linked above; the
repository does not claim local quality from this single fixture run alone.

Completed runs are indexed automatically in SQLite below the effective artifact
root. Inspect or reevaluate them without provider access:

```bash
uv run evalforge history list
uv run evalforge history show <run-id>
uv run evalforge replay <run-id>
```

The commands above use the cwd-local `artifacts` directory by default. An
explicit artifact root can be selected when working from another location:

```bash
uv run evalforge history list --artifact-root artifacts
uv run evalforge history show <run-id> --artifact-root artifacts
uv run evalforge replay <run-id> --artifact-root artifacts
```

Use `--history-db PATH` on `run`, `history`, or `replay` for an explicit local
database location. Replay reads immutable snapshot artifacts and never calls a
provider.

To index a completed artifact directory copied from another checkout without
rerunning inference, import it directly (the default database is beside the
artifact directory):

```bash
uv run evalforge history import /path/to/artifacts/<run-id>
```

Use `--history-db PATH` when importing into a specific history database. The
import requires all six immutable artifacts and verifies their contents before
indexing.

### Local dashboard API

The Python API exposes health, indexed runs, run detail, offline replay, and a
local run endpoint for workspace manifests. `POST /api/runs` accepts only a
relative YAML path below the configured workspace, rejects traversal and
absolute paths, and invokes no shell. It uses the same cwd-local history DB by
default and binds to loopback:

```bash
uv run evalforge serve
```

Use `--artifact-root PATH` or `--history-db PATH` to select another local
history store. CORS is limited to local development origins on ports 3000 and
5173. Binding a non-loopback host requires `--allow-remote` and provides no
authentication.

### Visual dashboard

Start the API, then run the local web application in a second terminal:

```bash
uv run evalforge serve --artifact-root artifacts
cd web
npm install
npm run dev -- --host 127.0.0.1 --port 5173
```

Open `http://localhost:5173`. The dashboard compares baseline and candidate
metrics, shows release-gate evidence and failed cases, and can verify an indexed
run through offline replay. In a clean clone, first restore the included capture
with `uv run evalforge history import artifacts/qwen25-05b-prompt-comparison-20260901`.

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
- [Benchmark plan](docs/BENCHMARK_PLAN.md) — hypotheses, datasets, metrics, and reporting rules.
- [Roadmap](docs/ROADMAP.md) — capability order after the first release.
- [Portfolio case study](docs/PORTFOLIO_CASE_STUDY.md) — business framing,
  three-minute demo, architecture, limitations, verification, and resume copy.

The documents above are authoritative for the current project scope.

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
stage is provider-ready with a first real CPU benchmark capture documented;
broader benchmark coverage remains pending. The repository has a Python 3.13 CLI
scaffold, strict experiment-manifest and JSONL dataset contracts, deterministic
mock-provider execution, atomic generation/evaluation artifacts, offline
deterministic evaluators, configuration summaries, baseline/candidate regression
comparison, deterministic quality gates, the complete mock-based run/report
workflow, and durable SQLite history with offline replay. The MVP remains
local-only and requires no API key or external service. A local FastAPI API and
focused visual dashboard are available for inspecting indexed runs, launching
workspace-local manifests, and replaying immutable evidence.
