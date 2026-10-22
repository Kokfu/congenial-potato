"""Pure preparation contracts: no clients, credentials, I/O or provider registration."""
import json
from datetime import datetime, timezone
from typing import Literal
from pydantic import BaseModel, ConfigDict, Field
from .providers import GenerationRequest


class TextContractError(ValueError):
    pass


class OfflineTextResult(BaseModel):
    model_config = ConfigDict(strict=True, extra='forbid')
    content: str = Field(min_length=1, max_length=20000)
    actual_model: str = Field(min_length=1, max_length=240)
    provider_request_id: str = Field(min_length=1, max_length=240)
    input_tokens: int | None
    output_tokens: int | None
    cached_input_tokens: int | None
    reasoning_output_tokens: int | None
    billing_ready: Literal[False] = False


def _fail():
    raise TextContractError('Unsupported or malformed offline text contract')


def _request(request: GenerationRequest, model: str):
    if (request.model_id != model or request.max_output_tokens > 1024 or
            request.require_tools or request.require_structured_output or request.fixture_document is not None or
            not request.messages or any(m.role == 'tool' or
                (m.role == 'system' and m.trust_origin != 'human') for m in request.messages)):
        _fail()
    if request.deadline_at is not None and (request.deadline_at.utcoffset() is None or
            request.deadline_at <= datetime.now(timezone.utc)):
        _fail()


def _bounded(body):
    if len(json.dumps(body, ensure_ascii=False).encode()) > 8192:
        _fail()
    return body


def deepseek_text_request(request: GenerationRequest) -> dict:
    _request(request, 'deepseek-flash')
    return _bounded({'model': request.model_id,
        'messages': [{'role': m.role, 'content': m.text} for m in request.messages],
        'max_tokens': request.max_output_tokens, 'stream': False, 'thinking': {'type': 'disabled'}})


def gemini_text_request(request: GenerationRequest) -> dict:
    _request(request, 'gemini-3.8-flash')
    # Moving a later system instruction to the front would silently change ordering.
    system, contents = [], []
    for message in request.messages:
        if message.role == 'system':
            if contents:
                _fail()
            system.append({'text': message.text})
        else:
            contents.append({'role': 'model' if message.role == 'assistant' else 'user',
                             'parts': [{'text': message.text}]})
    if not contents:
        _fail()
    body = {'contents': contents, 'generationConfig': {'candidateCount': 1,
        'maxOutputTokens': request.max_output_tokens, 'thinkingConfig': {'thinkingLevel': 'low'}}}
    if system:
        body['systemInstruction'] = {'parts': system}
    return _bounded(body)


def _count(values, key):
    value = values.get(key)
    if value is not None and (type(value) is not int or value < 0):
        _fail()
    return value


def _total(values, key, *parts):
    total = _count(values, key)
    if total is not None and all(part is not None for part in parts) and total != sum(parts):
        _fail()


def _result(**values):
    try:
        return OfflineTextResult(**values)
    except ValueError:
        _fail()


def parse_deepseek_text(payload: dict) -> OfflineTextResult:
    try:
        choices = payload['choices']
        if len(choices) != 1 or choices[0]['finish_reason'] != 'stop':
            _fail()
        message = choices[0]['message']
        if (message['role'] != 'assistant' or message.get('tool_calls') or
                message.get('function_call') or message.get('reasoning_content')):
            _fail()
        usage = payload.get('usage') or {}
        inputs, outputs = _count(usage, 'prompt_tokens'), _count(usage, 'completion_tokens')
        cached = _count(usage, 'prompt_cache_hit_tokens')
        missed = _count(usage, 'prompt_cache_miss_tokens')
        if inputs is not None and cached is not None and cached > inputs:
            _fail()
        _total(usage, 'prompt_tokens', cached, missed)
        _total(usage, 'total_tokens', inputs, outputs)
        return _result(content=message['content'], actual_model=payload['model'],
            provider_request_id=payload['id'], input_tokens=inputs, output_tokens=outputs,
            cached_input_tokens=cached, reasoning_output_tokens=None)
    except (KeyError, TypeError, IndexError, AttributeError):
        _fail()


def parse_gemini_text(payload: dict) -> OfflineTextResult:
    try:
        candidates = payload['candidates']
        if len(candidates) != 1 or candidates[0]['finishReason'] != 'STOP' or payload.get('promptFeedback', {}).get('blockReason'):
            _fail()
        candidate = candidates[0]
        if candidate.get('groundingMetadata') or candidate.get('urlContextMetadata'):
            _fail()
        content = candidate['content']
        if content['role'] != 'model' or not content['parts']:
            _fail()
        texts = []
        for part in content['parts']:
            if set(part) != {'text'} or not isinstance(part['text'], str):
                _fail()
            texts.append(part['text'])
        usage = payload.get('usageMetadata') or {}
        inputs = _count(usage, 'promptTokenCount')
        visible = _count(usage, 'candidatesTokenCount')
        thoughts = _count(usage, 'thoughtsTokenCount')
        cached = _count(usage, 'cachedContentTokenCount')
        tools = _count(usage, 'toolUsePromptTokenCount')
        if tools not in (None, 0) or (inputs is not None and cached is not None and cached > inputs):
            _fail()
        # Missing thinking usage is unknown, not zero. Never understate billable output.
        outputs = visible + thoughts if visible is not None and thoughts is not None else None
        _total(usage, 'totalTokenCount', inputs, outputs)
        return _result(content=''.join(texts), actual_model=payload['modelVersion'],
            provider_request_id=payload['responseId'], input_tokens=inputs, output_tokens=outputs,
            cached_input_tokens=cached, reasoning_output_tokens=thoughts)
    except (KeyError, TypeError, IndexError, AttributeError):
        _fail()
