from uuid import uuid4

from sqlalchemy import select

from workforce.db import session_factory
from workforce.models import Agent, AgentProjectGrant, Owner, Project
from workforce.tool_policy import (canonical_policy_resource, evaluate_tool_policy,
                                   set_tool_policy)


def test_project_ceiling_agent_grant_and_explicit_deny():
    with session_factory()() as db:
        project = Project(name='Policy project')
        agent = Agent(name='Worker', role='specialist')
        db.add_all([project, agent])
        db.flush()
        grant = AgentProjectGrant(agent_id=agent.id, project_id=project.id,
                                  action='project.execute', allowed=True)
        db.add(grant)
        owner_id = db.scalar(select(Owner.id))
        action = 'project.artifact.read'
        version_id = str(uuid4())
        resource = canonical_policy_resource(action, project.id, version_id)

        def decide():
            return evaluate_tool_policy(db, agent_id=agent.id, project_id=project.id,
                                        action=action, resource=resource)

        assert decide().effect == 'deny'
        assert evaluate_tool_policy(db, agent_id=agent.id, project_id=project.id,
                                    action='host.shell', resource=f'project:{project.id}').effect == 'deny'
        project_rule = set_tool_policy(db, project_id=project.id, agent_id=None,
                                       action=action, resource_id=None,
                                       effect='allow', owner_id=owner_id)
        assert decide().effect == 'deny'  # Project ceiling alone is insufficient.
        set_tool_policy(db, project_id=project.id, agent_id=agent.id,
                        action=action, resource_id=None,
                        effect='allow', owner_id=owner_id)
        assert decide().effect == 'allow'
        exact = set_tool_policy(db, project_id=project.id, agent_id=agent.id,
                                action=action, resource_id=version_id,
                                effect='deny', owner_id=owner_id)
        assert decide().effect == 'deny'  # Exact deny beats broader allows.
        assert len(decide().snapshot['rules']) == 3
        changed = set_tool_policy(db, project_id=project.id, agent_id=agent.id,
                                  action=action, resource_id=version_id,
                                  effect='require_approval', owner_id=owner_id)
        assert changed.id == exact.id and changed.revision == 2
        assert decide().effect == 'require_approval'
        assert project_rule.revision == 1
        assert evaluate_tool_policy(db, agent_id=agent.id, project_id=project.id,
                                    action=action, resource=f'project:{project.id}/artifact:{version_id}').effect == 'deny'
        grant.allowed = False
        db.flush()
        assert decide().effect == 'deny'
        db.commit()
