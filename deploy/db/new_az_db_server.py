#!/usr/bin/env python3
import argparse
import os
import subprocess
import sys
import uuid 

def parse_command_line():
    parser = argparse.ArgumentParser(
        description='Postgres for Azure creation tool. Note: Requires az cli to be installed')
    parser.add_argument('-s', '--server', help='DB server hostname', required=True)
    parser.add_argument('-g', '--group', help='Azure resource group', default='DAS-Dev')
    parser.add_argument('-l', '--location', help='DB server datacenter location', default='eastus')
    parser.add_argument('--username', default='postgres', help='DB admin username')
    parser.add_argument('--sku', default='GP_Gen5_2', help='DB size [basic, GP_Gen5_2]')
    args = parser.parse_args()
    return args

args = parse_command_line()
admin_passwd = str(uuid.uuid4()).replace('-','')

# Ref: https://docs.microsoft.com/en-gb/cli/azure/postgres/server?view=azure-cli-latest#az-postgres-server-create
# SKUs: https://docs.microsoft.com/en-us/azure/postgresql/concepts-pricing-tiers
#       {pricing tier}_{compute generation}_{vCores}
create_server_command = [
    'az', 'postgres', 'server', 'create',
    '--resource-group', args.group,
    '--location', args.location,
    '--name', args.server,
    '--admin-user', args.username,
    '--admin-password', admin_passwd,
    '--sku-name', args.sku,
]

create_prompt = 'Create PostgreSQL server {}? [y/n]: '.format(args.server)
create_server = input(create_prompt)
if create_server == 'y':
    print("Creating PostgreSQL server...")
    subprocess.check_call(create_server_command)
else:
    sys.exit(1)

# Set up firewall.
# Ref: https://docs.microsoft.com/en-gb/cli/azure/postgres/server/firewall-rule?view=azure-cli-latest#az-postgres-server-firewall-rule-create
azure_firewall_command = [
    'az', 'postgres', 'server', 'firewall-rule', 'create',
    '--resource-group', args.group,
    '--server-name', args.server,
    '--start-ip-address', '0.0.0.0',
    '--end-ip-address', '0.0.0.0',
    '--name', 'AllowAllAzureIPs',
]

local_ip_firewall_command = [
    'az', 'postgres', 'server', 'firewall-rule', 'create',
    '--resource-group', args.group,
    '--server-name', args.server,
    '--start-ip-address', '216.220.194.1',
    '--end-ip-address', '216.220.194.254',
    '--name', 'VulcanEgress',
]

create_rule = input('Create firewall rules? [y/n]: ')
if create_rule == 'y':
    print("Allowing access from Azure...")
    subprocess.check_call(azure_firewall_command)
    print("Allowing access from local IP...")
    subprocess.check_call(local_ip_firewall_command)


create_db_command = [
    'az', 'postgres', 'db', 'create',
    '--resource-group', args.group,
    '--server-name', args.server,
    '--name', os.getenv('APP_DB_NAME'),
]

create_app_db = input('Create App DB? [y/n]: ')
if create_app_db == 'y':
    print("Creating App DB...")
    subprocess.check_call(create_db_command)


connect_details_command = [
    'az', 'postgres', 'server', 'show',
    '--resource-group', args.group,
    '--name', args.server,
]
print("Getting access details...")
subprocess.check_call(connect_details_command)

# Connect to Azure using connection string format (to force SSL)
# psql "host=$POSTGRES_HOST sslmode=require port=5432 user=$POSTGRES_ADMIN_USER@$POSTGRES_SERVER_NAME dbname=postgres" -W
