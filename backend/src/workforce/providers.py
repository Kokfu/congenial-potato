"""Application-owned conversation provider boundary. No live adapters are registered."""
from datetime import datetime, timezone
from decimal import Decimal
from enum import StrEnum
from collections.abc import Iterator
from typing import Literal, Protocol

from pydantic import BaseModel, Field


class ProviderErrorKind(StrEnum):
    AUTH = 'auth'
    UNAVAILABLE_MODEL = 'unavailable_model'
    RATE_LIMIT = 'rate_limit'
    TIMEOUT = 'timeout'
    TRANSIENT = 'transient'
    INVALID_REQUEST = 'invalid_request'
    CAPABILITY = 'capability_mismatch'
    MALFORMED_RESPONSE = 'malformed_response'
    CANCELLED = 'cancelled'


class ProviderError(Exception):
    def __init__(self, kind: ProviderErrorKind, message: str, retryable: bool = False):
        super().__init__(message)
        self.kind = kind
        self.retryable = retryable


class Capabilities(BaseModel):
    text_input: bool = True
    text_output: bool = True
    tool_calls: bool = False
    structured_output: bool = False
    usage_reported: bool = False
    max_input_tokens: int = Field(gt=0)
    max_output_tokens: int = Field(gt=0)


class CatalogModel(BaseModel):
    model_id: str
    capabilities: Capabilities | None = None


class CatalogSnapshot(BaseModel):
    connection_id: str
    origin: str
    observed_at: datetime
    models: tuple[CatalogModel, ...]


class TextMessage(BaseModel):
    role: Literal['system', 'user', 'assistant', 'tool']
    text: str = Field(min_length=1, max_length=20000)
    trust_origin: Literal['human', 'agent', 'external', 'tool']


class GenerationRequest(BaseModel):
    request_id: str
    model_id: str
    messages: tuple[TextMessage, ...] = Field(min_length=1)
    max_output_tokens: int = Field(gt=0)
    require_tools: bool = False
    require_structured_output: bool = False
    deadline_at: datetime | None = None

    @property
    def input_text(self) -> str:
        return '\n'.join(message.text for message in self.messages)


class Usage(BaseModel):
    # input_tokens is the inclusive count used by cost calculation. Provider
    # cache/reasoning breakdowns are recorded separately for provenance.
    input_tokens: int | None = Field(default=None, ge=0)
    output_tokens: int | None = Field(default=None, ge=0)
    cached_input_tokens: int | None = Field(default=None, ge=0)
    cache_creation_input_tokens: int | None = Field(default=None, ge=0)
    reasoning_output_tokens: int | None = Field(default=None, ge=0)
    reported_cost_usd: Decimal | None = Field(default=None, ge=0)


class UsageEstimate(BaseModel):
    input_tokens: int = Field(ge=0)
    output_tokens_upper_bound: int = Field(ge=0)
    cost_upper_bound_usd: Decimal | None = Field(default=None, ge=0)


class GenerationResponse(BaseModel):
    content: str
    actual_model: str
    provider_request_id: str | None = None
    finish_reason: str
    usage: Usage


class StreamEvent(BaseModel):
    kind: Literal['text_delta', 'final']
    text: str | None = None
    response: GenerationResponse | None = None


class ProviderAdapter(Protocol):
    connection_id: str

    def discover_models(self, refresh: bool = False) -> CatalogSnapshot: ...
    def describe_capabilities(self, model_id: str) -> Capabilities: ...
    def generate(self, request: GenerationRequest) -> GenerationResponse: ...
    def stream(self, request: GenerationRequest) -> Iterator[StreamEvent]: ...
    def estimate_usage(self, request: GenerationRequest) -> UsageEstimate: ...
    def cancel(self, request_id: str) -> bool: ...
    def health(self) -> str: ...


class FakeAdapter:
    """A deterministic contract fixture with an explicitly refreshable catalog."""
    def __init__(self, connection_id: str, models: tuple[CatalogModel, ...], failure_kind: ProviderErrorKind | None = None):
        self.connection_id = connection_id
        self._models = models
        self._catalog: CatalogSnapshot | None = None
        self._failure_kind = failure_kind

    def discover_models(self, refresh: bool = False) -> CatalogSnapshot:
        if refresh or self._catalog is None:
            self._catalog = CatalogSnapshot(connection_id=self.connection_id, origin='fixture',
                                            observed_at=datetime.now(timezone.utc), models=self._models)
        return self._catalog

    def describe_capabilities(self, model_id: str) -> Capabilities:
        for model in self.discover_models().models:
            if model.model_id == model_id:
                if model.capabilities is None:
                    raise ProviderError(ProviderErrorKind.CAPABILITY, 'Model capabilities are unvalidated')
                return model.capabilities
        raise ProviderError(ProviderErrorKind.UNAVAILABLE_MODEL, 'Model is not available')

    def _validate(self, request: GenerationRequest) -> Capabilities:
        if request.deadline_at is not None:
            if request.deadline_at.tzinfo is None or request.deadline_at <= datetime.now(timezone.utc):
                raise ProviderError(ProviderErrorKind.TIMEOUT, 'Model call deadline expired')
        cap = self.describe_capabilities(request.model_id)
        if (not cap.text_input or not cap.text_output or
            request.max_output_tokens > cap.max_output_tokens or
            (request.require_tools and not cap.tool_calls) or
            (request.require_structured_output and not cap.structured_output)):
            raise ProviderError(ProviderErrorKind.CAPABILITY, 'Requested capability is unavailable')
        if len(request.input_text) // 4 + 1 > cap.max_input_tokens:
            raise ProviderError(ProviderErrorKind.INVALID_REQUEST, 'Input exceeds model limit')
        return cap

    def estimate_usage(self, request: GenerationRequest) -> UsageEstimate:
        self._validate(request)
        return UsageEstimate(input_tokens=len(request.input_text) // 4 + 1,
                             output_tokens_upper_bound=request.max_output_tokens, cost_upper_bound_usd=None)

    def generate(self, request: GenerationRequest) -> GenerationResponse:
        self._validate(request)
        if self._failure_kind is not None:
            raise ProviderError(self._failure_kind, 'Synthetic provider failure')
        return GenerationResponse(content=f'Synthetic result for execution {request.request_id}',
                                  actual_model=request.model_id,
                                  provider_request_id=f'fixture:{self.connection_id}:{request.request_id}',
                                  finish_reason='stop',
                                  usage=Usage(input_tokens=len(request.input_text) // 4 + 1,
                                              output_tokens=8, reported_cost_usd=None))

    def stream(self, request: GenerationRequest) -> Iterator[StreamEvent]:
        response = self.generate(request)
        yield StreamEvent(kind='text_delta', text=response.content)
        yield StreamEvent(kind='final', response=response)

    def cancel(self, request_id: str) -> bool:
        return True

    def health(self) -> str:
        return 'fixture_ready'


class StructuredFixtureAdapter(FakeAdapter):
    """Echo a synthetic JSON fixture through the provider response boundary."""
    prefix: str

    def generate(self, request: GenerationRequest) -> GenerationResponse:
        self._validate(request)
        instruction = next((message.text for message in request.messages
                            if message.role == 'system'), '')
        if not instruction.startswith(self.prefix):
            raise ProviderError(ProviderErrorKind.INVALID_REQUEST,
                                'Fixture structured response is unavailable')
        content = instruction[len(self.prefix):].strip()
        return GenerationResponse(content=content, actual_model=request.model_id,
                                  provider_request_id=f'fixture:{self.connection_id}:{request.request_id}',
                                  finish_reason='stop',
                                  usage=Usage(input_tokens=len(request.input_text) // 4 + 1,
                                              output_tokens=len(content) // 4 + 1))


class CollaborationFixtureAdapter(StructuredFixtureAdapter):
    prefix = 'FIXTURE_COLLAB_JSON:'


class MemoryFixtureAdapter(StructuredFixtureAdapter):
    prefix = 'FIXTURE_MEMORY_JSON:'


class ToolFixtureAdapter(StructuredFixtureAdapter):
    prefix = 'FIXTURE_TOOL_JSON:'


class ProviderRegistry:
    def __init__(self, adapters: tuple[ProviderAdapter, ...]):
        self._adapters = {adapter.connection_id: adapter for adapter in adapters}
        if len(self._adapters) != len(adapters):
            raise ValueError('Duplicate provider connection')

    def get(self, connection_id: str) -> ProviderAdapter:
        try:
            return self._adapters[connection_id]
        except KeyError as exc:
            raise ProviderError(ProviderErrorKind.INVALID_REQUEST, 'Provider connection is unavailable') from exc

    def connections(self) -> tuple[str, ...]:
        return tuple(self._adapters)


def fixture_registry() -> ProviderRegistry:
    base = Capabilities(max_input_tokens=4096, max_output_tokens=512, usage_reported=True)
    advanced = Capabilities(max_input_tokens=8192, max_output_tokens=1024,
                            tool_calls=True, structured_output=True, usage_reported=True)
    return ProviderRegistry((
        FakeAdapter('fixture', (CatalogModel(model_id='fake-v1', capabilities=base),)),
        FakeAdapter('fixture-alpha', (CatalogModel(model_id='alpha-text-v1', capabilities=base),)),
        FakeAdapter('fixture-beta', (CatalogModel(model_id='beta-tools-v1', capabilities=advanced),)),
        CollaborationFixtureAdapter('fixture-collaboration', (
            CatalogModel(model_id='collaboration-v1', capabilities=advanced),)),
        MemoryFixtureAdapter('fixture-memory', (
            CatalogModel(model_id='memory-v1', capabilities=advanced),)),
        ToolFixtureAdapter('fixture-tool', (
            CatalogModel(model_id='tool-v1', capabilities=advanced),)),
        FakeAdapter('fixture-timeout', (CatalogModel(model_id='timeout-v1', capabilities=base),),
                    failure_kind=ProviderErrorKind.TIMEOUT),
    ))


registry = fixture_registry()
