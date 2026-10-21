"""Fresh admission/result checks for explicit, unpriced text-fixture drafts."""
import json
from sqlalchemy import select

from .document_draft_contract import FixtureDocument
from .models import (AgentConfigVersion, DocumentDraftRun, DocumentPlanTask, Execution,
    ExecutionBriefContext, PlanProposal, Task, TaskAssignment)
from .plans import document_source, plan_hash, PlanError
from .execution_briefs import source_record, BriefSourceError
from .services import authorize_agent_project

TEXT_FIXTURES = frozenset({'fixture', 'fixture-alpha', 'fixture-beta'})


class DocumentDraftError(ValueError):
    pass


def checked_plan(db, task, expected_hash, *, authority=True):
    association = db.get(DocumentPlanTask, task.id)
    plan = db.get(PlanProposal, association.proposal_id, populate_existing=True) if association else None
    if (plan is None or plan.status != 'admitted' or plan.project_id != task.project_id or
            plan.payload_hash != expected_hash or plan_hash(plan.payload) != expected_hash):
        raise DocumentDraftError('Reviewed plan is unavailable or changed')
    try:
        binding = document_source(db, plan.source_execution_id)
    except PlanError as exc:
        raise DocumentDraftError('Reviewed source/context is unavailable') from exc
    if binding is None or binding != plan.payload.get('document_source'):
        raise DocumentDraftError('Reviewed source/context changed')
    assignment = db.scalar(select(TaskAssignment).where(TaskAssignment.task_id == task.id))
    item = next((item for item in plan.payload['tasks'] if item['work_key'] == task.work_key), None)
    if (assignment is None or item is None or item['title'] != task.title or
            item['assignee_id'] != assignment.agent_id):
        raise DocumentDraftError('Reviewed task assignment changed')
    source = db.get(Execution, plan.source_execution_id)
    if authority:
        if source.cancelled or source.status != 'succeeded':
            raise DocumentDraftError('Plan source is unavailable')
        authorize_agent_project(db, source.agent_id, task.project_id, 'project.execute')
        authorize_agent_project(db, assignment.agent_id, task.project_id, 'project.execute')
    return plan, binding, assignment


def require_text_fixture(config):
    if (config.provider_connection not in TEXT_FIXTURES or
            (config.config or {}).get('output_contract', 'text') != 'text' or
            (config.config or {}).get('price_envelope') is not None):
        raise DocumentDraftError('Reviewed drafts require an unpriced text fixture')


def fixture_for_run(db, execution, *, authority=True):
    run = db.get(DocumentDraftRun, execution.id)
    if run is None:
        return None
    task = db.get(Task, execution.task_id)
    plan, binding, assignment = checked_plan(db, task, run.plan_digest, authority=authority)
    if run.proposal_id != plan.id or execution.agent_id != assignment.agent_id:
        raise DocumentDraftError('Draft run scope changed')
    try:
        recorded = source_record(db, execution)
    except BriefSourceError as exc:
        raise DocumentDraftError('Draft source/context is unavailable') from exc
    if (recorded['status'] != 'pinned' or recorded['project_id'] != binding['project_id'] or
            recorded['revision'] != binding['brief_revision'] or recorded['digest'] != binding['brief_digest']):
        raise DocumentDraftError('Draft source differs from reviewed plan')
    config = db.get(AgentConfigVersion, execution.config_version_id)
    require_text_fixture(config)
    # The copied preparation is separately verified by source_record as well.
    original = db.get(ExecutionBriefContext, plan.source_execution_id)
    prepared = db.get(ExecutionBriefContext, execution.id)
    if (prepared is None or prepared.message != original.message or prepared.digest != binding['context_digest']):
        raise DocumentDraftError('Draft preparation differs from reviewed context')
    return FixtureDocument(plan_id=plan.id, plan_digest=run.plan_digest, title=task.title,
        project_id=task.project_id, brief_revision=binding['brief_revision'],
        brief_digest=binding['brief_digest'], context_digest=binding['context_digest'],
        source_prefix=json.loads(prepared.message)['content'])
