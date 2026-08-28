# EvalForge Validation Hardening Plan

## Purpose

This document is a self-contained implementation handoff for Gemini. Complete
this hardening pass before beginning Milestone 2 (provider execution and
generation artifacts).

The objective is to make the validated experiment and dataset snapshots truly
reproducible, deeply immutable, and safe to use as the foundation for execution.

## Starting state

The working tree already contains uncommitted fixes from the first audit. Preserve
and review them; do not reset, discard, or recreate them blindly.

Existing uncommitted work currently addresses:

- canonical manifest hashing;
- direct Pydantic model freezing;
- finite quality-gate thresholds;
- rejection of nonstandard JSON constants;
- malformed UTF-8 dataset handling;
- duplicate YAML-key rejection;
- locked CI dependency installation;
- README setup instructions; and
- the missing MIT license file.

Before editing, run:

```bash
git status --short
git diff --check
git diff
uv lock --check
uv run ruff format --check .
uv run ruff check .
uv run pytest
```

Expected baseline: 13 tests pass. `git diff --check` currently reports an extra
blank line at the end of `README.md`; fix it during this work.

## Scope

Implement only validation and reproducibility hardening:

1. Deeply immutable manifest and dataset values.
2. Recursive JSON-value validation, including finite-number enforcement.
3. Semantic output-schema and quality-gate validation.
4. Robust duplicate-key YAML error handling.
5. Missing edge-case tests and documentation cleanup.

Do not implement providers, generation records, evaluators, experiment execution,
reports, caching, databases, APIs, or UI in this change.

## 1. Introduce a canonical JSON-value boundary

Create a small module such as `src/evalforge/json_types.py` that owns recursive
JSON normalization. Avoid scattering ad hoc recursion across the configuration and
dataset modules.

The accepted value domain is:

```text
null | boolean | integer | finite float | string
| array of accepted values
| object with string keys and accepted values
```

Reject:

- `NaN`, positive infinity, and negative infinity;
- bytes;
- dates and datetimes implicitly created by YAML;
- sets and tuples supplied as manifest values;
- mappings with non-string keys; and
- arbitrary Python objects.

Errors must identify the logical path where possible, for example:

```text
configurations.candidate.inference_parameters.temperature must be finite
```

### Deep-freezing strategy

After validation, recursively convert:

- mappings to a read-only mapping representation; and
- sequences to tuples.

Prefer standard-library types. `types.MappingProxyType` is acceptable if Pydantic
serialization and equality are verified. If it causes unreliable serialization,
implement a minimal internal immutable `Mapping` instead of adding a dependency
solely for frozen dictionaries.

Provide explicit helpers with clear responsibilities, such as:

- `validate_json_value(value, path)`: reject invalid values;
- `freeze_json(value)`: recursively create immutable values; and
- `thaw_json(value)`: produce ordinary JSON-serializable dictionaries and lists.

`canonical_digest` must operate on the thawed canonical representation. It must
continue using sorted keys, stable separators, UTF-8, and `ensure_ascii=False`.

Do not rely on `ConfigDict(frozen=True)` alone. Pydantic freezing is shallow.

## 2. Make every snapshot-relevant container deeply immutable

Apply the shared JSON helpers to all values that contribute to an experiment or
dataset digest.

### Manifest models

Deep-freeze:

- `ModelConfig.inference_parameters`;
- `ExperimentConfig.configurations`;
- `ExperimentConfig.output_schema`;
- `ExperimentConfig.evaluators` as a tuple;
- `ExperimentConfig.quality_gates`; and
- any nested collections inside these fields.

The nested Pydantic models should remain frozen as well.

### Dataset models

Deep-freeze:

- `TestCase.input`;
- `TestCase.expected`;
- `TestCase.tags` as a tuple; and
- all nested objects and arrays inside input and expected values.

`DatasetSnapshot.cases` should remain a tuple.

### Required immutability tests

Tests must attempt mutation at more than one depth:

```python
manifest.config.output_schema["tampered"] = True
manifest.config.configurations["candidate"].inference_parameters["temperature"] = 2
dataset.cases[0].input["text"] = "mutated"
dataset.cases[0].expected["nested"]["value"] = "mutated"
dataset.cases[0].tags.append("mutated")
```

Each operation must fail. Confirm afterward that serialized values and digests are
unchanged.

Do not weaken the tests with only direct attribute assignment; that is already
covered and was the gap in the previous fix.

## 3. Enforce JSON compatibility and finite numbers everywhere

The current changes reject `NaN` in quality gates and JSONL parsing, but YAML
values stored under `Any` can still contain non-finite numbers or non-JSON types.

Apply recursive validation to:

- `ModelConfig.inference_parameters`;
- `ExperimentConfig.output_schema`;
- `TestCase.input`; and
- `TestCase.expected`.

Add tests for:

- `.nan`, `.inf`, and `-.inf` in every quality-gate field;
- `.nan` and `.inf` under inference parameters;
- non-finite constants in dataset input and expected output;
- YAML timestamps or binary values in JSON-only fields; and
- nested non-finite values, not just top-level values.

Rename or parameterize the existing tests so a test claiming infinity coverage
actually exercises positive and negative infinity.

## 4. Validate output-schema semantics

Add `jsonschema` as a runtime dependency and update `uv.lock`.

Validate `ExperimentConfig.output_schema` using the schema's declared dialect when
present. A suitable approach is:

```python
validator_class = jsonschema.validators.validator_for(schema)
validator_class.check_schema(schema)
```

Convert schema-library exceptions into the existing `ManifestError` boundary with
an actionable message. Do not expose an uncaught `SchemaError` from the CLI.

At minimum, reject:

- an empty schema if the project decides it carries no useful contract;
- unknown or invalid schema keywords when the selected dialect treats them as
  invalid;
- malformed `type`, `required`, or `properties` values; and
- an invalid `$schema` URI/dialect declaration.

Add tests for one valid Draft 2020-12 schema and several invalid schemas.

## 5. Validate quality-gate metric names and evaluator relationships

Define the MVP metric names explicitly:

```text
schema_validity
field_accuracy
p95_latency_ms
```

Reject unknown quality-gate keys during manifest validation.

Enforce these relationships:

- `schema_validity` requires the `json_schema` evaluator;
- `field_accuracy` requires the `field_accuracy` evaluator; and
- `p95_latency_ms` is an execution metric and requires no evaluator.

Also reject duplicate evaluator types, because running the same MVP evaluator
twice has no defined meaning.

Add tests for:

- an unknown metric name;
- a missing required evaluator;
- duplicate evaluator entries; and
- the valid example manifest.

Keep these rules in one named mapping or validator so later metrics do not require
duplicated conditional code.

## 6. Harden the YAML duplicate-key loader

The current `_construct_mapping` uses a key in dictionary membership before
ensuring that the constructed key is hashable. Unusual YAML such as a sequence or
mapping used as a key can therefore raise an uncaught `TypeError`.

Ensure every invalid mapping key becomes `yaml.constructor.ConstructorError` or
another `yaml.YAMLError`, which `load_manifest` already converts to
`ManifestError`.

Preserve nested duplicate-key detection.

Add tests for:

- a duplicate top-level key;
- a duplicate nested key; and
- an unhashable sequence/mapping key.

No malformed YAML input should escape the public loader as `TypeError`.

## 7. Finish validation contracts and error paths

Add or confirm tests for the documented Milestone 1 behavior:

- empty dataset;
- missing dataset file;
- malformed UTF-8 manifest;
- malformed UTF-8 dataset;
- manifest root that is not a mapping;
- empty expected output if field accuracy requires at least one expected field;
- whitespace-only experiment names, configuration names, provider names, model
  names, case IDs, and tags;
- duplicate case tags if they are not meaningful; and
- CLI exit code `2` for invalid manifest and dataset inputs.

Use parameterized tests where it improves readability. Avoid testing Pydantic
internals or brittle full error strings; assert the stable error category and the
relevant field or line number.

## 8. Documentation and repository cleanup

- Remove the extra blank line at the end of `README.md` so `git diff --check`
  passes.
- Keep the new `LICENSE` file.
- Keep `uv sync --locked --all-groups` in CI.
- Ensure local setup instructions match actual commands.
- Add a short note to `docs/IMPLEMENTATION_PLAN.md` recording this hardening pass
  as complete only after every verification command passes.
- Do not mark Milestone 2 complete or partially complete.

## Verification checklist

Run all of these from the repository root:

```bash
uv sync --all-groups
uv lock --check
uv run ruff format .
uv run ruff format --check .
uv run ruff check .
uv run pytest
uv run evalforge --help
uv run evalforge --version
uv run evalforge validate examples/invoice/eval.yaml
git diff --check
git status --short
```

Also build the package into the ignored `.tmp/` directory and inspect its contents:

```bash
uv build --out-dir .tmp/dist
```

The wheel and source distribution must contain the `evalforge` package, README,
and license metadata. Do not commit `.tmp/` artifacts.

## Definition of done

This hardening pass is complete only when:

- manifest and dataset content cannot be mutated at any nested depth;
- digests remain stable across YAML formatting and line-ending changes;
- digests cannot diverge from live in-memory snapshot values;
- every accepted `Any` value is valid JSON data with finite numbers;
- invalid JSON Schemas are rejected during manifest validation;
- quality-gate names and evaluator dependencies are validated;
- malformed YAML mapping keys produce `ManifestError`;
- invalid CLI inputs consistently return exit code `2`;
- formatting, lint, tests, package build, lockfile check, and diff check pass; and
- no Milestone 2 functionality has been introduced.

## Commit guidance

The tree already contains a coherent group of uncommitted audit fixes. After all
items above pass, create one focused commit containing only:

- the existing audit fixes;
- the remaining validation hardening;
- tests;
- dependency and lockfile changes;
- README/license/CI cleanup; and
- this hardening plan and the implementation-status update.

Suggested commit message:

```text
Harden manifest and dataset validation
```

Before committing, inspect `git diff --cached --check` and the complete staged
diff. Do not commit `.python/`, `.uv-cache/`, `.venv/`, `.tmp/`, build artifacts,
or unrelated files. Do not push unless the user explicitly requests it.
