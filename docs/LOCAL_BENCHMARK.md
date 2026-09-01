# Local inference benchmark capture

EvalForge can run against any local server that implements the non-streaming
OpenAI-compatible `POST /v1/chat/completions` contract. The repository does not
download a runtime or model and contains no fabricated local-model results.

## Suggested capture

Start a local server (for example, llama.cpp) with a JSON-capable model:

```bash
llama-server -m /path/to/model.gguf --host 127.0.0.1 --port 8080
uv run evalforge run examples/invoice/local-openai.yaml --run-id local-YYYYMMDD
```

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
server returns. Local quality is not a claim until a real run is captured and
reviewed with this methodology.
