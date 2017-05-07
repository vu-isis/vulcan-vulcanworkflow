from bson import ObjectId
import logging
import simplejson

from paste.deploy.converters import asbool
from pylons import tmpl_context as c, app_globals as g
from tg import config, expose, redirect, flash
from tg.decorators import with_trailing_slash
from webob import exc

from vulcanforge.auth.model import User
from vulcanforge.auth.schema import ACE
from vulcanforge.common.controllers.decorators import require_post
from vulcanforge.project.model import Project, ProjectRole
from vulcanforge.project.validators import ShortnameValidator
from vulcanforge.tools.home.project_main import (
    ProjectHomeApp,
    ProjectHomeController
)
from vulcanworkflow.base.model.participation import (
    WorkflowInvitation,
    WorkflowMembershipInvitation
)

LOG = logging.getLogger(__name__)

TEMPLATE_HOME = 'home/'


class WorkflowHomeApp(ProjectHomeApp):
    tool_label = 'wfhome'
    static_folder = 'wfhome'
    default_mount_label = 'Workflow Home'

    def __init__(self, project, config):
        super(WorkflowHomeApp, self).__init__(project, config)
        self.root = WorkflowHomeController()


class WorkflowHomeController(ProjectHomeController):

    _tool_excludes = ('wfhome', 'chat', 'calendar')

    @with_trailing_slash
    @expose('wfhome/index.html')
    def index(self, **kwargs):
        info = super(WorkflowHomeController, self).index(**kwargs)
        isAdmin = c.project.is_founding_admin(c.user)
        if isAdmin:
            q = {'project_id': c.project._id}
            invites = WorkflowInvitation.query.find(q)
            invitations = [dict(team=x.invitee, id=x._id) for x in invites
                           if not x._id in c.project.participants]
            info['wf_invitations'] = invitations
        return info

    @expose('json')
    def profile_info(self):
        info = super(WorkflowHomeController, self).profile_info()
        info['admin'] = c.project.is_founding_admin(c.user)
        if (c.project.founder and not c.project.founder.deleted and
                g.security.has_access(c.project.founder,'read')):
            info['founder'] = dict(name=c.project.founder.name,
                                   url=c.project.founder.url(),
                                   icon_url=c.project.founder.icon_url)
        plist = [Project.by_id(x) for x in c.project.participants
                 if x != c.project.founder._id]
        participants = [x for x in plist if not x.deleted
                        and g.security.has_access(x, 'read')]
        if participants:
            pinfo = [dict(name=x.name, url=x.url(), icon_url=x.icon_url)
                     for x in participants]
            info['participants'] = pinfo
        return info

    @expose()
    def workflow_invitation_rescind(self, id_string):
        if not id_string:
            raise exc.HTTPNotFound
        invite = WorkflowInvitation.query.get(_id=ObjectId(id_string))
        if invite:
            invite.delete()
            flash('Invitation canceled')
        else:
            flash('Invitation not available')
        redirect('..')

    def is_eligible(self, p):
        """A role has been granted the workflows permission in project"""
        if p != c.project.founder and p._id not in c.project.participants:
            for ace in p.acl:
                if ace.permission == 'workflows' and ace.access == ACE.ALLOW:
                    return True
        return False

    @expose('json')
    def eligible_users(self):
        projects = [Project.by_id(x) for x in c.project.participants]
        eligible_projects = [x for x in projects
                             if g.security.has_access(x, 'workflows')]
        users = {}
        existing_users = {x.username: x for x in c.project.users()}
        public_users = asbool(config.get('all_users_public', False))
        for project in eligible_projects:
            for u in project.users():
                is_public = public_users or u.public
                if (is_public and not u.disabled
                        and u.username not in existing_users
                        and u.username not in users):
                    users[u.username] = (u, project)
        retval = {}
        for username in users:
            user, project = users[username]
            retval[user.display_name] = dict(
                username=user.username,
                email=user.get_email_address(),
                project_id=str(project._id)
            )
        return retval

    @require_post()
    @expose('json')
    def do_invite_teams(self, invitees="", invitation_msg="", **kw):
        validator = ShortnameValidator()
        if invitees:
            invited = simplejson.loads(invitees)
            if (type(invited) is list):
                itext = invitation_msg or "Please join my workflow."
                ac_id = c.project.home_ac._id
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
                        # issue invitation
                        invite = WorkflowInvitation.create(
                            c.user, c.project, ip, itext
                        )
                        invite.send()

        return {"status": "success"}

    @require_post()
    @expose('json')
    def do_invite_users(self, invitees="", invitation_msg="", **kw):
        if invitees:
            invited = simplejson.loads(invitees)
            if (type(invited) is list):
                itext = invitation_msg or "Please join my workflow."
                admin_role = ProjectRole.by_name('Admin', c.project)
                member_role = ProjectRole.by_name('Member', c.project)
                ac_id = c.project.home_ac._id
                with g.context_manager.push(app_config_id=ac_id):
                    c.project.notifications_disabled = False
                    for invitee in invited:
                        # check if email invitee is current user
                        if 'address' in invitee:
                            email = invitee['address']
                            user = User.by_email_address(email)
                            if user:
                                invitee['username'] = user.username
                        # issue invitation
                        if 'username' in invitee:
                            username = invitee['username']
                            user = User.by_username(username)
                            if user and user.username != c.user.username:
                                pid = invitee.get('project_id', None)
                                if pid:
                                    try:
                                        fpid = ObjectId(pid)
                                    except:
                                        fpid = None
                                cm = WorkflowMembershipInvitation.from_user
                                n = cm(user, from_project_id=fpid, text=itext)
                                n.send()

        return {"status": "success"}
