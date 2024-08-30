import hashlib
import json
import random
import time
import urllib

import config
import jwt


class AuthentificationError(Exception):
    pass


def create_token(user_id, *, add_random=False):
    day = int(time.time() / (24 * 60 * 60))
    extra = ''
    if add_random:
        extra = ':' + ''.join(map(lambda x: chr(x + ord('a')), [random.choice(range(26)) for nonce in range(40)]))
    return hashlib.sha256((
                                  str(user_id) + ':' +
                                  str(day) + ':' +
                                  config.auth_salt +
                                  extra
                          ).encode()).hexdigest()


def check(user_id, token):
    return token == create_token(user_id)


class vk:
    url = 'https://oauth.vk.com/authorize?' + urllib.parse.urlencode({
        'client_id': config.vk_app_id,
        'display': 'page',
        'response_type': 'code',
        'redirect_uri': config.base_url_global + '/auth/vk/done'
    })

    @classmethod
    def do(cls, code):
        vk_oauth_url = 'https://oauth.vk.com/access_token?' + urllib.parse.urlencode({
            'client_id': config.vk_app_id,
            'client_secret': config.vk_client_secret,
            'redirect_uri': config.base_url_global + '/auth/vk/done',
            'code': code
        })
        res = json.loads(urllib.request.urlopen(vk_oauth_url).read().decode())
        if 'error' in res:
            raise AuthentificationError(str(res['error_description']))
        user_id = str(res['user_id'])

        api_url = "https://api.vk.com/method/users.get?" + \
                  urllib.parse.urlencode({
                      'user_ids': user_id,
                      'access_token': config.vk_access_token,
                      'v': 5.92,
                  })
        res = json.loads(urllib.request.urlopen(api_url).read().decode())
        if 'error' in res:
            raise AuthentificationError(str(res['error_description']))

        res = res['response'][0]

        name = "%s %s" % (res['first_name'], res['last_name'])
        url = "https://vk.com/id%s" % res['id']

        return ('vk:' + user_id, name, url)


class google:
    url = 'https://accounts.google.com/o/oauth2/v2/auth?' + urllib.parse.urlencode({
        'client_id': config.google_client_id,
        'response_type': 'code',
        'scope': 'openid profile',
        'redirect_uri': config.base_url_global + '/auth/google/done'
    })

    @classmethod
    def do(cls, code):
        google_oauth_base = 'https://www.googleapis.com/oauth2/v4/token'
        google_oauth_data = urllib.parse.urlencode({
            'client_id': config.google_client_id,
            'client_secret': config.google_client_secret,
            'redirect_uri': config.base_url_global + '/auth/google/done',
            'code': code,
            'grant_type': 'authorization_code'
        })
        response = urllib.request.urlopen(
            google_oauth_base,
            google_oauth_data.encode('utf-8'))
        res = json.loads(response.read().decode())
        if 'error' in res:
            raise AuthentificationError(str(res['error_description']))
        token = jwt.decode(res['id_token'], options={"verify_signature": False}, algorithms=['RS256'])
        sub = token['sub']
        name = token.get('name', sub)
        url = token.get('picture', '')
        return ('google:' + sub, name, url)
