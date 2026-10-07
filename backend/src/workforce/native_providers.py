"""Text-only native SDK adapters. Deliberately unregistered until live budget gates exist."""
from collections.abc import Iterator
from datetime import datetime, timezone
import os
from pathlib import Path
import stat

import anthropic
import openai

from .providers import (Capabilities, CatalogModel, CatalogSnapshot, GenerationRequest,
                        GenerationResponse, ProviderError, ProviderErrorKind, StreamEvent,
                        Usage, UsageEstimate)


def _read_secret(path: Path | None) -> str:
    if path is None or not path.is_absolute():
        raise ValueError('An absolute private secret file reference is required')
    if not hasattr(os, 'O_NOFOLLOW'):
        raise ValueError('Provider secret file requires no-follow file opening')
    try:
        fd = os.open(path, os.O_RDONLY | os.O_CLOEXEC | os.O_NONBLOCK | os.O_NOFOLLOW)
    except (OSError, ValueError):
        raise ValueError('Provider secret file is unavailable') from None
    try:
        info = os.fstat(fd)
        if not stat.S_ISREG(info.st_mode):
            raise ValueError('Provider secret must be a regular file')
        if info.st_uid not in (0, os.getuid()):
            raise ValueError('Provider secret file owner is not trusted')
        if info.st_mode & 0o077:
            raise ValueError('Provider secret file must not be group/world readable')
        if info.st_size > 8192:
            raise ValueError('Provider secret file is too large')
        chunks = bytearray()
        while len(chunks) <= 8192:
            part = os.read(fd, 8193 - len(chunks))
            if not part:
                break
            chunks.extend(part)
        if len(chunks) > 8192:
            raise ValueError('Provider secret file is too large')
        raw = bytes(chunks).removesuffix(b'\n')
        if not raw.strip() or b'\n' in raw or b'\r' in raw or b'\x00' in raw:
            raise ValueError('Provider secret file must contain one nonempty line')
        try:
            return raw.decode('utf-8')
        except UnicodeDecodeError:
            raise ValueError('Provider secret file is not UTF-8') from None
    finally:
        os.close(fd)


def _api_error(error: Exception, sdk: str) -> ProviderError:
    namespace = openai if sdk == 'openai' else anthropic
    if isinstance(error, namespace.APITimeoutError):
        return ProviderError(ProviderErrorKind.TIMEOUT, 'Provider request timed out', retryable=True)
    if isinstance(error, namespace.APIConnectionError):
        return ProviderError(ProviderErrorKind.TRANSIENT, 'Provider connection failed', retryable=True)
    if isinstance(error, namespace.APIStatusError):
        status = error.status_code
        if status in (401, 403):
            return ProviderError(ProviderErrorKind.AUTH, 'Provider authentication failed')
        if status == 404:
            return ProviderError(ProviderErrorKind.UNAVAILABLE_MODEL, 'Provider model unavailable')
        if status == 429:
            return ProviderError(ProviderErrorKind.RATE_LIMIT, 'Provider rate limit', retryable=True)
        if status >= 500:
            return ProviderError(ProviderErrorKind.TRANSIENT, 'Provider service failure', retryable=True)
        return ProviderError(ProviderErrorKind.INVALID_REQUEST, 'Provider rejected request')
    return ProviderError(ProviderErrorKind.MALFORMED_RESPONSE, 'Provider SDK failure')


def _remaining_timeout(request: GenerationRequest) -> float | None:
    if request.deadline_at is None:
        return None
    if request.deadline_at.tzinfo is None:
        raise ProviderError(ProviderErrorKind.INVALID_REQUEST, 'Deadline must include a timezone')
    seconds = (request.deadline_at - datetime.now(timezone.utc)).total_seconds()
    if seconds <= 0:
        raise ProviderError(ProviderErrorKind.TIMEOUT, 'Model call deadline expired')
    return seconds


class NativeTextAdapter:
    connection_id: str

    def __init__(self, validated_models: dict[str, Capabilities]):
        self._validated_models = dict(validated_models)
        self._catalog: CatalogSnapshot | None = None

    def describe_capabilities(self, model_id: str) -> Capabilities:
        try:
            return self._validated_models[model_id]
        except KeyError as exc:
            raise ProviderError(ProviderErrorKind.CAPABILITY, 'Model capabilities are unvalidated') from exc

    def _validate(self, request: GenerationRequest) -> None:
        cap = self.describe_capabilities(request.model_id)
        if (not cap.text_input or not cap.text_output or request.max_output_tokens > cap.max_output_tokens or
            request.require_tools or request.require_structured_output or
            any(message.role == 'tool' for message in request.messages)):
            raise ProviderError(ProviderErrorKind.CAPABILITY, 'Requested capability is unavailable')
        # A byte can be a token. Reject inputs that cannot fit the declared bound.
        if len(request.input_text.encode()) > cap.max_input_tokens:
            raise ProviderError(ProviderErrorKind.INVALID_REQUEST, 'Input exceeds validated model limit')

    def estimate_usage(self, request: GenerationRequest) -> UsageEstimate:
        self._validate(request)
        return UsageEstimate(input_tokens=len(request.input_text.encode()),
                             output_tokens_upper_bound=request.max_output_tokens,
                             cost_upper_bound_usd=None)

    def stream(self, request: GenerationRequest) -> Iterator[StreamEvent]:
        raise ProviderError(ProviderErrorKind.CAPABILITY, 'Native streaming is not validated')

    def cancel(self, request_id: str) -> bool:
        return False

    def health(self) -> str:
        return 'configured_no_network_probe'

    def _catalog_from_ids(self, ids: list[str], refresh: bool) -> CatalogSnapshot:
        if refresh or self._catalog is None:
            all_ids = sorted(set(ids) | set(self._validated_models))
            self._catalog = CatalogSnapshot(connection_id=self.connection_id, origin='provider_list+operator_validation',
                                            observed_at=datetime.now(timezone.utc),
                                            models=tuple(CatalogModel(model_id=model_id,
                                                                      capabilities=self._validated_models.get(model_id))
                                                         for model_id in all_ids))
        return self._catalog


class OpenAITextAdapter(NativeTextAdapter):
    connection_id = 'openai-native'

    def __init__(self, validated_models: dict[str, Capabilities], *, secret_file: Path | None = None,
                 client: openai.OpenAI | None = None):
        super().__init__(validated_models)
        self._client = client or openai.OpenAI(api_key=_read_secret(secret_file), max_retries=0, timeout=20)

    def discover_models(self, refresh: bool = False) -> CatalogSnapshot:
        if self._catalog is not None and not refresh:
            return self._catalog
        try:
            ids = [model.id for model in self._client.models.list().data]
        except openai.OpenAIError as exc:
            raise _api_error(exc, 'openai') from None
        return self._catalog_from_ids(ids, refresh)

    def generate(self, request: GenerationRequest) -> GenerationResponse:
        self._validate(request)
        timeout = _remaining_timeout(request)
        content = [{'role': message.role, 'content': message.text} for message in request.messages]
        try:
            client = self._client.with_options(timeout=timeout) if timeout is not None else self._client
            response = client.responses.create(model=request.model_id, input=content,
                                                      max_output_tokens=request.max_output_tokens,
                                                      store=False)
        except openai.OpenAIError as exc:
            raise _api_error(exc, 'openai') from None
        if response.status != 'completed' or not response.output_text:
            raise ProviderError(ProviderErrorKind.MALFORMED_RESPONSE, 'Provider returned no completed text')
        usage = response.usage
        return GenerationResponse(content=response.output_text, actual_model=response.model,
                                  provider_request_id=response.id, finish_reason=response.status,
                                  usage=Usage(input_tokens=usage.input_tokens if usage else None,
                                              output_tokens=usage.output_tokens if usage else None,
                                              reported_cost_usd=None))


class AnthropicTextAdapter(NativeTextAdapter):
    connection_id = 'anthropic-native'

    def __init__(self, validated_models: dict[str, Capabilities], *, secret_file: Path | None = None,
                 client: anthropic.Anthropic | None = None):
        super().__init__(validated_models)
        self._client = client or anthropic.Anthropic(api_key=_read_secret(secret_file), max_retries=0, timeout=20)

    def discover_models(self, refresh: bool = False) -> CatalogSnapshot:
        if self._catalog is not None and not refresh:
            return self._catalog
        try:
            ids = [model.id for model in self._client.models.list().data]
        except anthropic.AnthropicError as exc:
            raise _api_error(exc, 'anthropic') from None
        return self._catalog_from_ids(ids, refresh)

    def generate(self, request: GenerationRequest) -> GenerationResponse:
        self._validate(request)
        timeout = _remaining_timeout(request)
        system = '\n'.join(message.text for message in request.messages if message.role == 'system')
        messages = [{'role': message.role, 'content': message.text}
                    for message in request.messages if message.role != 'system']
        if not messages:
            raise ProviderError(ProviderErrorKind.INVALID_REQUEST, 'User or assistant content required')
        try:
            client = self._client.with_options(timeout=timeout) if timeout is not None else self._client
            kwargs = {'model': request.model_id, 'messages': messages, 'max_tokens': request.max_output_tokens}
            if system:
                kwargs['system'] = system
            response = client.messages.create(**kwargs)
        except anthropic.AnthropicError as exc:
            raise _api_error(exc, 'anthropic') from None
        if not response.content or any(block.type != 'text' for block in response.content):
            raise ProviderError(ProviderErrorKind.MALFORMED_RESPONSE, 'Provider returned non-text content')
        output = ''.join(block.text for block in response.content)
        if not output:
            raise ProviderError(ProviderErrorKind.MALFORMED_RESPONSE, 'Provider returned empty text')
        return GenerationResponse(content=output, actual_model=response.model,
                                  provider_request_id=response.id, finish_reason=response.stop_reason or 'unknown',
                                  usage=Usage(input_tokens=response.usage.input_tokens,
                                              output_tokens=response.usage.output_tokens,
                                              reported_cost_usd=None))
