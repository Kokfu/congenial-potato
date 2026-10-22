"""Offline SDK contract tests: every provider request is intercepted in memory."""
import json
import os
from datetime import datetime, timedelta, timezone

import anthropic
import httpx2
import openai
import pytest

from workforce.native_providers import AnthropicTextAdapter, OpenAITextAdapter
from workforce.providers import Capabilities, GenerationRequest, ProviderError, ProviderErrorKind, TextMessage

CAPABILITIES = Capabilities(max_input_tokens=4096, max_output_tokens=256, usage_reported=True)
REQUEST = GenerationRequest(request_id='offline-fixture', model_id='fixture-model', max_output_tokens=32,
                            messages=(TextMessage(role='system', trust_origin='human', text='Stay concise.'),
                                      TextMessage(role='user', trust_origin='human', text='Say hello.')))


def test_openai_sdk_326_response_and_catalog_are_normalized_offline():
    calls = []

    def handler(request):
        calls.append((request.url.path, json.loads(request.content) if request.content else None))
        if request.url.path == '/v1/models':
            return httpx2.Response(200, json={'object': 'list', 'data': [
                {'id': 'fixture-model', 'object': 'model', 'created': 0, 'owned_by': 'fixture'},
                {'id': 'unvalidated-model', 'object': 'model', 'created': 0, 'owned_by': 'fixture'}]})
        return httpx2.Response(200, json={'id': 'resp_fixture', 'object': 'response', 'created_at': 0,
            'status': 'completed', 'model': 'fixture-model', 'output': [{'id': 'msg_fixture', 'type': 'message',
            'role': 'assistant', 'status': 'completed', 'content': [{'type': 'output_text', 'text': 'Hello', 'annotations': []}]}],
            'usage': {'input_tokens': 4, 'output_tokens': 2, 'total_tokens': 6,
                      'input_tokens_details': {'cached_tokens': 1, 'cache_write_tokens': 1},
                      'output_tokens_details': {'reasoning_tokens': 1}}})

    client = openai.OpenAI(api_key='offline-fixture', max_retries=0,
                           http_client=httpx2.Client(transport=httpx2.MockTransport(handler)))
    adapter = OpenAITextAdapter({'fixture-model': CAPABILITIES}, client=client)
    catalog = adapter.discover_models(refresh=True)
    assert catalog.origin == 'provider_list+operator_validation'
    assert next(m for m in catalog.models if m.model_id == 'unvalidated-model').capabilities is None
    with pytest.raises(ProviderError) as unvalidated:
        adapter.describe_capabilities('unvalidated-model')
    assert unvalidated.value.kind == ProviderErrorKind.CAPABILITY
    response = adapter.generate(REQUEST.model_copy(update={
        'deadline_at': datetime.now(timezone.utc) + timedelta(seconds=20)}))
    assert (response.content, response.actual_model, response.provider_request_id) == ('Hello', 'fixture-model', 'resp_fixture')
    assert response.usage.input_tokens == 4 and response.usage.reported_cost_usd is None
    assert (response.usage.cached_input_tokens, response.usage.cache_creation_input_tokens,
            response.usage.reasoning_output_tokens) == (1, 1, 1)
    assert calls[1][1]['store'] is False
    assert calls[1][1]['input'][0]['role'] == 'system'


def test_anthropic_sdk_111_message_and_catalog_are_normalized_offline():
    calls = []

    def handler(request):
        calls.append((request.url.path, json.loads(request.content) if request.content else None))
        if request.url.path == '/v1/models':
            return httpx2.Response(200, json={'data': [{'id': 'fixture-model', 'type': 'model',
                'display_name': 'Fixture', 'created_at': '2026-10-07T00:00:00Z'}],
                'has_more': False, 'first_id': 'fixture-model', 'last_id': 'fixture-model'})
        return httpx2.Response(200, json={'id': 'msg_fixture', 'type': 'message', 'role': 'assistant',
            'model': 'fixture-model', 'content': [{'type': 'text', 'text': 'Hello'}],
            'stop_reason': 'end_turn', 'stop_sequence': None, 'usage': {
                'input_tokens': 4, 'cache_creation_input_tokens': 2, 'cache_read_input_tokens': 3,
                'output_tokens': 2, 'output_tokens_details': {'thinking_tokens': 1}}})

    client = anthropic.Anthropic(api_key='offline-fixture', max_retries=0,
                                 http_client=httpx2.Client(transport=httpx2.MockTransport(handler)))
    adapter = AnthropicTextAdapter({'fixture-model': CAPABILITIES}, client=client)
    assert adapter.discover_models(refresh=True).models[0].model_id == 'fixture-model'
    response = adapter.generate(REQUEST.model_copy(update={
        'deadline_at': datetime.now(timezone.utc) + timedelta(seconds=20)}))
    assert (response.content, response.actual_model, response.provider_request_id) == ('Hello', 'fixture-model', 'msg_fixture')
    assert (response.usage.input_tokens, response.usage.output_tokens,
            response.usage.cache_creation_input_tokens, response.usage.cached_input_tokens,
            response.usage.reasoning_output_tokens) == (9, 2, 2, 3, 1)
    assert response.usage.reported_cost_usd is None
    assert calls[1][1]['system'] == 'Stay concise.'
    assert calls[1][1]['messages'][0]['role'] == 'user'


def test_native_adapter_requires_validated_capabilities_and_normalizes_rate_limit():
    def rate_limit(_request):
        return httpx2.Response(429, json={'error': {'type': 'rate_limit_error', 'message': 'fixture only'}})

    client = openai.OpenAI(api_key='offline-fixture', max_retries=0,
                           http_client=httpx2.Client(transport=httpx2.MockTransport(rate_limit)))
    with pytest.raises(ProviderError) as missing:
        OpenAITextAdapter({}, client=client).generate(REQUEST)
    assert missing.value.kind == ProviderErrorKind.CAPABILITY
    with pytest.raises(ProviderError) as limited:
        OpenAITextAdapter({'fixture-model': CAPABILITIES}, client=client).generate(REQUEST)
    assert limited.value.kind == ProviderErrorKind.RATE_LIMIT and limited.value.retryable
    assert 'fixture only' not in str(limited.value)


def test_native_credentials_require_private_absolute_file(tmp_path):
    secret = tmp_path / 'provider-key'
    secret.write_text('offline-fixture-key')
    secret.chmod(0o644)
    with pytest.raises(ValueError, match='group/world'):
        OpenAITextAdapter({}, secret_file=secret)
    secret.chmod(0o600)
    assert OpenAITextAdapter({}, secret_file=secret).health() == 'configured_no_network_probe'
    assert AnthropicTextAdapter({}, secret_file=secret).health() == 'configured_no_network_probe'
    with pytest.raises(ValueError, match='absolute'):
        OpenAITextAdapter({}, secret_file=type(secret)('relative-key'))


def test_native_secret_reader_rejects_links_special_files_and_oversize(tmp_path):
    secret = tmp_path / 'private-key'
    secret.write_text('synthetic-private-key\n')
    secret.chmod(0o600)
    link = tmp_path / 'link'
    link.symlink_to(secret)
    with pytest.raises(ValueError, match='unavailable') as linked:
        OpenAITextAdapter({}, secret_file=link)
    assert 'synthetic-private-key' not in str(linked.value)
    with pytest.raises(ValueError, match='regular file'):
        AnthropicTextAdapter({}, secret_file=tmp_path)
    pipe = tmp_path / 'pipe'
    os.mkfifo(pipe, 0o600)
    with pytest.raises(ValueError, match='regular file'):
        OpenAITextAdapter({}, secret_file=pipe)
    secret.write_bytes(b'x' * 8193)
    with pytest.raises(ValueError, match='too large'):
        OpenAITextAdapter({}, secret_file=secret)


def test_native_secret_reader_accepts_one_line_only(tmp_path):
    secret = tmp_path / 'private-key'
    secret.write_text('synthetic-private-key\nnext-line')
    secret.chmod(0o600)
    with pytest.raises(ValueError, match='one nonempty line') as multiline:
        AnthropicTextAdapter({}, secret_file=secret)
    assert 'synthetic-private-key' not in str(multiline.value)
    secret.write_bytes(b'synthetic\x00key')
    with pytest.raises(ValueError, match='one nonempty line'):
        OpenAITextAdapter({}, secret_file=secret)
    secret.write_bytes(b'\xff')
    with pytest.raises(ValueError, match='UTF-8'):
        OpenAITextAdapter({}, secret_file=secret)
    secret.write_text('synthetic-private-key\n')
    secret.chmod(0o400)
    assert OpenAITextAdapter({}, secret_file=secret).health() == 'configured_no_network_probe'


def test_anthropic_auth_failure_and_native_streaming_fail_closed():
    def unauthorized(_request):
        return httpx2.Response(401, json={'type': 'error',
            'error': {'type': 'authentication_error', 'message': 'offline secret text'}})

    client = anthropic.Anthropic(api_key='offline-fixture', max_retries=0,
                                 http_client=httpx2.Client(transport=httpx2.MockTransport(unauthorized)))
    adapter = AnthropicTextAdapter({'fixture-model': CAPABILITIES}, client=client)
    with pytest.raises(ProviderError) as denied:
        adapter.generate(REQUEST)
    assert denied.value.kind == ProviderErrorKind.AUTH and not denied.value.retryable
    assert 'offline secret text' not in str(denied.value)
    with pytest.raises(ProviderError) as unsupported:
        adapter.stream(REQUEST)
    assert unsupported.value.kind == ProviderErrorKind.CAPABILITY


def test_native_deadline_expires_without_network_request():
    calls = []
    def handler(request):
        calls.append(request)
        raise AssertionError('Expired deadline reached network transport')
    past = REQUEST.model_copy(update={'deadline_at': datetime.now(timezone.utc) - timedelta(seconds=1)})
    openai_client = openai.OpenAI(api_key='offline-fixture', max_retries=0,
                                 http_client=httpx2.Client(transport=httpx2.MockTransport(handler)))
    anthropic_client = anthropic.Anthropic(api_key='offline-fixture', max_retries=0,
                                           http_client=httpx2.Client(transport=httpx2.MockTransport(handler)))
    for adapter in (OpenAITextAdapter({'fixture-model': CAPABILITIES}, client=openai_client),
                    AnthropicTextAdapter({'fixture-model': CAPABILITIES}, client=anthropic_client)):
        with pytest.raises(ProviderError) as expired:
            adapter.generate(past)
        assert expired.value.kind == ProviderErrorKind.TIMEOUT
    assert not calls


@pytest.mark.parametrize('kind', ['openai', 'anthropic'])
@pytest.mark.parametrize('failure', ['rate_limit', 'service', 'timeout', 'connection'])
@pytest.mark.parametrize('deadline', [False, True])
def test_injected_sdk_retry_defaults_never_resend_generation(kind, failure, deadline):
    calls = []

    def handle(request):
        calls.append(request)
        if failure == 'timeout':
            raise httpx2.ReadTimeout('synthetic secret must not escape', request=request)
        if failure == 'connection':
            raise httpx2.ConnectError('synthetic secret must not escape', request=request)
        return httpx2.Response(429 if failure == 'rate_limit' else 503,
            json={'error': {'type': 'api_error', 'message': 'synthetic secret must not escape'}})

    constructor, adapter_type = ((openai.OpenAI, OpenAITextAdapter) if kind == 'openai'
                                else (anthropic.Anthropic, AnthropicTextAdapter))
    client = constructor(
        api_key='offline-fixture', max_retries=2,
        http_client=httpx2.Client(transport=httpx2.MockTransport(handle)))
    adapter = adapter_type({'fixture-model': CAPABILITIES}, client=client)
    request = REQUEST.model_copy(update={'deadline_at': datetime.now(timezone.utc) + timedelta(seconds=20)}) if deadline else REQUEST
    # The adapter must override the injected policy on both deadline paths.
    with pytest.raises(ProviderError) as error:
        adapter.generate(request)
    expected = {'rate_limit': ProviderErrorKind.RATE_LIMIT, 'service': ProviderErrorKind.TRANSIENT,
                'timeout': ProviderErrorKind.TIMEOUT, 'connection': ProviderErrorKind.TRANSIENT}
    assert error.value.kind == expected[failure]
    assert len(calls) == 1 and client.max_retries == 2
    assert 'synthetic secret' not in str(error.value)


@pytest.mark.parametrize('kind', ['openai', 'anthropic'])
def test_catalog_failure_does_not_inherit_sdk_retries(kind):
    calls = []

    def handle(request):
        calls.append(request)
        return httpx2.Response(503, json={'error': {'type': 'api_error', 'message': 'offline'}})

    constructor = openai.OpenAI if kind == 'openai' else anthropic.Anthropic
    client = constructor(api_key='offline-fixture', max_retries=2,
        http_client=httpx2.Client(transport=httpx2.MockTransport(handle)))
    adapter_type = OpenAITextAdapter if kind == 'openai' else AnthropicTextAdapter
    with pytest.raises(ProviderError):
        adapter_type({}, client=client).discover_models()
    assert len(calls) == 1 and client.max_retries == 2
