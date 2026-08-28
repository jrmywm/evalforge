# EvalForge Roadmap

## Roadmap policy

This roadmap is ordered by demonstrated product value, not by technology novelty.
A stage begins only after the previous stage has a working demonstration and
passing acceptance criteria.

Later stages may change in response to benchmark findings. Only the CLI MVP is a
committed scope.

## Stage 1 — CLI regression evaluator

Deliver the specification in [MVP.md](MVP.md):

- invoice-extraction dataset;
- deterministic mock provider;
- schema and field-accuracy evaluators;
- baseline-versus-candidate comparison;
- release gates;
- JSON and Markdown artifacts; and
- CI-compatible exit codes.

Exit condition: the complete pass/fail demo runs from a clean checkout without
credentials.

## Stage 2 — Real local inference

Add one provider for an OpenAI-compatible local endpoint, initially targeting an
accessible server such as llama.cpp or Ollama. Treat vLLM as a later performance
target for compatible Linux/GPU environments.

Add:

- provider timeouts and retry policy;
- resolved model identity;
- token accounting where supported;
- fresh/cache/replay execution modes; and
- real benchmark methodology.

Exit condition: compare two real local configurations and publish reproducible
artifacts with clearly stated hardware and limitations.

## Stage 3 — Durable local experiment history

Add SQLite first unless concurrent or hosted operation creates a demonstrated need
for PostgreSQL.

Add:

- searchable experiment history;
- dataset, prompt, and evaluator version records;
- artifact indexing;
- cache lookup with canonical request keys; and
- offline reevaluation of stored generations.

Exit condition: a developer can find, replay, and compare prior experiments
without manually locating artifact directories.

## Stage 4 — API and focused web interface

Add FastAPI and a small Next.js interface around proven workflows:

- experiment list and detail;
- baseline/candidate comparison;
- failure explorer; and
- configuration submission.

Avoid a generic dashboard until user workflows establish which summaries matter.

Exit condition: the UI makes the existing comparison and failure workflow faster
without changing its semantics.

## Stage 5 — Calibrated semantic evaluation

Add LLM-as-a-judge only for a selected behavior unsupported by deterministic
evaluation.

Add:

- versioned rubrics;
- human-labelled calibration cases;
- agreement analysis;
- judge abstention and error handling; and
- judge cost tracking.

Exit condition: documented evidence shows when the judge is reliable enough to
inform, but not silently define, a release decision.

## Stage 6 — Adversarial and security evaluation

Add reviewed adversarial cases and mutation strategies for:

- ambiguous and corrupted structured inputs;
- direct and indirect prompt injection;
- schema manipulation; and
- unsafe or unauthorized tool requests when tools are introduced.

Exit condition: EvalForge catches a security or robustness regression that normal
cases do not expose.

## Stage 7 — RAG evaluation

Extend records and evaluators to cover retrieval independently from generation:

- retrieval precision and recall;
- context relevance;
- grounded answer correctness; and
- citation correctness.

Exit condition: compare two retriever configurations and explain whether changed
answer quality came from retrieval or generation.

## Stage 8 — Agent trajectory evaluation

Add structured trajectory records and deterministic checks for:

- tool selection;
- arguments;
- ordering;
- unnecessary or missing calls;
- loop length; and
- final-answer correctness.

Exit condition: identify a trajectory regression that final-answer-only scoring
would miss.

## Stage 9 — Scale and observability

Only after experiment volume requires it, consider:

- background workers;
- PostgreSQL;
- Redis;
- OpenTelemetry;
- Langfuse;
- Prometheus and Grafana; and
- Temporal for durable orchestration.

Each dependency requires a written operational need and a demonstration of the
failure mode it resolves.

## Stage 10 — Distribution and deployment

Potential outcomes include:

- reusable GitHub Action;
- pull-request annotations;
- hosted team deployment;
- container images; and
- Kubernetes manifests if real deployment requirements justify them.

This stage is optional for portfolio success. A deeply tested CLI with credible
benchmarks is more valuable than an elaborate deployment without users or
evidence.

## Portfolio-ready threshold

EvalForge is ready to feature prominently when it has:

- a polished CLI and focused UI or exceptionally clear reports;
- one real local-model benchmark;
- reproducible raw artifacts;
- a compelling regression story;
- tests and CI;
- a short demo video; and
- documentation of limitations and engineering tradeoffs.

Temporal, Kubernetes, multiple commercial providers, and broad framework support
are not required for this threshold.
