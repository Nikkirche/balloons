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
