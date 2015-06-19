from authomatic.providers import openid

DEFAULT_MESSAGE = 'Have you got a bandage?'
DEFAULTS = {
    'popup': True,
}

AUTHENTICATION = {
    'openid': {
        'class_': openid.OpenID,
    },
}


# Concatenate the configs.
config = {}
config.update(AUTHENTICATION)
config['__defaults__'] = DEFAULTS
