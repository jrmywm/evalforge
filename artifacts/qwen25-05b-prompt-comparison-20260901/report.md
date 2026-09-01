# EvalForge report: invoice-extraction-local-openai

**Decision:** `PASSED`

- Run: `qwen25-05b-prompt-comparison-20260901`
- Manifest digest: `df08280f7e7cd94c6b2fe4e1f0751ccac57d96114a8c42901508ca12dc3de7af`
- Dataset: version `1.0`, digest `88447e5966ff9f3504bcab97eb6df4468e50fd438cf3d13ee53dbc87fb83310a`

## Configuration comparison

| Configuration | Provider | Model | Cases passed | Schema validity | Field accuracy | P95 latency (ms) |
| --- | --- | --- | ---: | ---: | ---: | ---: |
| baseline | openai_compatible | qwen2.5-0.5b-instruct | 14/20 | 1.0 | 0.9 | 2753.2584000146016 |
| candidate | openai_compatible | qwen2.5-0.5b-instruct | 14/20 | 1.0 | 0.9 | 2441.524700028822 |

## Metric deltas

| Metric | Baseline | Candidate | Delta | Relative delta |
| --- | ---: | ---: | ---: | ---: |
| schema_validity | 1.0 | 1.0 | 0.0 | 0.0 |
| field_accuracy | 0.9 | 0.9 | 0.0 | 0.0 |
| p95_latency_ms | 2753.2584000146016 | 2441.524700028822 | -311.7336999857798 | -0.11322355358440987 |

## Quality gates

| Metric | Rule | Observed | Threshold | Result | Reason |
| --- | --- | ---: | ---: | --- | --- |
| baseline.field_accuracy | data_integrity | 0.0 | 0.0 | PASS | baseline has no missing evaluations |
| baseline.field_accuracy | data_integrity | 0.0 | 0.0 | PASS | baseline has no evaluator errors |
| baseline.schema_validity | data_integrity | 0.0 | 0.0 | PASS | baseline has no missing evaluations |
| baseline.schema_validity | data_integrity | 0.0 | 0.0 | PASS | baseline has no evaluator errors |
| candidate.field_accuracy | data_integrity | 0.0 | 0.0 | PASS | candidate has no missing evaluations |
| candidate.field_accuracy | data_integrity | 0.0 | 0.0 | PASS | candidate has no evaluator errors |
| candidate.schema_validity | data_integrity | 0.0 | 0.0 | PASS | candidate has no missing evaluations |
| candidate.schema_validity | data_integrity | 0.0 | 0.0 | PASS | candidate has no evaluator errors |
| field_accuracy | minimum | 0.9 | 0.9 | PASS | candidate field_accuracy meets minimum 0.9 |
| field_accuracy | maximum_regression | 0.0 | 0.01 | PASS | field_accuracy deterioration is within maximum 0.01 |
| p95_latency_ms | maximum | 2441.524700028822 | 10000.0 | PASS | candidate p95_latency_ms meets maximum 10000.0 |
| schema_validity | minimum | 1.0 | 1.0 | PASS | candidate schema_validity meets minimum 1.0 |

### Gate failures

None.

## Case transitions

- Newly failing: None
- Newly passing: None

## Failed cases

### `baseline` / `invoice-004`
Tags: ordinary, jpy
Description: Japanese yen without decimals.
Expected: `{"currency": "JPY", "invoice_number": "004-A", "total": 12000.0}`
Actual: `{"currency": "¥", "invoice_number": "004-A", "total": 12000}`
Raw response: `{"choices": [{"finish_reason": "stop", "index": 0, "message": {"content": "{\\n  \\"currency\\": \\"¥\\",\\n  \\"invoice_number\\": \\"004-A\\",\\n  \\"total\\": 12000\\n}", "role": "assistant"}}], "created": 1788240476, "id": "chatcmpl-9Mj6gtKjv4sMzgj5liF5oNf7FDhqA15z", "model": "local-model", "object": "chat.completion", "system_fingerprint": "b10727-ab0b3bd3c", "timings": {"cache_n": 44, "predicted_ms": 1451.586, "predicted_n": 36, "predicted_per_second": 24.111557978652318, "predicted_per_token_ms": 41.473885714285714, "prompt_ms": 817.733, "prompt_n": 76, "prompt_per_second": 92.93987157177222, "prompt_per_token_ms": 10.759644736842105}, "usage": {"completion_tokens": 36, "prompt_tokens": 120, "prompt_tokens_details": {"cached_tokens": 44}, "total_tokens": 156}}`
- Evaluator `field_accuracy` v`1.0`: `failed`, score `0.6666666666666666` - one or more expected fields do not match
  Details: `{"correct_fields": 2, "expected_fields": 3, "extra_fields": [], "mismatches": [{"actual": "¥", "expected": "JPY", "kind": "mismatch", "path": "/currency"}], "numeric_tolerance": 1e-06}`
- Evaluator `json_schema` v`1.0`: `passed`, score `1.0` - output is valid JSON and satisfies the configured JSON Schema
  Details: `{"schema_errors": []}`

### `baseline` / `invoice-005`
Tags: eur, decimal-comma, thousands
Description: German amount format.
Expected: `{"currency": "EUR", "invoice_number": "2026/005", "total": 1234.56}`
Actual: `{"currency": "EUR", "invoice_number": "2026/005", "total": 1.23456}`
Raw response: `{"choices": [{"finish_reason": "stop", "index": 0, "message": {"content": "{\\n  \\"currency\\": \\"EUR\\",\\n  \\"invoice_number\\": \\"2026/005\\",\\n  \\"total\\": 1.23456\\n}", "role": "assistant"}}], "created": 1788240478, "id": "chatcmpl-gnhKFVwLz09mT80I05tlqPtue7FNCjhK", "model": "local-model", "object": "chat.completion", "system_fingerprint": "b10727-ab0b3bd3c", "timings": {"cache_n": 44, "predicted_ms": 1794.22, "predicted_n": 42, "predicted_per_second": 22.851155376709656, "predicted_per_token_ms": 43.76146341463415, "prompt_ms": 829.58, "prompt_n": 86, "prompt_per_second": 103.66691578871236, "prompt_per_token_ms": 9.646279069767443}, "usage": {"completion_tokens": 42, "prompt_tokens": 130, "prompt_tokens_details": {"cached_tokens": 44}, "total_tokens": 172}}`
- Evaluator `field_accuracy` v`1.0`: `failed`, score `0.6666666666666666` - one or more expected fields do not match
  Details: `{"correct_fields": 2, "expected_fields": 3, "extra_fields": [], "mismatches": [{"actual": 1.23456, "expected": 1234.56, "kind": "mismatch", "path": "/total"}], "numeric_tolerance": 1e-06}`
- Evaluator `json_schema` v`1.0`: `passed`, score `1.0` - output is valid JSON and satisfies the configured JSON Schema
  Details: `{"schema_errors": []}`

### `baseline` / `invoice-011`
Tags: brl, decimal-comma
Description: Brazilian currency notation.
Expected: `{"currency": "BRL", "invoice_number": "011-B", "total": 88.7}`
Actual: `{"currency": "R$", "invoice_number": "011-B", "total": 88.7}`
Raw response: `{"choices": [{"finish_reason": "stop", "index": 0, "message": {"content": "{\\n  \\"currency\\": \\"R$\\",\\n  \\"invoice_number\\": \\"011-B\\",\\n  \\"total\\": 88.7\\n}", "role": "assistant"}}], "created": 1788240492, "id": "chatcmpl-uQKMq2aTMThXAvooLjHVndqwaLlwzhP8", "model": "local-model", "object": "chat.completion", "system_fingerprint": "b10727-ab0b3bd3c", "timings": {"cache_n": 43, "predicted_ms": 1263.478, "predicted_n": 36, "predicted_per_second": 27.701313358839645, "predicted_per_token_ms": 36.09937142857143, "prompt_ms": 690.457, "prompt_n": 79, "prompt_per_second": 114.41697310621807, "prompt_per_token_ms": 8.739962025316455}, "usage": {"completion_tokens": 36, "prompt_tokens": 122, "prompt_tokens_details": {"cached_tokens": 43}, "total_tokens": 158}}`
- Evaluator `field_accuracy` v`1.0`: `failed`, score `0.6666666666666666` - one or more expected fields do not match
  Details: `{"correct_fields": 2, "expected_fields": 3, "extra_fields": [], "mismatches": [{"actual": "R$", "expected": "BRL", "kind": "mismatch", "path": "/currency"}], "numeric_tolerance": 1e-06}`
- Evaluator `json_schema` v`1.0`: `passed`, score `1.0` - output is valid JSON and satisfies the configured JSON Schema
  Details: `{"schema_errors": []}`

### `baseline` / `invoice-015`
Tags: eur, thousands, decimal-comma
Description: Space thousands separator.
Expected: `{"currency": "EUR", "invoice_number": "015", "total": 4500.0}`
Actual: `{"currency": "EUR", "invoice_number": "015", "total": 4500000}`
Raw response: `{"choices": [{"finish_reason": "stop", "index": 0, "message": {"content": "{\\n  \\"currency\\": \\"EUR\\",\\n  \\"invoice_number\\": \\"015\\",\\n  \\"total\\": 4500000\\n}", "role": "assistant"}}], "created": 1788240499, "id": "chatcmpl-KGjQYCcvGqincChl065zdYk3rSGC6Nsz", "model": "local-model", "object": "chat.completion", "system_fingerprint": "b10727-ab0b3bd3c", "timings": {"cache_n": 47, "predicted_ms": 1297.843, "predicted_n": 37, "predicted_per_second": 27.738331986226378, "predicted_per_token_ms": 36.05119444444445, "prompt_ms": 651.902, "prompt_n": 75, "prompt_per_second": 115.04796733251315, "prompt_per_token_ms": 8.692026666666667}, "usage": {"completion_tokens": 37, "prompt_tokens": 122, "prompt_tokens_details": {"cached_tokens": 47}, "total_tokens": 159}}`
- Evaluator `field_accuracy` v`1.0`: `failed`, score `0.6666666666666666` - one or more expected fields do not match
  Details: `{"correct_fields": 2, "expected_fields": 3, "extra_fields": [], "mismatches": [{"actual": 4500000, "expected": 4500.0, "kind": "mismatch", "path": "/total"}], "numeric_tolerance": 1e-06}`
- Evaluator `json_schema` v`1.0`: `passed`, score `1.0` - output is valid JSON and satisfies the configured JSON Schema
  Details: `{"schema_errors": []}`

### `baseline` / `invoice-018`
Tags: sek, decimal-comma, thousands
Description: Swedish amount format.
Expected: `{"currency": "SEK", "invoice_number": "018", "total": 1200.0}`
Actual: `{"currency": "SEK", "invoice_number": "018", "total": 1200000}`
Raw response: `{"choices": [{"finish_reason": "stop", "index": 0, "message": {"content": "{\\n  \\"currency\\": \\"SEK\\",\\n  \\"invoice_number\\": \\"018\\",\\n  \\"total\\": 1200000\\n}", "role": "assistant"}}], "created": 1788240505, "id": "chatcmpl-m8bL7n1PawS9zakXAQ9PlOmhsqz8rJLq", "model": "local-model", "object": "chat.completion", "system_fingerprint": "b10727-ab0b3bd3c", "timings": {"cache_n": 44, "predicted_ms": 1151.645, "predicted_n": 38, "predicted_per_second": 32.12795609758216, "predicted_per_token_ms": 31.12554054054054, "prompt_ms": 908.367, "prompt_n": 86, "prompt_per_second": 94.6753900130674, "prompt_per_token_ms": 10.562406976744185}, "usage": {"completion_tokens": 38, "prompt_tokens": 130, "prompt_tokens_details": {"cached_tokens": 44}, "total_tokens": 168}}`
- Evaluator `field_accuracy` v`1.0`: `failed`, score `0.6666666666666666` - one or more expected fields do not match
  Details: `{"correct_fields": 2, "expected_fields": 3, "extra_fields": [], "mismatches": [{"actual": 1200000, "expected": 1200.0, "kind": "mismatch", "path": "/total"}], "numeric_tolerance": 1e-06}`
- Evaluator `json_schema` v`1.0`: `passed`, score `1.0` - output is valid JSON and satisfies the configured JSON Schema
  Details: `{"schema_errors": []}`

### `baseline` / `invoice-020`
Tags: duplicate-values, usd
Description: Final invoice value is required.
Expected: `{"currency": "USD", "invoice_number": "020-F", "total": 200.0}`
Actual: `{"currency": "USD", "invoice_number": "020", "total": 200.0}`
Raw response: `{"choices": [{"finish_reason": "stop", "index": 0, "message": {"content": "{\\n  \\"currency\\": \\"USD\\",\\n  \\"invoice_number\\": \\"020\\",\\n  \\"total\\": 200.00\\n}", "role": "assistant"}}], "created": 1788240509, "id": "chatcmpl-ivEFAoM6f00yJBjyvkZ39WAOZ4Rf7Xu7", "model": "local-model", "object": "chat.completion", "system_fingerprint": "b10727-ab0b3bd3c", "timings": {"cache_n": 43, "predicted_ms": 1362.805, "predicted_n": 36, "predicted_per_second": 25.682324323729365, "predicted_per_token_ms": 38.937285714285714, "prompt_ms": 749.454, "prompt_n": 85, "prompt_per_second": 113.4159001086124, "prompt_per_token_ms": 8.81710588235294}, "usage": {"completion_tokens": 36, "prompt_tokens": 128, "prompt_tokens_details": {"cached_tokens": 43}, "total_tokens": 164}}`
- Evaluator `field_accuracy` v`1.0`: `failed`, score `0.6666666666666666` - one or more expected fields do not match
  Details: `{"correct_fields": 2, "expected_fields": 3, "extra_fields": [], "mismatches": [{"actual": "020", "expected": "020-F", "kind": "mismatch", "path": "/invoice_number"}], "numeric_tolerance": 1e-06}`
- Evaluator `json_schema` v`1.0`: `passed`, score `1.0` - output is valid JSON and satisfies the configured JSON Schema
  Details: `{"schema_errors": []}`

### `candidate` / `invoice-004`
Tags: ordinary, jpy
Description: Japanese yen without decimals.
Expected: `{"currency": "JPY", "invoice_number": "004-A", "total": 12000.0}`
Actual: `{"currency": "USD", "invoice_number": "004-A", "total": 12000}`
Raw response: `{"choices": [{"finish_reason": "stop", "index": 0, "message": {"content": "{\\n  \\"currency\\": \\"USD\\",\\n  \\"invoice_number\\": \\"004-A\\",\\n  \\"total\\": 12000\\n}", "role": "assistant"}}], "created": 1788240518, "id": "chatcmpl-7qVxEFsBxhMgcQUr2bitwzPGR40PxxM2", "model": "local-model", "object": "chat.completion", "system_fingerprint": "b10727-ab0b3bd3c", "timings": {"cache_n": 82, "predicted_ms": 1132.819, "predicted_n": 36, "predicted_per_second": 30.896374442872165, "predicted_per_token_ms": 32.366257142857144, "prompt_ms": 685.81, "prompt_n": 76, "prompt_per_second": 110.81786500634287, "prompt_per_token_ms": 9.023815789473684}, "usage": {"completion_tokens": 36, "prompt_tokens": 158, "prompt_tokens_details": {"cached_tokens": 82}, "total_tokens": 194}}`
- Evaluator `field_accuracy` v`1.0`: `failed`, score `0.6666666666666666` - one or more expected fields do not match
  Details: `{"correct_fields": 2, "expected_fields": 3, "extra_fields": [], "mismatches": [{"actual": "USD", "expected": "JPY", "kind": "mismatch", "path": "/currency"}], "numeric_tolerance": 1e-06}`
- Evaluator `json_schema` v`1.0`: `passed`, score `1.0` - output is valid JSON and satisfies the configured JSON Schema
  Details: `{"schema_errors": []}`

### `candidate` / `invoice-005`
Tags: eur, decimal-comma, thousands
Description: German amount format.
Expected: `{"currency": "EUR", "invoice_number": "2026/005", "total": 1234.56}`
Actual: `{"currency": "EUR", "invoice_number": "2026/005", "total": 1.23456}`
Raw response: `{"choices": [{"finish_reason": "stop", "index": 0, "message": {"content": "{\\n  \\"currency\\": \\"EUR\\",\\n  \\"invoice_number\\": \\"2026/005\\",\\n  \\"total\\": 1.23456\\n}", "role": "assistant"}}], "created": 1788240520, "id": "chatcmpl-KHLWdOQl5VSbZXQIj3IlOFVoIC0kW773", "model": "local-model", "object": "chat.completion", "system_fingerprint": "b10727-ab0b3bd3c", "timings": {"cache_n": 82, "predicted_ms": 1301.209, "predicted_n": 42, "predicted_per_second": 31.509158021501538, "predicted_per_token_ms": 31.736804878048783, "prompt_ms": 757.179, "prompt_n": 86, "prompt_per_second": 113.57948384728051, "prompt_per_token_ms": 8.804406976744186}, "usage": {"completion_tokens": 42, "prompt_tokens": 168, "prompt_tokens_details": {"cached_tokens": 82}, "total_tokens": 210}}`
- Evaluator `field_accuracy` v`1.0`: `failed`, score `0.6666666666666666` - one or more expected fields do not match
  Details: `{"correct_fields": 2, "expected_fields": 3, "extra_fields": [], "mismatches": [{"actual": 1.23456, "expected": 1234.56, "kind": "mismatch", "path": "/total"}], "numeric_tolerance": 1e-06}`
- Evaluator `json_schema` v`1.0`: `passed`, score `1.0` - output is valid JSON and satisfies the configured JSON Schema
  Details: `{"schema_errors": []}`

### `candidate` / `invoice-011`
Tags: brl, decimal-comma
Description: Brazilian currency notation.
Expected: `{"currency": "BRL", "invoice_number": "011-B", "total": 88.7}`
Actual: `{"currency": "R$", "invoice_number": "011-B", "total": 88.7}`
Raw response: `{"choices": [{"finish_reason": "stop", "index": 0, "message": {"content": "{\\n  \\"currency\\": \\"R$\\",\\n  \\"invoice_number\\": \\"011-B\\",\\n  \\"total\\": 88.7\\n}", "role": "assistant"}}], "created": 1788240532, "id": "chatcmpl-EZOWamPS5cfbdRZoL4Os8ymp45AWnPdV", "model": "local-model", "object": "chat.completion", "system_fingerprint": "b10727-ab0b3bd3c", "timings": {"cache_n": 81, "predicted_ms": 1303.187, "predicted_n": 36, "predicted_per_second": 26.857235377578203, "predicted_per_token_ms": 37.233914285714285, "prompt_ms": 727.478, "prompt_n": 79, "prompt_per_second": 108.59434924492562, "prompt_per_token_ms": 9.208582278481012}, "usage": {"completion_tokens": 36, "prompt_tokens": 160, "prompt_tokens_details": {"cached_tokens": 81}, "total_tokens": 196}}`
- Evaluator `field_accuracy` v`1.0`: `failed`, score `0.6666666666666666` - one or more expected fields do not match
  Details: `{"correct_fields": 2, "expected_fields": 3, "extra_fields": [], "mismatches": [{"actual": "R$", "expected": "BRL", "kind": "mismatch", "path": "/currency"}], "numeric_tolerance": 1e-06}`
- Evaluator `json_schema` v`1.0`: `passed`, score `1.0` - output is valid JSON and satisfies the configured JSON Schema
  Details: `{"schema_errors": []}`

### `candidate` / `invoice-015`
Tags: eur, thousands, decimal-comma
Description: Space thousands separator.
Expected: `{"currency": "EUR", "invoice_number": "015", "total": 4500.0}`
Actual: `{"currency": "EUR", "invoice_number": "015", "total": 4500000}`
Raw response: `{"choices": [{"finish_reason": "stop", "index": 0, "message": {"content": "{\\n  \\"currency\\": \\"EUR\\",\\n  \\"invoice_number\\": \\"015\\",\\n  \\"total\\": 4500000\\n}", "role": "assistant"}}], "created": 1788240540, "id": "chatcmpl-dWZ4pE5iD1jVYOQtsRpb5mwG5MgIHJHq", "model": "local-model", "object": "chat.completion", "system_fingerprint": "b10727-ab0b3bd3c", "timings": {"cache_n": 85, "predicted_ms": 1635.205, "predicted_n": 37, "predicted_per_second": 22.01558825957602, "predicted_per_token_ms": 45.42236111111111, "prompt_ms": 755.271, "prompt_n": 75, "prompt_per_second": 99.3021048074135, "prompt_per_token_ms": 10.070279999999999}, "usage": {"completion_tokens": 37, "prompt_tokens": 160, "prompt_tokens_details": {"cached_tokens": 85}, "total_tokens": 197}}`
- Evaluator `field_accuracy` v`1.0`: `failed`, score `0.6666666666666666` - one or more expected fields do not match
  Details: `{"correct_fields": 2, "expected_fields": 3, "extra_fields": [], "mismatches": [{"actual": 4500000, "expected": 4500.0, "kind": "mismatch", "path": "/total"}], "numeric_tolerance": 1e-06}`
- Evaluator `json_schema` v`1.0`: `passed`, score `1.0` - output is valid JSON and satisfies the configured JSON Schema
  Details: `{"schema_errors": []}`

### `candidate` / `invoice-018`
Tags: sek, decimal-comma, thousands
Description: Swedish amount format.
Expected: `{"currency": "SEK", "invoice_number": "018", "total": 1200.0}`
Actual: `{"currency": "SEK", "invoice_number": "018", "total": 1200000}`
Raw response: `{"choices": [{"finish_reason": "stop", "index": 0, "message": {"content": "{\\n  \\"currency\\": \\"SEK\\",\\n  \\"invoice_number\\": \\"018\\",\\n  \\"total\\": 1200000\\n}", "role": "assistant"}}], "created": 1788240549, "id": "chatcmpl-gw00QsbENXYjDDixXnNFteqkvFgpS0bY", "model": "local-model", "object": "chat.completion", "system_fingerprint": "b10727-ab0b3bd3c", "timings": {"cache_n": 82, "predicted_ms": 1347.892, "predicted_n": 38, "predicted_per_second": 27.45027049644927, "predicted_per_token_ms": 36.42951351351351, "prompt_ms": 753.931, "prompt_n": 86, "prompt_per_second": 114.06879409388922, "prompt_per_token_ms": 8.766639534883721}, "usage": {"completion_tokens": 38, "prompt_tokens": 168, "prompt_tokens_details": {"cached_tokens": 82}, "total_tokens": 206}}`
- Evaluator `field_accuracy` v`1.0`: `failed`, score `0.6666666666666666` - one or more expected fields do not match
  Details: `{"correct_fields": 2, "expected_fields": 3, "extra_fields": [], "mismatches": [{"actual": 1200000, "expected": 1200.0, "kind": "mismatch", "path": "/total"}], "numeric_tolerance": 1e-06}`
- Evaluator `json_schema` v`1.0`: `passed`, score `1.0` - output is valid JSON and satisfies the configured JSON Schema
  Details: `{"schema_errors": []}`

### `candidate` / `invoice-020`
Tags: duplicate-values, usd
Description: Final invoice value is required.
Expected: `{"currency": "USD", "invoice_number": "020-F", "total": 200.0}`
Actual: `{"currency": "USD", "invoice_number": "020", "total": 200.0}`
Raw response: `{"choices": [{"finish_reason": "stop", "index": 0, "message": {"content": "{\\n  \\"currency\\": \\"USD\\",\\n  \\"invoice_number\\": \\"020\\",\\n  \\"total\\": 200.00\\n}", "role": "assistant"}}], "created": 1788240553, "id": "chatcmpl-3Zvz3kVwm38U49wzKXfh9sFv2QBL5gaa", "model": "local-model", "object": "chat.completion", "system_fingerprint": "b10727-ab0b3bd3c", "timings": {"cache_n": 81, "predicted_ms": 1192.073, "predicted_n": 36, "predicted_per_second": 29.360618015842988, "predicted_per_token_ms": 34.05922857142858, "prompt_ms": 786.625, "prompt_n": 85, "prompt_per_second": 108.05657079294454, "prompt_per_token_ms": 9.254411764705882}, "usage": {"completion_tokens": 36, "prompt_tokens": 166, "prompt_tokens_details": {"cached_tokens": 81}, "total_tokens": 202}}`
- Evaluator `field_accuracy` v`1.0`: `failed`, score `0.6666666666666666` - one or more expected fields do not match
  Details: `{"correct_fields": 2, "expected_fields": 3, "extra_fields": [], "mismatches": [{"actual": "020", "expected": "020-F", "kind": "mismatch", "path": "/invoice_number"}], "numeric_tolerance": 1e-06}`
- Evaluator `json_schema` v`1.0`: `passed`, score `1.0` - output is valid JSON and satisfies the configured JSON Schema
  Details: `{"schema_errors": []}`
