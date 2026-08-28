# EvalForge Benchmark Plan

## Purpose

The benchmark is both a product test and the primary portfolio evidence. It must
show a decision that is reproducible, inspectable, and more useful than a single
average accuracy number.

## MVP benchmark

The MVP uses deterministic mock providers. This benchmark verifies EvalForge's
mechanics; it does not claim anything about real model quality.

### Questions

- Does the engine score known outputs correctly?
- Does it expose regressions hidden by an improved aggregate score?
- Does it enforce release thresholds consistently?
- Can a reviewer identify the exact failed cases?

### Dataset composition

Create approximately 20 invoice-extraction cases across these tags:

- ordinary invoices;
- ambiguous dates;
- thousands and decimal separators;
- multiple currencies;
- missing optional fields;
- duplicate or distracting values;
- Unicode text; and
- malformed or incomplete source text.

Cases should be authored deliberately. Generated variants must be reviewed before
they are accepted as benchmark data.

### Demonstration configurations

Provide at least two manifests:

1. `pass.yaml`: candidate improves or preserves quality and satisfies every gate.
2. `regression.yaml`: candidate improves at least one aggregate metric but causes
   a meaningful subset regression or threshold violation.

The second scenario is the stronger demonstration because it proves that a simple
headline metric is insufficient.

## Metrics

### Required for MVP

- JSON parse rate;
- schema-validity rate;
- field-level accuracy;
- case pass rate;
- median latency;
- P95 latency;
- provider error count; and
- evaluator error count.

Cost and token fields should exist in records, but mock results must clearly label
them as unavailable or zero API charge rather than implying a real economic
comparison.

### Later real-model benchmark

After adding a local OpenAI-compatible provider, measure:

- the same quality and reliability metrics;
- time to first token where available;
- total latency;
- input and output tokens;
- throughput under a declared concurrency;
- peak memory or VRAM when measurable; and
- model and quantization identity.

Commercial pricing comparisons are optional and must include the pricing date and
source in the generated methodology.

## Quality-gate policy

The initial benchmark should exercise:

- an absolute quality minimum;
- a maximum permitted quality regression;
- a schema-validity requirement;
- a latency ceiling; and
- zero tolerance for evaluator errors.

Thresholds must be declared before running the benchmark. Do not tune a threshold
after seeing a candidate result without documenting the change as a new policy
version.

## Reproducibility record

Every published benchmark should include:

- EvalForge version or source commit;
- operating system and Python version;
- dataset name, version, and digest;
- manifest snapshot and digest;
- provider and model identity;
- prompt and inference parameters;
- evaluator names and versions;
- execution origin: fresh, cache, or replay;
- start time and duration; and
- raw generation and evaluation artifacts where licensing permits.

For local models, also record relevant hardware, server software, quantization,
context configuration, batch settings, and concurrency.

## Statistical discipline

The 20-case MVP dataset validates workflow behavior but is too small for broad
claims about model superiority. Later model comparisons should:

- use enough cases to report uncertainty;
- use paired comparisons because models see the same cases;
- report counts and confidence intervals alongside percentages;
- separate exploratory and held-out cases;
- repeat nondeterministic samples when variability matters; and
- avoid treating LLM-judge scores as ground truth without calibration.

## LLM-judge entry criteria

Do not introduce an LLM judge until:

- deterministic evaluation is insufficient for a named target behavior;
- a human-labelled calibration set exists;
- the rubric has explicit examples and an abstention policy;
- agreement with human labels can be measured; and
- judge model, prompt, cost, and latency are recorded.

## Reporting rules

- Label mock, local, and commercial results distinctly.
- Never publish placeholder percentages as measured findings.
- Show absolute case counts with rates.
- Disclose excluded and errored cases.
- Present regressions as prominently as improvements.
- Preserve failed examples unless data restrictions prevent it.
- State limitations next to conclusions, not in an obscure appendix.

## Desired first portfolio finding

The first credible finding should resemble:

> Candidate B improved overall field accuracy, but EvalForge blocked it because
> date accuracy regressed on ambiguous formats beyond the declared threshold.

This claim is modest, easy to reproduce, and demonstrates why the tool exists.
