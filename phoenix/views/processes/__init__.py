from pyramid.view import view_config, view_defaults

from phoenix.views import MyView

import logging
logger = logging.getLogger(__name__)

@view_defaults(permission='edit', layout='default')
class Processes(MyView):
    def __init__(self, request, name, title, description=None):
        super(Processes, self).__init__(request, name, title, description)

    def breadcrumbs(self):
        breadcrumbs = super(Processes, self).breadcrumbs()
        breadcrumbs.append(dict(route_name='processes_overview', title='Processes'))
        breadcrumbs.append(dict(route_name=self.name, title=self.title))
        return breadcrumbs
