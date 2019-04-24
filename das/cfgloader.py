import argparse
import os
from azure.storage.blob import BlockBlobService
'''
AzureCfgLoader
Simple config loader, copies app config from storage bucket to a .env
file in the Django settings directory
'''

class AzureCfgLoader():

    def __init__(self, account, container, access_key):
        self.blob_svc = BlockBlobService(account_name=account, account_key=access_key)
        self.container = container

    def fetch_env_config(self):
        self.blob_svc.get_blob_to_path(self.container, f'{self.container}.env','das_server/.env')

if __name__ == '__main__':

    if os.environ.get('USE_AZURE_STORAGE', 'false') == 'true':
        parser = argparse.ArgumentParser(description='config_loader')
        parser.add_argument('--storagetype', default=os.environ.get('STORAGE_TYPE', 'azure'))
        parser.add_argument('--account', default=os.environ.get('CONFIG_ACCOUNT', 'dasconfigwesteurope'))
        parser.add_argument('--container', default=os.environ.get('CONFIG_CONTAINER', ''))
        parser.add_argument('--accesskey', default=os.environ.get('CONFIG_ACCOUNT_KEY', ''))
        args = parser.parse_args()

        # for now, we'll assume azure. We'll fill in gcp and S3 via boto
        # the .env file is expected to be in the same directory as the settings files
        loader = AzureCfgLoader(args.account, args.container, args.accesskey)
        loader.fetch_env_config()