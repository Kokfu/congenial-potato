"""Offline SDK contract tests: every provider request is intercepted in memory."""
import json
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
            'usage': {'input_tokens': 4, 'output_tokens': 2, 'total_tokens': 6}})

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
            'stop_reason': 'end_turn', 'stop_sequence': None, 'usage': {'input_tokens': 4, 'output_tokens': 2}})

    client = anthropic.Anthropic(api_key='offline-fixture', max_retries=0,
                                 http_client=httpx2.Client(transport=httpx2.MockTransport(handler)))
    adapter = AnthropicTextAdapter({'fixture-model': CAPABILITIES}, client=client)
    assert adapter.discover_models(refresh=True).models[0].model_id == 'fixture-model'
    response = adapter.generate(REQUEST.model_copy(update={
        'deadline_at': datetime.now(timezone.utc) + timedelta(seconds=20)}))
    assert (response.content, response.actual_model, response.provider_request_id) == ('Hello', 'fixture-model', 'msg_fixture')
    assert response.usage.output_tokens == 2 and response.usage.reported_cost_usd is None
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
