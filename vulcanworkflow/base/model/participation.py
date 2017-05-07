import logging
import os

from ming.odm import FieldProperty, ForeignIdProperty
from ming import schema as S
from pylons import tmpl_context as c, app_globals as g
from tg import config

from vulcanforge.artifact.model import Artifact
from vulcanforge.auth.schema import ACE
from vulcanforge.common.exceptions import ForgeError
from vulcanforge.common.model.session import main_orm_session
from vulcanforge.common.util.model import VFRelationProperty
from vulcanforge.messaging.model import Conversation
from vulcanforge.notification.model import Notification
from vulcanforge.notification.util import gen_message_id
from vulcanforge.notification.tasks import sendmail
from vulcanforge.project.model import ProjectRole

LOG = logging.getLogger(__name__)

INVITATION_NOTIFICATION = u"""
The {} team has been invited to join the workflow by {}.
"""

INVITATION_EMAIL = u"""
The {team} team has been invited to join the {workflow} workflow.

{text}

You can accept this invitation on your User Dashboard.
"""

MEMBERSHIP_INVITATION_NOTIFICATION = u"""
The following user has been invited to join the workflow:

{}
Email: {}
{}
"""

MEMBERSHIP_INVITATION_EMAIL = u"""
You have been invited to participate in a workflow.

{text}

You can accept this invitation on your User Dashboard.
"""


class NotAuthorized(ForgeError):
    pass


class WorkflowInvitation(Artifact):

    class __mongometa__:
        session = main_orm_session
        name = 'workflow_invitation'
        indexes = ['project_id', 'email', 'user_id']

    _id = FieldProperty(S.ObjectId)
    project_id = ForeignIdProperty('WorkflowStep',
                                   if_missing=lambda: c.project._id)
    project = VFRelationProperty('WorkflowStep', via="project_id")
    invitee_id = ForeignIdProperty('Project', if_missing=None)
    invitee = VFRelationProperty('Project', via="invitee_id")
    user_id = ForeignIdProperty('User', if_missing=lambda: c.user._id)
    user = VFRelationProperty('User', via="user_id")
    text = FieldProperty(str)

    @classmethod
    def create(cls, user, workflow, project, text=''):
        obj = cls.query.get(user_id=user._id,
                            project_id=workflow._id,
                            invitee_id=project._id)
        if obj is None:
            obj = cls(
                project_id=workflow._id,
                invitee_id=project._id,
                user_id=user._id,
                text=text
            )
            Notification.post(
                artifact=obj,
                topic='participation',
                text=obj.notification_text,
                subject=obj.notification_subject
            )
        else:
            obj.text = text
        return obj

    @property
    def notification_subject(self):
        return u'Workflow Invitation to {} from {}'.format(
            self.invitee.name,
            self.project.name)

    @property
    def notification_text(self):
        return INVITATION_NOTIFICATION.format(
            self.invitee.name,
            self.user.display_name
        )

    @property
    def invitation_text(self):
        return INVITATION_EMAIL.format(
            team=self.invitee.name,
            workflow=self.project.name,
            user=self.user.display_name,
            text=self.text
        )

    @property
    def invitation_subject(self):
        return u'Workflow Invitation from {}'.format(
            self.project.name)

    def index(self, **kw):
        index_doc = super(WorkflowInvitation, self).index(**kw)
        index_doc.update({'title_s': self.invitation_subject})
        return index_doc

    def url(self):
        return self.app_config.url()

    def send(self):
        users = [x.get_email_address() for x in self.invitee.users()
                 if g.security.has_access(self.invitee, 'workflows', x)]
        for user in users:
            sendmail.post(
                fromaddr=g.forgemail_return_path,
                destinations=[user],
                reply_to=g.forgemail_return_path,
                subject=self.invitation_subject,
                message_id=gen_message_id(),
                text=self.invitation_text
            )

    def accept(self):
        g.security.require_access(self.invitee, 'workflows')
        # add invitee as participant in workflow step
        self.project.participants += [self.invitee._id]
        # add accepting user as an admin in workflow step
        self.project.add_user(c.user, ['Admin'])
        # create project role in workflow step for members of invitee project
        ir = ProjectRole.upsert(name=self.invitee.name,
                                project_id=self.project._id)
        # grant role read access to the workflow step
        self.project.acl += [ACE.allow(ir._id, 'read')]
        # add accepting user to this role
        pr = self.project.project_role(c.user)
        pr.roles += [ir._id]
        # finally, delete invitation
        self.delete()

    def reject(self):
        g.security.require_access(self.invitee, 'workflows')
        self.delete()

    def rescind(self):
        if not self.project.is_founding_admin(c.user):
            raise NotAuthorized("Not authorized to rescind invitation.")
        self.delete()


class WorkflowMembershipInvitation(Artifact):

    class __mongometa__:
        session = main_orm_session
        name = 'workflow_membership_invitation'
        indexes = ['project_id', 'user_id']

    _id = FieldProperty(S.ObjectId)
    project_id = ForeignIdProperty('Project', if_missing=lambda: c.project._id)
    project = VFRelationProperty('Project', via="project_id")
    from_project_id = ForeignIdProperty('Project', if_missing=None)
    from_project = VFRelationProperty('Project', via="from_project_id")
    user_id = ForeignIdProperty('User', if_missing=None)
    user = VFRelationProperty('User', via="user_id")
    creator_id = ForeignIdProperty('User', if_missing=lambda: c.user._id)
    creator = VFRelationProperty('User', via="creator_id")
    text = FieldProperty(str)

    @classmethod
    def from_user(cls, user, project=None, from_project_id=None, text=''):
        if project is None:
            project = c.project
        obj = cls.query.get(user_id=user._id, project_id=project._id)
        if obj is None:
            obj = cls(
                user_id=user._id,
                project_id=project._id,
                from_project_id=from_project_id,
                text=text
            )
            Notification.post(
                artifact=obj,
                topic='membership',
                text=obj.notification_text,
                subject=obj.invitation_subject
            )
        else:
            obj.text = text
        return obj

    @property
    def notification_text(self):
        if self.user_id:
            name_tag = u'Name: {}'.format(self.user.display_name)
            profile_tag = u'Profile: {}'.format(
                os.path.join(
                    config.get('base_url', 'https://vulcanforge.org'),
                    self.user.url() + 'profile'
                )
            )
        else:
            name_tag = ''
            profile_tag = ''
        return MEMBERSHIP_INVITATION_NOTIFICATION.format(
            name_tag,
            self.user.get_email_address(),
            profile_tag
        )

    @property
    def invitation_text(self):
        if self.user_id:
            read_roles = self.project.get_read_roles()
            if 'anonymous' in read_roles or 'authenticated' in read_roles:
                url_text = "the project's home tool:"
                url = g.url(self.project.url())
            else:
                url_text = "your profile"
                if self.user_id:
                    url_text += ":"
                    url = g.url(self.user.url() + "profile")
                else:
                    url = ""
        else:
            url_text = "registering here: "
            if self.registration_token:
                url = self.registration_token.full_registration_url
            else:
                url = g.url('/auth/register')

        return MEMBERSHIP_INVITATION_EMAIL.format(
            text=self.text
        )

    @property
    def invitation_subject(self):
        return u'Membership Invitation from {}'.format(
            self.creator.display_name)

    def index(self, **kw):
        index_doc = super(WorkflowMembershipInvitation, self).index(**kw)
        index_doc.update({'title_s': self.invitation_subject})
        return index_doc

    def url(self):
        return self.app_config.url()

    def send(self):
        conversation = Conversation(subject="Workflow Invitation")
        conversation.add_user_id(self.user_id)
        conversation.add_user_id(self.creator_id)
        conversation.add_message(self.creator_id, self.invitation_text)

    def accept(self):
        if c.user != self.user:
            raise NotAuthorized("Not authorized to accept invitation.")
        # add invitee as participant in workflow step
        roles = ['Member']
        if self.from_project_id:
            roles.append(self.from_project.name)
        self.project.add_user(c.user, roles)
        # finally, delete invitation
        self.delete()

    def reject(self):
        if c.user != self.user:
            raise NotAuthorized("Not authorized to reject invitation.")
        self.delete()

    def rescind(self):
        g.security.require_access(self.project, 'admin')
        self.delete()