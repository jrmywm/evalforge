# EvalForge Architecture

## Architectural style

The MVP is a single-process CLI organized as a modular Python package. Domain
logic must not depend on the CLI or artifact format. Provider execution,
evaluation, comparison, and reporting are separate boundaries.

```text
CLI
 │
 ▼
Manifest loader ──► validated ExperimentConfig
 │
 ▼
Experiment engine
 ├──► Provider ──► GenerationRecord
 ├──► Evaluators ──► EvaluationResult
 ├──► Aggregator ──► ConfigurationSummary
 ├──► Comparator ──► RegressionResult
 └──► Gate engine ──► QualityGateResult
                         │
                         ▼
                    Report writers
```

## Proposed package structure

```text
src/evalforge/
├── cli.py
├── config.py
├── models.py
├── engine.py
├── aggregation.py
├── regression.py
├── gates.py
├── providers/
│   ├── base.py
│   └── mock.py
├── evaluators/
│   ├── base.py
│   ├── json_schema.py
│   └── field_accuracy.py
└── reporting/
    ├── json_report.py
    └── markdown_report.py
```

This is a starting layout, not a mandate to create empty modules. A module should
exist only when it owns real behavior.

## Domain model

### `TestCase`

- stable ID;
- input payload;
- expected output;
- tags; and
- optional description.

### `DatasetSnapshot`

- name and declared version;
- content digest;
- source path; and
- validated test cases.

The content digest prevents two different datasets from silently sharing a
version label.

### `ModelConfig`

- configuration ID such as `baseline` or `candidate`;
- provider name;
- model identifier;
- prompt or prompt reference;
- inference parameters; and
- optional seed.

### `ExperimentConfig`

- experiment identity;
- dataset reference;
- configurations;
- evaluator specifications;
- quality gates;
- artifact settings; and
- execution settings.

### `GenerationRecord`

- experiment, configuration, and case IDs;
- normalized request;
- raw and normalized response;
- provider and model identity;
- inference parameters;
- start and end timestamps;
- latency;
- input and output token counts when known;
- estimated monetary cost when known;
- origin: `fresh`, `cache`, or `replay`;
- terminal status; and
- structured error details.

This record is immutable after it is written. Evaluation results refer to it.

### `EvaluationResult`

- generation ID;
- evaluator name and version;
- numeric score when applicable;
- pass/fail status;
- reason;
- structured details such as field mismatches; and
- evaluator error, distinct from a model failure.

### `ConfigurationSummary`

- evaluated, failed, and errored case counts;
- aggregate evaluator scores;
- latency percentiles;
- token and cost totals; and
- tag-level breakdowns where supported.

### `RegressionResult`

- baseline and candidate summaries;
- absolute and relative changes;
- per-metric interpretation; and
- newly failing and newly passing cases.

### `QualityGateResult`

- final decision;
- evaluated rules;
- observed values;
- thresholds; and
- all failure reasons.

## Execution invariants

- Baseline and candidate use the exact same dataset snapshot.
- Provider exceptions become generation errors; they do not masquerade as score
  zero or terminate unrelated cases.
- Evaluator exceptions become evaluator errors and cannot silently pass a gate.
- Reports are derived from structured result objects, not independently computed.
- Aggregation defines how missing and errored cases affect every metric.
- Stable IDs link manifests, generations, evaluations, and reports.
- Artifact writes are atomic where practical so partial reports are not mistaken
  for completed experiments.

## Artifact layout

```text
artifacts/<experiment-run-id>/
├── manifest.snapshot.yaml
├── dataset.snapshot.jsonl
├── generations.jsonl
├── evaluations.jsonl
├── experiment.json
└── report.md
```

The run identifier may include a timestamp, but reproducibility must rely on
content digests and captured configuration rather than the timestamp.

Completed runs are indexed in `evalforge.sqlite3` below the effective artifact
root (or an explicitly supplied history path). The index stores canonical report
JSON and artifact references, uses SQLite WAL mode and parameterized queries, and
never stores API-key values. Replay consumes immutable snapshot artifacts without
constructing or invoking a provider.

## Metric semantics

### Schema validity

The proportion of attempted generations that parse and satisfy the configured
schema. Provider failures are reported separately and must not disappear from the
denominator without an explicit policy.

### Field accuracy

The number of correct comparable fields divided by the number of expected fields.
The evaluator must define behavior for absent optional fields, numeric tolerance,
case sensitivity, and normalized representations.

### Newly failing cases

`new_failure_count` is the number of case IDs that pass every configured
evaluator for the baseline and fail at least one evaluator for the candidate.
It supports an absolute maximum gate, commonly zero, so an aggregate quality
improvement cannot conceal regressions on previously working inputs.

### Latency

Report at least median and P95 duration for successful provider calls. Also report
the number of failed calls so a fast failure cannot improve perceived latency.

### Cost

Mock executions report no API charge. A future provider may report actual or
estimated monetary cost. Local compute must be labelled separately rather than
presented as universally free.

## Caching and replay policy

Caching is intentionally deferred, but its semantics are defined now:

- `fresh` requests provider inference;
- `cache` reuses a response with an exact canonical request key; and
- `replay` evaluates explicitly selected stored generations.

Benchmark runs should default to fresh generation unless their stated methodology
permits cache use. Nondeterministic sampling must not be hidden behind cache hits.
The canonical key will eventually include provider, resolved model identity,
prompt messages, input, tools, output schema, inference parameters, and relevant
provider options.

## Future boundaries

After the CLI proves useful, the same domain services can be invoked by FastAPI
and a worker. PostgreSQL can replace filesystem indexing while object artifacts
remain portable. These are migrations driven by actual requirements, not MVP
dependencies.
