import logging
import re
import simplejson

from ming.odm import ThreadLocalODMSession
from ming.odm import state, session
from pylons import tmpl_context as c, app_globals as g
from tg.decorators import expose

from vulcanforge.auth.schema import ACE
from vulcanforge.common.controllers.decorators import require_post
from vulcanforge.common.tasks.index import add_global_objs
from vulcanforge.neighborhood.controllers import NeighborhoodController
from vulcanforge.neighborhood.exceptions import RegistrationError
from vulcanforge.project.model import Project, ProjectFile
from vulcanforge.project.validators import ShortnameValidator

from vulcanworkflow.base.model.participation import WorkflowInvitation

LOG = logging.getLogger(__name__)


class WorkFlowProjectNeighborhoodController(NeighborhoodController):

    @expose('json')
    def workflows_initiating_projects(self):
        g.security.require_authenticated()
        q = {'deleted': False,
             'neighborhood_id': self.neighborhood._id}
        project_cls = self.neighborhood.project_cls
        return {x.name: x.shortname for x in project_cls.query_find(q)
                if g.security.has_access(x, 'workflows')}

    @expose('json')
    def workflows_eligible_projects(self):
        g.security.require_authenticated()
        q = {'deleted': False,
             'neighborhood_id': self.neighborhood._id}
        project_cls = self.neighborhood.project_cls
        projects = [x for x in project_cls.query_find(q)
                    if g.security.has_access(x, 'read')]
        eligibles = []
        for p in projects:
            for ace in p.acl:
                if ace.permission == 'workflows' and ace.access == ACE.ALLOW:
                    eligibles.append(p)
                    break
        return {x.name: x.shortname for x in eligibles}


class WorkflowNeighborhoodController(NeighborhoodController):

    def is_eligible(self, p):
        """A role has been granted the workflows permission in project"""
        for ace in p.acl:
            if ace.permission == 'workflows' and ace.access == ACE.ALLOW:
                return True
        return False

    @expose('json')
    def existing_workflows(self):
        return super(WorkflowNeighborhoodController, self).existing_projects()

    @require_post()
    @expose('json')
    def do_create_workflow(self, name, summary, founder=None,
                       icon=None, invitation_msg="", invitees="", **kw):
        g.security.require_access(c.neighborhood, 'register')
        # name
        name_regex = re.compile("^[A-Za-z]+[A-Za-z0-9 -]*$")
        mo = name_regex.match(name)
        if not mo:
            return {"status": "error", "reason": "Invalid workflow name"}
        else:
            name = name.encode('utf-8')
        # founder
        validator = ShortnameValidator()
        try:
            validator.validate_name(founder)
        except:
            return {"status": "error", "reason": "Invalid founder"}
        founding_project = Project.by_shortname(founder)
        if not founding_project:
            return {"status": "error", "reason": "Unknown founder"}
        elif not self.is_eligible(founding_project):
            return {"status": "error", "reason": "Ineligible founder"}
        # generate shortname and ensure uniqueness
        shortname = re.sub("[^A-Za-z0-9]", "", name).lower()
        project_cls = self.neighborhood.project_cls
        i = 1
        while True:
            if project_cls.by_shortname(shortname):
                i += 1
                shortname = shortname + unicode(i)
            else:
                break
        # team creation
        try:
            project = self.neighborhood.register_workflow(
                shortname,
                founding_project,
                workflow_name=name,
                short_description=summary.encode('utf-8')
            )
        except RegistrationError:
            ThreadLocalODMSession.close_all()
            return {"status": "error", "reason": "Workflow creation failed"}

        # team icon
        if icon is not None:
            if project.icon:
                ProjectFile.remove(dict(
                    project_id=project._id,
                    category='icon'
                ))
            ProjectFile.save_image(
                icon.filename,
                icon.file,
                content_type=icon.type,
                square=True,
                thumbnail_size=(64, 64),
                thumbnail_meta=dict(project_id=project._id, category='icon'))
            session(ProjectFile).flush()
            g.cache.redis.expire('navdata', 0)
            if state(project).status != "dirty":
                add_global_objs.post([project.index_id()])

        # invitations
        if invitees:
            invited = simplejson.loads(invitees)
            if (type(invited) is list):
                itext = invitation_msg or "Please join my workflow."
                ac_id = project.home_ac._id
                with g.context_manager.push(app_config_id=ac_id):
                    c.project.notifications_disabled = False
                    for name in invited:
                        try:
                            validator.validate_name(name)
                        except:
                            continue
                        ip = Project.by_shortname(name)
                        if not (ip and self.is_eligible(ip)):
                            continue
                        if ip == project:
                            continue
                        # issue invitation
                        invite = WorkflowInvitation.create(
                            c.user, project, ip, itext
                        )
                        invite.send()

        return {"status": "success"}
