import argparse
import json
import logging
import sys
import time
# pyyaml sorts keys. oyaml does not
import oyaml as yaml
from dotmap import DotMap

log_format = '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
logging.basicConfig(stream=sys.stdout, level=logging.INFO, format=log_format)
logging.Formatter.converter = time.gmtime
logger = logging.getLogger('config-generator')


class TerraformExtractor:
    # Well known fields name for infrastructure. We concatentate
    # the appropriate partner or site name to find the values
    # of the keys in the terraform output
    TF_PARTNER_INFRA_FIELDS = {
        'storage_account_name': 'STORAGE_ACCOUNT',
        'storage_container_name': 'STORAGE_CONTAINER',
        'storage_account_primary_access_key_vault_path': 'STORAGE_ACCOUNT_KEY',
        'db_server_fqdn': 'DB_HOST',
    }

    TF_SITE_INFRA_FIELDS = {
        'db_name': 'DB_NAME',
        'db_name': 'DB_USER',
        'db_login_password_vault_path': 'DB_PASSWORD',
    }

    @classmethod
    def extract_infra_keys(cls, cluster, site, json_file):
        with open(args.tcfg) as json_file:
            terra_data = json.load(json_file)
        partner_fields = cls.extract_config_keys(args.partner, cls.TF_PARTNER_INFRA_FIELDS, terra_data)
        site_fields = cls.extract_config_keys(args.site, cls.TF_SITE_INFRA_FIELDS, terra_data)
        return {**partner_fields, **site_fields}

    @staticmethod
    def extract_config_keys(prefix, infra_dict, tf_dict):
        env_dict = {}
        for key in infra_dict.keys():
            infra_key = '{}_{}'.format(prefix, key)
            env = { infra_dict[key] : tf_dict[infra_key]['value'] }
            env_dict.update(env)
        return env_dict


class DasEnvironmentExtractor:

    CFG_FIELDS = {
        'email.host_user': 'EMAIL_USER',
        'email.info': 'EMAIL_INFO',
        'email.notification': 'EMAIL_NOTIFICATION',
    }

    @classmethod
    def extract_config_keys(cls, env_data):
        data = DotMap(env_data)
        env_dict = {}
        return env_dict


def parse_command_line():
    parser = argparse.ArgumentParser(
        description='Generate config for AKS site')
    parser.add_argument('-p', '--partner', help='Partner/cluster name for deployment', required=True)
    parser.add_argument('-s', '--site', help='Site/pipeline name for deployment', required=True)
    parser.add_argument('-t', '--tcfg', help='Terraform output file', required=True)

    args = parser.parse_args()
    return args


if __name__ == '__main__':
    args = parse_command_line()
    infra_fields = TerraformExtractor.extract_infra_keys(args.partner, args.site, args.tcfg)
    cfg_data = \
        {'apiVersion' : 'v1',
         'kind' : 'Configmap',
         'metadata' : {'namespace' : '<<namespace>>', 'name' : 'site-configmap'},
         'data' : infra_fields
         }

    print(yaml.dump(cfg_data, default_flow_style=False))






