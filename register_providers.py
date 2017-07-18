import os
import time
import yaml

hostname = os.environ['HOSTNAME']
curl_cmd = 'curl -s -o /dev/null -w "{msg_out} : %{{http_code}}\\n" {params} {url}'
providers_cfg = yaml.load(file('./providers.cfg', 'r'))
admin_pw = providers_cfg['admin_pw']
providers = providers_cfg['providers']
login_url = 'https://{0}:8443/account/login'.format(hostname)
cookie_fn = '/tmp/login_cookie'

# Allow some time for Phoenix to start (if we are called in the docker startup sequence)
attempt = 0
while attempt < 10:
    if os.system(curl_cmd.format(msg_out='Login response',
                                 params=('--cookie-jar {0} '
                                         '--data '
                                         '"password={1}&csrf_token=0&submit=submit"').format(cookie_fn, admin_pw),
                                 url=login_url)) == 0:
        break
    time.sleep(6)
    attempt += 1
if attempt == 10:
    raise Exception('Cannot log in to {0}'.format(login_url))

for provider in providers:
    cfg = providers[provider]
    url = os.path.expandvars(cfg['url'])
    public = 'true' if providers[provider]['public'] else 'false'
    params= ('--cookie {cookie} '
             '--data "'
             'service_name={name}&'
             'url={url}&'
             'service_title={cfg[title]}&'
             'public={public}&'
             'c4i={cfg[c4i]}&'
             'csrf_token=0&'
             'service_type=WPS&'
             'register=register"').format(cookie=cookie_fn,
                                          name=provider,
                                          url=url,
                                          public=public,
                                          cfg=cfg)

    os.system(curl_cmd.format(msg_out='Register response',
                              params=params,
                              url='https://{0}:8443/services/register'.format(hostname)))
os.remove(cookie_fn)
