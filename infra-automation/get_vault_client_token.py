#!/usr/bin/python3

import json
import http.client
import os
from urllib.parse import urlparse

def get_client_token(vault_address=None, vault_secret_id=None, vault_role_id=None):
    body=json.dumps({
           "role_id": vault_role_id,
           "secret_id": vault_secret_id
           })

    url = urlparse(vault_address)

    conn = http.client.HTTPSConnection(*url.netloc.split(':'))
    conn.request('POST', '/v1/auth/approle/login', body)
    response = conn.getresponse()

    if response.code == 200:
        data =response.read()
        data = json.loads(data)
        return data['auth']['client_token']
    else:
        print(f'Bad response for app-role login. code={response.code}, body={response.read()}')


if __name__ == '__main__':

    vault_address = os.environ.get('VAULT_ADDRESS')
    vault_secret_id = os.environ.get('VAULT_SECRET_ID')
    vault_role_id = os.environ.get('VAULT_ROLE_ID')

    if not (vault_secret_id and vault_role_id and vault_address):
        exit(1)
        
    print(get_client_token(vault_address=vault_address,
            vault_secret_id=vault_secret_id, vault_role_id=vault_role_id))
