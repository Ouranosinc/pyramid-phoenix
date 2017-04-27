from datetime import datetime
import uuid

from pyramid.view import view_config, view_defaults, forbidden_view_config
from pyramid.httpexceptions import HTTPFound, HTTPForbidden
from pyramid.response import Response
from pyramid.security import remember, forget

from deform import Form, Button, ValidationFailure
from authomatic.adapters import WebObAdapter

from phoenix.views import MyView
from phoenix.security import Admin, Guest, authomatic, passwd_check
from phoenix.security import allowed_auth_protocols
from phoenix.security import AUTH_PROTOCOLS
from phoenix.twitcherclient import generate_access_token
from phoenix.account.schema import PhoenixSchema, LdapSchema, ESGFOpenIDSchema, OpenIDSchema, OAuthSchema

import logging
logger = logging.getLogger(__name__)


def add_user(request, login_id, email='', openid='', name='unknown', organisation='', notes='', group=Guest):
    user = dict(
        identifier=str(uuid.uuid1()),
        login_id=login_id,
        email=email,
        openid=openid,
        name=name,
        organisation=organisation,
        notes=notes,
        group=group,
        creation_time=datetime.now(),
        last_login=datetime.now())
    request.db.users.save(user)
    return request.db.users.find_one({'identifier': user['identifier']})


@forbidden_view_config(renderer='templates/account/forbidden.pt', layout="default")
def forbidden(request):
    request.response.status = 403
    return dict()


@view_config(route_name='account_register', renderer='templates/account/register.pt',
             permission='view', layout="default")
def register(request):
    return dict()


@view_defaults(permission='view', layout='default')
class Account(MyView):
    def __init__(self, request):
        super(Account, self).__init__(request, name="account", title='Account')

    def appstruct(self, protocol):
        if protocol == 'oauth2':
            return dict(provider='github')
        elif protocol == 'esgf':
            return dict(provider='dkrz')
        else:
            return dict()

    def generate_form(self, protocol):
        if protocol == 'phoenix':
            schema = PhoenixSchema()
        elif protocol == 'esgf':
            schema = ESGFOpenIDSchema()
        elif protocol == 'openid':
            schema = OpenIDSchema()
        elif protocol == 'oauth2':
            schema = OAuthSchema()
        else:
            schema = LdapSchema()
        btn = Button(name='submit', title='Log in',
                     css_class="btn btn-success btn-lg btn-block")
        form = Form(schema=schema, buttons=(btn,), formid='deform')
        return form

    def process_form(self, form, protocol):
        try:
            controls = self.request.POST.items()
            appstruct = form.validate(controls)
        except ValidationFailure, e:
            logger.exception('validation of form failed.')
            return dict(
                active=protocol,
                protocol_name=AUTH_PROTOCOLS[protocol],
                auth_protocols=allowed_auth_protocols(self.request),
                form=e.render())
        else:
            if protocol == 'phoenix':
                return self.phoenix_login(appstruct)
            elif protocol == 'ldap':
                return self.ldap_login()
            elif protocol == 'oauth2':
                return HTTPFound(location=self.request.route_path('account_auth',
                                 provider_name=appstruct.get('provider')))
            elif protocol == 'esgf':
                return HTTPFound(location=self.request.route_path('account_auth',
                                 provider_name=appstruct.get('provider'),
                                 _query=dict(username=appstruct.get('username'))))
            elif protocol == 'openid':
                openid = appstruct.get('openid')
                return HTTPFound(location=self.request.route_path('account_auth',
                                 provider_name='openid', _query=dict(id=openid)))
            else:
                return HTTPForbidden()

    def send_notification(self, email, subject, message):
        """Sends email notification to admins.

        Sends email with the pyramid_mailer module.
        For configuration look at documentation http://pythonhosted.org//pyramid_mailer/
        """
        from pyramid_mailer import get_mailer
        mailer = get_mailer(self.request)

        sender = "noreply@%s" % (self.request.server_name)

        recipients = set()
        for user in self.request.db.users.find({'group': Admin}):
            email = user.get('email')
            if email:
                recipients.add(email)

        if len(recipients) > 0:
            from pyramid_mailer.message import Message
            message = Message(subject=subject,
                              sender=sender,
                              recipients=recipients,
                              body=message)
            try:
                mailer.send_immediately(message, fail_silently=True)
            except:
                logger.exception("failed to send notification")
        else:
            logger.warn("Can't send notification. No admin emails are available.")

    def login_success(self, login_id, email='', name="Unknown", openid=None, local=False):
        user = self.request.db.users.find_one(dict(login_id=login_id))
        if user is None:
            logger.warn("new user: %s", login_id)
            user = add_user(self.request, login_id=login_id, email=email, group=Guest)
            subject = 'Phoenix: New user %s logged in on %s' % (name, self.request.server_name)
            message = 'Please check the activation of the user {0} on the Phoenix host {1}'.format(
                name, self.request.server_name)
            self.send_notification(email, subject, message)
        if local and login_id == 'phoenix@localhost':
            user['group'] = Admin
        user['last_login'] = datetime.now()
        if openid:
            user['openid'] = openid
        user['name'] = name
        self.userdb.update({'login_id': login_id}, user)
        self.session.flash("Hello <strong>{0}</strong>. Welcome to Phoenix.".format(name), queue='info')
        if user.get('group') == Guest:
            msg = """
            You are member of the <strong>Guest</strong> group.
            You are allowed to submit processes without <strong>access restrictions</strong>.
            """
            self.session.flash(msg, queue='info')
        else:
            generate_access_token(self.request.registry, userid=user['identifier'])
        headers = remember(self.request, user['identifier'])
        return HTTPFound(location=self.request.route_path('home'), headers=headers)

    def login_failure(self, message=None):
        msg = 'Sorry, login failed.'
        if message:
            msg = 'Sorry, login failed: {0}'.format(message)
        self.session.flash(msg, queue='danger')
        logger.warn(msg)
        return HTTPFound(location=self.request.route_path('home'))

    @view_config(route_name='account_login', renderer='templates/account/login.pt')
    def login(self):
        protocol = self.request.matchdict.get('protocol', 'phoenix')
        allowed_protocols = allowed_auth_protocols(self.request)

        # Make sure disabled protocols are not accessed directly
        if protocol not in allowed_protocols:
            return HTTPForbidden()

        if protocol == 'ldap':
            # Ensure that the ldap connector is created
            self.ldap_prepare()

        form = self.generate_form(protocol)
        if 'submit' in self.request.POST:
            return self.process_form(form, protocol)
        # TODO: Add ldap to title?
        return dict(active=protocol,
                    protocol_name=AUTH_PROTOCOLS[protocol],
                    auth_protocols=allowed_protocols,
                    form=form.render(self.appstruct(protocol)))

    @view_config(route_name='account_logout', permission='edit')
    def logout(self):
        headers = forget(self.request)
        return HTTPFound(location=self.request.route_path('home'), headers=headers)

    def phoenix_login(self, appstruct):
        password = appstruct.get('password')
        if passwd_check(self.request, password):
            return self.login_success(login_id="phoenix@localhost", name="Phoenix", local=True)
        return self.login_failure()

    @view_config(route_name='account_auth')
    def authomatic_login(self):
        _authomatic = authomatic(self.request)

        provider_name = self.request.matchdict.get('provider_name')

        # Start the login procedure.
        response = Response()
        result = _authomatic.login(WebObAdapter(self.request, response), provider_name)

        if result:
            if result.error:
                # Login procedure finished with an error.
                return self.login_failure(message=result.error.message)
            elif result.user:
                if not (result.user.name and result.user.id):
                    result.user.update()
                # Hooray, we have the user!
                logger.info("login successful for user %s", result.user.name)
                if result.provider.name in ['openid', 'dkrz', 'ipsl', 'smhi', 'badc', 'pcmdi']:
                    # TODO: change login_id ... more infos ...
                    return self.login_success(login_id=result.user.id,
                                              email=result.user.email,
                                              openid=result.user.id,
                                              name=result.user.name)
                elif result.provider.name == 'github':
                    # TODO: fix email ... get more infos ... which login_id?
                    login_id = "{0.username}@github.com".format(result.user)
                    #email = "{0.username}@github.com".format(result.user)
                    # get extra info
                    if result.user.credentials:
                        pass
                    return self.login_success(login_id=login_id, name=result.user.name)
        return response

    def ldap_prepare(self):
        """Lazy LDAP connector construction"""
        ldap_settings = self.request.db.ldap.find_one()

        if ldap_settings is None:
            # Warn if LDAP is about to be used but not set up.
            self.session.flash('LDAP does not seem to be set up correctly!', queue='danger')
        elif getattr(self.request, 'ldap_connector', None) is None:
            logger.debug('Set up LDAP connector...')

            # Set LDAP settings
            import ldap
            if ldap_settings['scope'] == 'ONELEVEL':
                ldap_scope = ldap.SCOPE_ONELEVEL
            else:
                ldap_scope = ldap.SCOPE_SUBTREE

            # FK: Do we have to think about race conditions here?
            from pyramid.config import Configurator
            config = Configurator(registry=self.request.registry)
            config.ldap_setup(ldap_settings['server'],
                              bind=ldap_settings['bind'],
                              passwd=ldap_settings['passwd'])
            config.ldap_set_login_query(
                base_dn=ldap_settings['base_dn'],
                filter_tmpl=ldap_settings['filter_tmpl'],
                scope=ldap_scope)
            config.commit()

    def ldap_login(self):
        """LDAP login"""
        username = self.request.params.get('username')
        password = self.request.params.get('password')

        # Performing ldap login
        from pyramid_ldap import get_ldap_connector
        connector = get_ldap_connector(self.request)
        auth = connector.authenticate(username, password)

        if auth is not None:
            # Get user name and email
            ldap_settings = self.request.db.ldap.find_one()
            name = (auth[1].get(ldap_settings['name'])[0] if ldap_settings['name'] != '' else 'Unknown')
            email = (auth[1].get(ldap_settings['email'])[0] if ldap_settings['email'] != '' else '')

            # Authentication successful
            return self.login_success(login_id=auth[0], name=name, email=email)  # login_id=user_dn
        else:
            # Authentification failed
            return self.login_failure()
