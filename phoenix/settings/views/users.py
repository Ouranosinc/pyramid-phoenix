from pyramid.view import view_config
from pyramid.httpexceptions import HTTPFound

from . import SettingsView
from phoenix.security import Admin, User, Guest

import logging
logger = logging.getLogger(__name__)

class Users(SettingsView):
    def __init__(self, request):
        super(Users, self).__init__(request, name='settings_users', title='Users')

    def breadcrumbs(self):
        breadcrumbs = super(Users, self).breadcrumbs()
        breadcrumbs.append(dict(route_path=self.request.route_path(self.name), title=self.title))
        return breadcrumbs

    @view_config(route_name='remove_user')
    def remove(self):
        # TODO: fix handling of userids
        userid = self.request.matchdict.get('userid')
        if userid is not None:
            self.userdb.remove(dict(identifier=userid))
            self.session.flash('User removed', queue="info")
        return HTTPFound(location=self.request.route_path(self.name))

    @view_config(route_name='settings_users', renderer='../templates/settings/users.pt')
    def view(self):
        user_items = list(self.userdb.find().sort('last_login', -1))
        grid = UsersGrid(
                self.request,
                user_items,
                ['name', 'userid', 'email', 'organisation', 'notes', 'group', 'last_login', ''],
            )
        return dict(grid=grid)

from phoenix.grid import CustomGrid
    
class UsersGrid(CustomGrid):
    def __init__(self, request, *args, **kwargs):
        super(UsersGrid, self).__init__(request, *args, **kwargs)
        self.column_formats['userid'] = self.label_td('login_id')
        self.column_formats['group'] = self.group_td
        self.column_formats['last_login'] = self.time_ago_td('last_login')
        self.column_formats[''] = self.buttongroup_td
        self.exclude_ordering = self.columns

    def group_td(self, col_num, i, item):
        from webhelpers2.html.builder import HTML
        group = item.get('group')
        label = "???"
        if group == Admin:
            label = "Admin"
        elif group == User:
            label = "User"
        elif group == Guest:
            label = "Guest"
        return HTML.td(label)

    def buttongroup_td(self, col_num, i, item):
        from phoenix.utils import ActionButton
        buttons = []
        buttons.append( ActionButton('edit', css_class="btn btn-success", icon="fa fa-pencil",
                                     href=self.request.route_path('settings_edit_user', userid=item.get('identifier'))))
        buttons.append( ActionButton('remove', css_class="btn btn-danger", icon="fa fa-trash",
                                     href=self.request.route_path('remove_user', userid=item.get('identifier'))))

        return self.render_td(renderer="buttongroup2_td.mako", buttons=buttons)
    

