"""Deterministic cited text fixture; no inference or external effects."""
import json
from pydantic import BaseModel, ConfigDict, Field


class FixtureDocument(BaseModel):
    model_config = ConfigDict(extra='forbid', strict=True)
    plan_id: str = Field(min_length=1, max_length=36)
    plan_digest: str = Field(pattern=r'^[a-f0-9]{64}$')
    title: str = Field(min_length=1, max_length=240)
    project_id: str = Field(min_length=1, max_length=36)
    brief_revision: int = Field(ge=1)
    brief_digest: str = Field(pattern=r'^[a-f0-9]{64}$')
    context_digest: str = Field(pattern=r'^[a-f0-9]{64}$')
    source_prefix: str = Field(max_length=6000)


def render_document_fixture(data: FixtureDocument) -> str:
    def render(count):
        return ('# Synthetic document draft\n\n'
            'Local fixture only; this is not model-written analysis.\n\n'
            f'Reviewed work: {json.dumps(data.title, ensure_ascii=False)}\n\n'
            '## Quoted source excerpt [S1]\n'
            f'{json.dumps(data.source_prefix[:count], ensure_ascii=False)}\n\n'
            'The excerpt may omit supplied notes. Facts, owners and dates outside it remain unknown.\n\n'
            '## Recorded references\n'
            f'[S1] Project {data.project_id}; brief revision {data.brief_revision}; '
            f'full-source SHA-256 {data.brief_digest}.\n'
            f'Prepared context SHA-256: {data.context_digest}.\n'
            f'Reviewed plan: {data.plan_id}; payload SHA-256 {data.plan_digest}.\n')
    count = min(400, len(data.source_prefix))
    while count and len(render(count)) > 1800:
        count //= 2
    result = render(count)
    if len(result) > 1800:
        raise ValueError('Fixture document metadata exceeds output bound')
    return result
