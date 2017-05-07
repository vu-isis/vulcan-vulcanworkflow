from ming.odm import FieldProperty

from vulcanforge.neighborhood.model import Neighborhood
from vulcanforge.project.model import Project


class WorkflowProject(Project):
    """
    A kind of project that can authorize creation of workflows
    """

    _polymorphic_queries = True

    class __mongometa__:
        polymorphic_identity = 'workflow_project'

    kind = FieldProperty(str, if_missing='workflow_project')

    _perms_base = ['read', 'write', 'admin', 'workflows']
    _perms_proj = _perms_base[:]
    _perms_init = _perms_base + ['register', 'overseer']


class WorkflowProjectNeighborhood(Neighborhood):

    class __mongometa__:
        polymorphic_identity = 'workflow_project_neighborhood'

    kind = FieldProperty(str, if_missing='workflow_project_neighborhood')

    @property
    def project_cls(self):
        return WorkflowProject

    @property
    def controller_class(self):
        from vulcanworkflow.base.controllers import \
            WorkFlowProjectNeighborhoodController
        return WorkFlowProjectNeighborhoodController
