#!/usr/bin/python3

# ------------------------------------------------------------------------------
# This is a helper script for logging into Vault using App Role credentials.
# It's intended to be an executable and to run with only python 3.5+ and no
# other dependencies.
#
# The purpose of this script is to take a vault address, role_id and secret_id
# and login to generate a token. By default this script will print just the
# token, so it can be used to set the value of VAULT_TOKEN environment variable.
# 
# Run this script with --help for more details.
#
# ------------------------------------------------------------------------------
import json
import http.client
import os
from urllib.parse import urlparse

def get_client_token(options):
    body=json.dumps({
           "role_id": options.vault_role_id,
           "secret_id": options.vault_secret_id
           })

    url = urlparse(options.vault_address)

    conn = http.client.HTTPSConnection(*url.netloc.split(':'))
    conn.request('POST', '/v1/auth/approle/login', body)
    response = conn.getresponse()

    if response.code == 200:
        data = response.read()
        data = json.loads(data.decode('utf8'))
        return data
    else:
        print('Bad response for app-role login. code={code}, body={body}'.format(code=response.code, body=response.read()))


if __name__ == '__main__':

    import argparse

    parser = argparse.ArgumentParser(allow_abbrev=True)
    parser.add_argument('--vault_address', action='store', 
            help='Vault Address (ex. https://vault-prod.erboh.cloud)')

    parser.add_argument('--vault_role_id', action='store', 
            help='Vault App Role ID')

    parser.add_argument('--vault_secret_id', action='store', 
            help='Vault App Role Secret ID')

    parser.add_argument('--verbose', action='store_true', 
            help='Print the approle login response object. Otherwise just print the auth.client_token.',
            default=False)

    options = parser.parse_args()

    for prop in ('vault_address', 'vault_role_id', 'vault_secret_id'):
        if not getattr(options, prop):
            setattr(options, prop, os.environ.get(prop.upper()))

    if not (options.vault_secret_id and options.vault_role_id and options.vault_address):
        print('Not able to login with approle without having VAULT_ADDRESS, VAULT_SECRET_ID and VAULT_ROLE_ID')
        exit(1)

    data = get_client_token(options)

    if data:
        if options.verbose:
            print(json.dumps(data, indent=2))
        else:
            print(data['auth']['client_token'])
