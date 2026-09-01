"""Offline in-process tests for the OpenAI-compatible local provider."""

from __future__ import annotations

import hashlib
import json
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any

import yaml
from typer.testing import CliRunner

from evalforge.cli import app
from evalforge.config import OpenAICompatibleOptions
from evalforge.json_types import thaw_json
from evalforge.providers import (
    NormalizedRequest,
    OpenAICompatibleError,
    OpenAICompatibleProvider,
)

RUNNER = CliRunner()


class StubState:
    def __init__(self, responses: list[tuple[int, dict[str, Any]]]) -> None:
        self.responses = responses
        self.requests: list[tuple[dict[str, str], dict[str, Any]]] = []


def _server(state: StubState) -> tuple[ThreadingHTTPServer, threading.Thread]:
    class Handler(BaseHTTPRequestHandler):
        def do_POST(self) -> None:  # noqa: N802 - stdlib handler API
            length = int(self.headers["Content-Length"])
            body = json.loads(self.rfile.read(length))
            state.requests.append((dict(self.headers), body))
            status, response = state.responses.pop(0)
            encoded = json.dumps(response).encode("utf-8")
            self.send_response(status)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(encoded)))
            self.end_headers()
            self.wfile.write(encoded)

        def log_message(self, *_args: object) -> None:
            return

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    return server, thread


def _request() -> NormalizedRequest:
    return NormalizedRequest(
        experiment="stub",
        configuration="baseline",
        case_id="case-1",
        model="local-model",
        prompt="Extract fields.",
        input={"text": "invoice 1"},
        output_schema={"type": "object", "properties": {"value": {"type": "string"}}},
        inference_parameters={"temperature": 0.0, "unsafe": "not-forwarded"},
    )


def _response(*, model: str = "resolved-local") -> dict[str, Any]:
    return {
        "id": "chatcmpl-stub",
        "model": model,
        "choices": [{"index": 0, "message": {"role": "assistant", "content": '{"value":"ok"}'}}],
        "usage": {"prompt_tokens": 7, "completion_tokens": 3, "total_tokens": 10},
    }


def test_success_is_structured_raw_and_deterministic() -> None:
    state = StubState([(200, _response()) for _ in range(40)])
    server, thread = _server(state)
    try:
        provider = OpenAICompatibleProvider(
            "local-model",
            options=OpenAICompatibleOptions(
                base_url=f"http://127.0.0.1:{server.server_port}/v1", retries=0
            ),
        )
        first = provider.generate(_request())
        second = provider.generate(_request())
    finally:
        server.shutdown()
        thread.join()

    assert first.output == second.output == {"value": "ok"}
    assert first.resolved_model == "resolved-local"
    assert first.usage is not None and first.usage.total_tokens == 10
    assert first.raw_output["id"] == "chatcmpl-stub"
    assert state.requests[0][1] == state.requests[1][1]
    assert state.requests[0][1]["stream"] is False
    assert state.requests[0][1]["response_format"] == {
        "type": "json_schema",
        "json_schema": {
            "name": "evalforge_output",
            "strict": True,
            "schema": _request().output_schema,
        },
    }
    assert "unsafe" not in state.requests[0][1]
    assert "ok" not in json.dumps(state.requests[0][1])


def test_only_transient_http_failures_are_retried() -> None:
    state = StubState([(500, {}), (429, {}), (200, _response())])
    server, thread = _server(state)
    sleeps: list[float] = []
    try:
        provider = OpenAICompatibleProvider(
            "local-model",
            options=OpenAICompatibleOptions(
                base_url=f"http://127.0.0.1:{server.server_port}/v1", retries=2
            ),
            sleeper=sleeps.append,
        )
        result = provider.generate(_request())
    finally:
        server.shutdown()
        thread.join()
    assert result.output == {"value": "ok"}
    assert sleeps == [0.25, 0.5]
    assert len(state.requests) == 3

    state = StubState([(400, {})])
    server, thread = _server(state)
    try:
        provider = OpenAICompatibleProvider(
            "local-model",
            options=OpenAICompatibleOptions(
                base_url=f"http://127.0.0.1:{server.server_port}/v1", retries=3
            ),
            sleeper=lambda _: sleeps.append(99),
        )
        try:
            provider.generate(_request())
        except OpenAICompatibleError as error:
            assert error.error_type == "http_error"
            assert not error.retryable
        else:
            raise AssertionError("expected HTTP 400 to fail")
    finally:
        server.shutdown()
        thread.join()
    assert len(state.requests) == 1


def test_auth_header_is_used_but_secret_is_not_raw_evidence(monkeypatch: Any) -> None:
    secret = "test-secret-value"
    monkeypatch.setenv("EVALFORGE_TEST_KEY", secret)
    response = _response()
    response["authorization"] = f"Bearer {secret}"
    state = StubState([(200, response)])
    server, thread = _server(state)
    try:
        provider = OpenAICompatibleProvider(
            "local-model",
            options=OpenAICompatibleOptions(
                base_url=f"http://127.0.0.1:{server.server_port}/v1",
                api_key_env="EVALFORGE_TEST_KEY",
                retries=0,
            ),
        )
        result = provider.generate(_request())
    finally:
        server.shutdown()
        thread.join()
    assert state.requests[0][0]["Authorization"] == f"Bearer {secret}"
    assert secret not in json.dumps(thaw_json(result.raw_output))
    assert result.raw_output["authorization"] == "[REDACTED]"


def test_malformed_response_is_a_structured_nonretryable_error() -> None:
    state = StubState([(200, {"model": "resolved-local", "choices": []})])
    server, thread = _server(state)
    try:
        provider = OpenAICompatibleProvider(
            "local-model",
            options={"base_url": f"http://127.0.0.1:{server.server_port}/v1", "retries": 1},
        )
        try:
            provider.generate(_request())
        except OpenAICompatibleError as error:
            assert error.error_type == "malformed_response"
            assert not error.retryable
        else:
            raise AssertionError("expected malformed response")
    finally:
        server.shutdown()
        thread.join()


def test_malformed_content_preserves_redacted_decoded_response(monkeypatch: Any) -> None:
    secret = "embedded-test-secret"
    response = _response()
    response["debug"] = secret
    response["choices"][0]["message"]["content"] = '```json\n{"value":"ok"}\n```'
    state = StubState([(200, response)])
    monkeypatch.setenv("EVALFORGE_TEST_KEY", secret)
    server, thread = _server(state)
    try:
        provider = OpenAICompatibleProvider(
            "local-model",
            options=OpenAICompatibleOptions(
                base_url=f"http://127.0.0.1:{server.server_port}/v1",
                api_key_env="EVALFORGE_TEST_KEY",
                retries=0,
            ),
        )
        try:
            provider.generate(_request())
        except OpenAICompatibleError as error:
            assert error.details["raw_response"]["debug"] == "[REDACTED]"
            assert "```json" in error.details["raw_response"]["choices"][0]["message"]["content"]
            assert secret not in json.dumps(error.details)
        else:
            raise AssertionError("expected fenced JSON to fail normalized parsing")
    finally:
        server.shutdown()
        thread.join()


def test_undecodable_response_has_bounded_hashed_redacted_evidence(monkeypatch: Any) -> None:
    secret = "undecodable-test-secret"
    response_bytes = b"\xff" + secret.encode() + b"\xfe" + b"x" * 3000

    class Response:
        status = 200

        def __enter__(self) -> Response:
            return self

        def __exit__(self, *_args: object) -> None:
            return None

        def read(self) -> bytes:
            return response_bytes

    monkeypatch.setenv("EVALFORGE_TEST_KEY", secret)
    provider = OpenAICompatibleProvider(
        "local-model",
        options=OpenAICompatibleOptions(api_key_env="EVALFORGE_TEST_KEY", retries=0),
        opener=lambda *_args, **_kwargs: Response(),
    )
    try:
        provider.generate(_request())
    except OpenAICompatibleError as error:
        assert error.details["raw_response_bytes"] == len(response_bytes)
        assert error.details["raw_response_sha256"] == hashlib.sha256(response_bytes).hexdigest()
        assert len(error.details["raw_response_preview"]) <= 2048
        assert secret not in error.details["raw_response_preview"]
    else:
        raise AssertionError("expected undecodable response to fail")


def _write_local_manifest(tmp_path: Path, base_url: str, *, fast_failure: bool = False) -> Path:
    source = yaml.safe_load(Path("examples/invoice/local-openai.yaml").read_text(encoding="utf-8"))
    source["dataset"]["path"] = str(Path("examples/invoice/dataset.jsonl").resolve())
    if fast_failure:
        one_case = tmp_path / "one-case.jsonl"
        one_case.write_text(
            Path("examples/invoice/dataset.jsonl").read_text(encoding="utf-8").splitlines()[0]
            + "\n",
            encoding="utf-8",
        )
        source["dataset"]["path"] = str(one_case)
    for config in source["configurations"].values():
        config["provider_options"]["base_url"] = base_url
        config["provider_options"]["retries"] = 0
        if fast_failure:
            config["provider_options"]["timeout"] = 0.1
    source["output_schema"] = {
        "type": "object",
        "required": ["value"],
        "properties": {"value": {"type": "string"}},
    }
    source["quality_gates"]["field_accuracy"]["minimum"] = 0.0
    path = tmp_path / "local.yaml"
    path.write_text(yaml.safe_dump(source, sort_keys=False), encoding="utf-8")
    return path


def test_cli_local_stub_round_trip_and_unavailable_endpoint(tmp_path: Path) -> None:
    state = StubState([(200, _response()) for _ in range(40)])
    server, thread = _server(state)
    try:
        manifest_path = _write_local_manifest(tmp_path, f"http://127.0.0.1:{server.server_port}/v1")
        result = RUNNER.invoke(
            app,
            [
                "run",
                str(manifest_path),
                "--artifact-root",
                str(tmp_path / "artifacts"),
                "--run-id",
                "stub",
            ],
        )
    finally:
        server.shutdown()
        thread.join()
    assert result.exit_code == 0, result.stdout + result.stderr
    report = json.loads(
        (tmp_path / "artifacts" / "stub" / "experiment.json").read_text(encoding="utf-8")
    )
    assert report["configurations"][0]["generations"][0]["resolved_model"] == "resolved-local"
    assert report["configurations"][0]["generations"][0]["usage"]["total_tokens"] == 10
    assert len(state.requests) == 40
    assert state.requests[0][1]["model"] == state.requests[20][1]["model"]
    assert state.requests[0][1]["response_format"] == state.requests[20][1]["response_format"]
    assert state.requests[0][1]["messages"] != state.requests[20][1]["messages"]

    unavailable_manifest = _write_local_manifest(
        tmp_path, "http://127.0.0.1:9/v1", fast_failure=True
    )
    unavailable = RUNNER.invoke(
        app,
        [
            "run",
            str(unavailable_manifest),
            "--artifact-root",
            str(tmp_path / "unavailable"),
            "--run-id",
            "offline",
        ],
    )
    assert unavailable.exit_code == 2
    assert "endpoint unavailable" in unavailable.stderr
    assert "Decision:" not in unavailable.stdout
