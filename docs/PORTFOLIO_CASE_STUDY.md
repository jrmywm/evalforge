# EvalForge: release assurance for invoice extraction

## The business problem

Invoice extraction is a useful example of a production AI change that looks
small in code but carries operational risk. A prompt or model update can return
valid JSON while changing invoice numbers, currencies, or final totals. A team
needs an evidence-backed answer before promoting the candidate configuration.

EvalForge treats that answer as a release decision: run the baseline and
candidate against the same versioned invoice dataset, evaluate schema validity
and field accuracy, compare regressions, apply explicit quality gates, and show
the exact cases behind a block. This is a local demonstration, not a claim of
production deployment or customer impact.

### Stakeholders and risks

- **AI/product engineering:** needs a repeatable way to compare prompts,
  models, and inference settings.
- **Operations and finance users:** care about incorrect invoice identifiers,
  currencies, and totals more than aggregate scores alone.
- **Release owners:** need a clear pass/block decision and an auditable record
  of the inputs, evaluator results, and thresholds.
- **Security reviewers:** need confidence that invoice text is treated as
  untrusted input and that local tooling does not expose credentials or permit
  arbitrary manifest paths.

The current gates are visible in each manifest. The regression fixture is
expected to block because the candidate introduces field-level failures; the
pass fixture is expected to pass. The local OpenAI-compatible fixture is
provider-ready, while its single synthetic CPU capture is evidence for
reproducibility only, not a general quality or latency claim.

## Three-minute demo script

Use `examples/invoice/portfolio.yaml` as the primary portfolio story. It shows a
candidate improving field accuracy from `0.90` to `0.967` while EvalForge blocks
the release because two previously passing critical cases regress. See
`docs/benchmarks/portfolio-tradeoff.md` for the exact narrative and evidence.

Start two terminals from the repository root:

```bash
uv run evalforge serve --artifact-root artifacts
cd web
npm install
npm run dev -- --host 127.0.0.1 --port 5173
```

Open the workbench at:

```text
http://localhost:5173/?run=mock-regression-demo&step=decide
```

Then use this sequence:

1. **Decide (0:00-0:45).** Point out the candidate decision, gate evidence,
   current baseline, proposed candidate, and displayed failed cases. The
   important interaction is tracing a block back to the field mismatch that
   caused it.
2. **Investigate (0:45-1:30).** Select a failed case and show expected versus
   actual values, the evaluator reason, and generation metadata.
3. **Define (1:30-2:00).** Show the dataset snapshot, evaluator set, and every
   configured gate, including data integrity. This makes the comparison
   contract explicit.
4. **Run (2:00-2:35).** The UI can submit a workspace-local manifest through
   `POST /api/runs`. The exact CLI equivalents are:

   ```bash
   uv run evalforge run examples/invoice/pass.yaml
   uv run evalforge run examples/invoice/regression.yaml
   ```

   The pass command exits `0`; the regression command writes complete artifacts
   and exits `1` because a quality gate fails.
5. **Replay (2:35-3:00).** Return to Decide and select offline replay. Explain
   that replay reads immutable stored artifacts and does not call a model; the
   UI distinguishes a reproduced pass/block from a transport failure.

For a clean checkout with the included real-local capture, import it first:

```bash
uv run evalforge history import artifacts/qwen25-05b-prompt-comparison-20260901
```

The API request is a relative YAML manifest path plus an optional run ID. The
server resolves it below its configured workspace root. See the generated
contract at `http://127.0.0.1:8765/docs`.

## Architecture and data flow

```text
manifest + dataset snapshot -> validated experiment config
        -> baseline + candidate providers -> immutable generations.jsonl
        -> schema + field evaluators -> evaluations.jsonl
        -> aggregation -> regression -> quality gates
        -> experiment.json + report.md + SQLite index
        -> local API + local review workbench
```

The CLI and API share the same domain pipeline. Reports are derived from
structured results, and the six run artifacts are written as an immutable
evidence bundle. SQLite indexes completed reports for list/detail/replay;
replay evaluates stored generations without provider access.

## Security boundaries and limitations

- The default server binds to loopback. CORS allows only local development
  origins. Remote binding requires `--allow-remote` and has no authentication.
- The API accepts only workspace-relative YAML manifests, rejects traversal,
  absolute paths, unsupported extensions, and symlink escapes, and never
  invokes a shell to run a manifest.
- Provider API keys are read from the environment variable named by a manifest;
  key values are not stored in reports, history, or error details.
- Invoice text is data, not instructions. The local fixture's candidate prompt
  tests handling of prompt-injection text, but coverage is not comprehensive.
- The dataset is small and synthetic. The deterministic mock proves workflow
  behavior; the included local-model capture is one CPU datapoint. It does not
  establish production accuracy, cost, throughput, or customer outcomes.
- Authentication, hosted tenancy, background workers, broad benchmark coverage,
  and human-calibrated semantic judging are outside the current scope.

## Verification

From the repository root:

```bash
uv run pytest
uv run ruff check .
uv run ruff format --check .
```

For the web application:

```bash
cd web
npm run format -- --check
npm run lint
npm run build
```

Useful read-only checks include `uv run evalforge history list`,
`uv run evalforge history show <run-id>`, and
`uv run evalforge replay <run-id>`. Replay should reproduce the stored decision
without contacting a provider.

## Resume-ready description

**EvalForge — local-first AI release assurance for structured extraction.**
Built a Python 3.13 evaluation pipeline and local review workbench that
compares baseline and candidate invoice-extraction configurations on identical
versioned data; records immutable generation/evaluation JSONL artifacts;
computes schema validity, field accuracy, latency, regressions, and explicit
quality gates; indexes runs in SQLite; and supports offline replay through a
FastAPI API. Added deterministic mock coverage, an OpenAI-compatible local
provider, typed API errors, workspace-path validation, and a UI that traces a
release block to the exact failed field rather than hiding behind an aggregate
score.

## Interview framing

The strongest engineering story is the decision boundary: a model response is
not treated as useful merely because it parses. The system separates provider
errors from evaluator errors, uses the same dataset snapshot for both sides of
the comparison, preserves evidence for review, and keeps replay independent of
provider availability. Those choices map directly to forward-deployed work:
turning an ambiguous business risk into a measurable contract, implementing the
software end to end, and making the result understandable to engineers and
client stakeholders.
