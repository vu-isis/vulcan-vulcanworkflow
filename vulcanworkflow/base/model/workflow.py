import logging

from pylons import app_globals as g

from ming import schema as S
from ming.odm import FieldProperty, ForeignIdProperty, RelationProperty
from ming.utils import LazyProperty

from vulcanforge.auth.schema import ACE
from vulcanforge.neighborhood.model import Neighborhood
from vulcanforge.project.model import (
    Project, ProjectRole, MembershipInvitation
)
from .exceptions import RegistrationError

LOG = logging.getLogger(__name__)


class WorkflowStep(Project):

    _polymorphic_queries = True

    class __mongometa__:
        polymorphic_identity = 'workflow_step'

    kind = FieldProperty(str, if_missing='workflow_step')

    type_s = 'WorkflowStep'
    type_label = 'Workflow'

    # founding project
    founder_id = ForeignIdProperty(Project)
    founder = RelationProperty(Project, via='founder_id')
    # projects participating in WorkflowStep
    participants = FieldProperty([S.ObjectId])

    @LazyProperty
    def home_ac(self):
        proj_home_cls = g.tool_manager.tools["wfhome"]["app"]
        nbhd_home_cls = g.tool_manager.tools["neighborhood_home"]["app"]
        for ac in self.app_configs:
            app_cls = ac.load()
            if issubclass(app_cls, proj_home_cls) or \
                    issubclass(app_cls, nbhd_home_cls):
                return ac
        return None

    @property
    def icon_default_url(self):
        path = 'workflow/images/workflow_default.png'
        return g.resource_manager.absurl(path)

    @property
    def icon_url(self):
        return self.icon.url() if self.icon else self.icon_default_url

    def _required_apps(self, is_user_project=False):
        if is_user_project:
            return [('profile', 'profile', 'Profile'),
                    ('admin', 'admin', 'Admin')]
        else:
            return [('wfhome', 'home', 'Home'),
                    ('admin', 'admin', 'Admin')]

    def is_founding_admin(self, user):
        return (g.security.has_access(self, 'admin', user) and
                g.security.has_access(self.founder, 'workflows', user))

    def install_default_acl(self, admins=None, is_private_project=False,
                            is_user_project=False):
        installer = super(WorkflowStep, self).install_default_acl
        installer(admins, is_private_project, is_user_project)

        # create and assign role for founder project members
        fr = ProjectRole.upsert(name=self.founder.name, project_id=self._id)
        self.acl += [ACE.allow(fr._id, 'read')]
        for user in admins:
            pr = self.project_role(user)
            pr.roles += [fr._id]


class WorkflowNeighborhood(Neighborhood):

    class __mongometa__:
        polymorphic_identity = 'workflow_neighborhood'

    kind = FieldProperty(str, if_missing='workflow_neighborhood')

    @property
    def project_cls(self):
        return WorkflowStep

    @property
    def controller_class(self):
        from vulcanworkflow.base.controllers import \
            WorkflowNeighborhoodController
        return WorkflowNeighborhoodController

    def user_can_register(self, user=None):
        """
        Whether a user can register a WorkflowStep

        """
        if user:
            for p in user.my_projects():
                if ('workflows' in p.permissions and
                        g.security.has_access(p, 'workflows', user)):
                    return True
        return False

    @property
    def icon_default_url(self):
        path = 'workflow/images/workflows_default.png'
        return g.resource_manager.absurl(path)

    def icon_url(self):
        return self.icon.url() if self.icon else self.icon_default_url

    def register_workflow(self, shortname, founding_project=None,
                          user=None, workflow_name=None,
                          apps=None, tool_options=None,
                          short_description='', **kw):
        """
        Register a new WorkflowStep in the neighborhood.  The given user will
        become the project's administrator.  If no user is specified, c.user
        is used.
        """
        if Project.by_shortname(shortname):
            raise RegistrationError('The shortname already exists.')
        if founding_project and hasattr(founding_project, 'shortname'):
            kw['founder_id'] = founding_project._id
            kw['participants'] = [founding_project._id]
        elif not ('founder_id' in kw or 'participants' in kw):
            msg = "Missing founder or participants."
            raise RegistrationError(msg)

        register = super(WorkflowNeighborhood, self).register_project
        return register(shortname, user, workflow_name,
                        user_project=False, private_project=True,
                        apps=apps, tool_options=tool_options,
                        short_description=short_description, **kw)
