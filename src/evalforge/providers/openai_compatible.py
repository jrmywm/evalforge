"""Stdlib OpenAI-compatible chat-completions provider for local inference."""

from __future__ import annotations

import hashlib
import json
import os
import time
from collections.abc import Callable, Mapping
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from evalforge.config import OpenAICompatibleOptions
from evalforge.json_types import thaw_json
from evalforge.providers.base import NormalizedRequest, ProviderResponse, UsageMetadata


class OpenAICompatibleError(Exception):
    """Safe structured failure raised by the OpenAI-compatible provider."""

    def __init__(
        self,
        message: str,
        *,
        error_type: str,
        retryable: bool = False,
        details: Mapping[str, Any] | None = None,
    ) -> None:
        super().__init__(message)
        self.error_type = error_type
        self.retryable = retryable
        self.details = dict(details or {})


def _reject_json_constant(value: str) -> None:
    raise ValueError(f"nonstandard JSON constant {value!r}")


def _redact(value: Any, secret: str | None) -> Any:
    """Keep raw evidence useful while ensuring an API key cannot be persisted."""
    if isinstance(value, str):
        return value.replace(secret, "[REDACTED]") if secret else value
    if isinstance(value, list):
        return [_redact(item, secret) for item in value]
    if isinstance(value, dict):
        result: dict[str, Any] = {}
        for key, item in value.items():
            if str(key).lower() in {"authorization", "api_key", "apikey", "access_token"}:
                result[str(key)] = "[REDACTED]"
            else:
                result[str(key)] = _redact(item, secret)
        return result
    return value


def _raw_bytes_details(response_bytes: bytes, secret: str | None) -> dict[str, Any]:
    """Return bounded evidence for bytes that cannot be parsed as JSON text."""
    preview = response_bytes.decode("utf-8", errors="replace")[:2048]
    return {
        "raw_response_preview": _redact(preview, secret),
        "raw_response_sha256": hashlib.sha256(response_bytes).hexdigest(),
        "raw_response_bytes": len(response_bytes),
    }


class OpenAICompatibleProvider:
    """Call a non-streaming ``/v1/chat/completions`` compatible endpoint."""

    name = "openai_compatible"
    _forwarded_parameters = frozenset(
        {
            "frequency_penalty",
            "max_completion_tokens",
            "max_tokens",
            "presence_penalty",
            "seed",
            "stop",
            "temperature",
            "top_p",
        }
    )

    def __init__(
        self,
        model: str,
        *,
        options: OpenAICompatibleOptions | Mapping[str, Any] | None = None,
        sleeper: Callable[[float], None] = time.sleep,
        opener: Callable[..., Any] = urlopen,
        backoff_seconds: float = 0.25,
    ) -> None:
        if not model.strip():
            raise ValueError("model must be nonblank")
        self.model = model
        self.options = (
            options
            if isinstance(options, OpenAICompatibleOptions)
            else OpenAICompatibleOptions.model_validate(options or {})
        )
        self._sleeper = sleeper
        self._opener = opener
        self._backoff_seconds = backoff_seconds

    def _request_body(self, request: NormalizedRequest) -> dict[str, Any]:
        input_json = json.dumps(
            thaw_json(request.input), ensure_ascii=False, sort_keys=True, separators=(",", ":")
        )
        schema_json = json.dumps(
            thaw_json(request.output_schema),
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        )
        content = "\n\n".join(
            part
            for part in (
                request.prompt.strip(),
                f"Input JSON:\n{input_json}",
                "Return only a valid JSON object matching this output schema "
                f"(do not include markdown fences):\n{schema_json}",
            )
            if part
        )
        body: dict[str, Any] = {
            "model": self.model,
            "messages": [{"role": "user", "content": content}],
            "stream": False,
        }
        for name in sorted(self._forwarded_parameters):
            if name in request.inference_parameters:
                body[name] = thaw_json(request.inference_parameters[name])
        if self.options.json_response:
            body["response_format"] = {
                "type": "json_schema",
                "json_schema": {
                    "name": "evalforge_output",
                    "strict": True,
                    "schema": thaw_json(request.output_schema),
                },
            }
        return body

    def _headers(self) -> tuple[dict[str, str], str | None]:
        headers = {"Content-Type": "application/json", "Accept": "application/json"}
        secret: str | None = None
        if self.options.api_key_env is not None:
            secret = os.environ.get(self.options.api_key_env)
            if not secret:
                raise OpenAICompatibleError(
                    "configured API key environment variable is not set",
                    error_type="authentication_error",
                    details={"env_var": self.options.api_key_env},
                )
            headers["Authorization"] = f"Bearer {secret}"
        return headers, secret

    def _single_attempt(self, request: NormalizedRequest) -> ProviderResponse:
        headers, secret = self._headers()
        payload = json.dumps(
            self._request_body(request), ensure_ascii=False, sort_keys=True, separators=(",", ":")
        ).encode("utf-8")
        http_request = Request(
            f"{self.options.base_url}/chat/completions",
            data=payload,
            headers=headers,
            method="POST",
        )
        try:
            with self._opener(http_request, timeout=self.options.timeout) as response:
                status_value = getattr(response, "status", None)
                status = int(status_value if status_value is not None else response.getcode())
                response_bytes = response.read()
        except HTTPError as error:
            raise OpenAICompatibleError(
                f"OpenAI-compatible endpoint returned HTTP {error.code}",
                error_type="http_error",
                retryable=error.code == 429 or error.code >= 500,
                details={"status_code": error.code},
            ) from error
        except TimeoutError as error:
            raise OpenAICompatibleError(
                "OpenAI-compatible endpoint timed out",
                error_type="timeout",
                retryable=True,
            ) from error
        except URLError as error:
            if isinstance(error.reason, TimeoutError):
                raise OpenAICompatibleError(
                    "OpenAI-compatible endpoint timed out",
                    error_type="timeout",
                    retryable=True,
                ) from error
            raise OpenAICompatibleError(
                "could not connect to OpenAI-compatible endpoint",
                error_type="network_error",
                details={"reason_type": type(error.reason).__name__},
            ) from error
        except OSError as error:
            raise OpenAICompatibleError(
                "could not connect to OpenAI-compatible endpoint",
                error_type="network_error",
                details={"reason_type": type(error).__name__},
            ) from error

        if status < 200 or status >= 300:
            raise OpenAICompatibleError(
                f"OpenAI-compatible endpoint returned HTTP {status}",
                error_type="http_error",
                retryable=status == 429 or status >= 500,
                details={"status_code": status},
            )
        try:
            response_text = response_bytes.decode("utf-8")
        except UnicodeDecodeError as error:
            raise OpenAICompatibleError(
                "endpoint returned undecodable response bytes",
                error_type="malformed_response",
                details=_raw_bytes_details(response_bytes, secret),
            ) from error
        try:
            decoded = json.loads(response_text, parse_constant=_reject_json_constant)
        except (json.JSONDecodeError, ValueError) as error:
            raise OpenAICompatibleError(
                "endpoint returned malformed JSON",
                error_type="malformed_response",
                details=_raw_bytes_details(response_bytes, secret),
            ) from error
        if not isinstance(decoded, dict):
            raise OpenAICompatibleError(
                "endpoint response must be a JSON object",
                error_type="malformed_response",
                details={"raw_response": _redact(decoded, secret)},
            )
        response_details = {"raw_response": _redact(decoded, secret)}
        resolved_model = decoded.get("model")
        choices = decoded.get("choices")
        if not isinstance(resolved_model, str) or not resolved_model.strip():
            raise OpenAICompatibleError(
                "endpoint response is missing a resolved model",
                error_type="malformed_response",
                details=response_details,
            )
        if not isinstance(choices, list) or not choices or not isinstance(choices[0], dict):
            raise OpenAICompatibleError(
                "endpoint response is missing choices",
                error_type="malformed_response",
                details=response_details,
            )
        message = choices[0].get("message")
        content = message.get("content") if isinstance(message, dict) else None
        if not isinstance(content, (str, dict, list)):
            raise OpenAICompatibleError(
                "endpoint response is missing message content",
                error_type="malformed_response",
                details=response_details,
            )
        try:
            output = (
                json.loads(content, parse_constant=_reject_json_constant)
                if isinstance(content, str)
                else content
            )
        except (json.JSONDecodeError, ValueError) as error:
            raise OpenAICompatibleError(
                "endpoint message content is not valid JSON",
                error_type="malformed_response",
                details=response_details,
            ) from error

        usage_data = decoded.get("usage")
        usage: UsageMetadata | None = None
        if usage_data is not None:
            if not isinstance(usage_data, dict):
                raise OpenAICompatibleError(
                    "endpoint usage must be an object",
                    error_type="malformed_response",
                    details=response_details,
                )
            try:
                usage = UsageMetadata.model_validate(
                    {
                        "input_tokens": usage_data.get(
                            "input_tokens", usage_data.get("prompt_tokens")
                        ),
                        "output_tokens": usage_data.get(
                            "output_tokens", usage_data.get("completion_tokens")
                        ),
                        "total_tokens": usage_data.get("total_tokens"),
                    }
                )
            except ValueError as error:
                raise OpenAICompatibleError(
                    "endpoint usage contains invalid token counts",
                    error_type="malformed_response",
                    details=response_details,
                ) from error
        return ProviderResponse(
            output=output,
            raw_output=_redact(decoded, secret),
            resolved_model=resolved_model,
            usage=usage,
        )

    def generate(self, request: NormalizedRequest) -> ProviderResponse:
        """Generate one response, retrying only explicitly transient failures."""
        for attempt in range(self.options.retries + 1):
            try:
                return self._single_attempt(request)
            except OpenAICompatibleError as error:
                if not error.retryable or attempt >= self.options.retries:
                    raise
                self._sleeper(self._backoff_seconds * (2**attempt))
        raise AssertionError("retry loop must return or raise")
