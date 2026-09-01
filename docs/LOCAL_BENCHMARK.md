# Local inference benchmark capture

EvalForge can run against any local server that implements the non-streaming
OpenAI-compatible `POST /v1/chat/completions` contract. The repository does not
download a runtime or model. The first real capture is documented in
[qwen25-05b-cpu-20260901.md](benchmarks/qwen25-05b-cpu-20260901.md), with
artifacts in `artifacts/qwen25-05b-prompt-comparison-20260901`.

## Suggested capture

Start a local server (for example, llama.cpp) with a JSON-capable model:

```bash
llama-server -m /path/to/model.gguf --host 127.0.0.1 --port 8080
uv run evalforge run examples/invoice/local-openai.yaml --run-id local-YYYYMMDD
```

When `json_response` is enabled, EvalForge sends the output schema using the
OpenAI-compatible structured response format (`type: json_schema`, strict mode,
and the schema named `evalforge_output`). The schema is also included in the
prompt for servers that expose only partial structured-output support. The
local invoice fixture compares two prompts against the same model with
temperature `0`, a fixed seed, and a bounded token budget; the candidate prompt
additionally specifies ISO currency/final-total handling and ignores untrusted
invoice instructions.

Before publishing the resulting artifact directory, record:

- EvalForge version and source commit;
- OS, Python version, CPU, RAM, GPU/VRAM, and driver/runtime versions;
- server name/version, model path/name, quantization, context size, batch size,
  and concurrency;
- manifest and dataset versions/digests, prompt, inference parameters, and
  evaluator versions;
- generation/evaluation artifacts and the final report; and
- limitations such as dataset size, warm-up policy, sampling settings, and
  whether timings include serialization or network loopback overhead.

The report records provider, resolved model, latency, and any token usage the
server returns. The captured report records 14/20 cases passed for both
configurations, schema validity 1.0, and field accuracy 0.9; these results are
limited to the one synthetic dataset/run and should not be generalized.
