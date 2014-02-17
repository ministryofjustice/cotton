"""
Tasks for managing Route 53

# TODO: 
    * manage multiline values
    * DRY up the *_record tasks.

"""
import sys

import boto

from fabric.api import task, env
from fabric.contrib.console import confirm

from cotton import config

try:
    import config_aws
    config.aws = config_aws
except ImportError as e:
    import imp
    config.aws = imp.new_module("aws")


def get_r53_connection():
    conn = boto.connect_route53(
        aws_access_key_id=config.aws.ACCESS_KEY_ID,
        aws_secret_access_key=config.aws.SECRET_ACCESS_KEY)
    assert conn is not None
    return conn

@task
def list_zones():
    zones = get_r53_connection().get_all_hosted_zones()
    for host in zones['ListHostedZonesResponse']['HostedZones']:
        print "\t * %s (%s records)" % (host['Name'], 
                                        host['ResourceRecordSetCount'])

@task
def zone(zone_name):
    env.zone = get_r53_connection().get_zone(zone_name)

@task
def list_records():
    records = env.zone.get_records()
    for record in records:
        print "\t * %s (%s)" % (record.name, record.type)


@task
def create_record(record_type, name, value, ttl=300):
    """
    Creates an A, CNAME or MX record on Route 53.
    
    Usage: fab a.r53.zone:[r53 zone] a.r53.create_record:[type],[name],[value]
    """
    record_type = record_type.upper()
    if record_type not in ('A', 'CNAME', 'MX'):
        raise ValueError('Invalid record_type')

    zone = env.zone
    if record_type == "A":
        zone.add_a(name, value, ttl)
    if record_type == "CNAME":
        zone.add_cname(name, value, ttl)
    if record_type == "MX":
        zone.add_mx(name, value, ttl)

@task
def update_record(record_type, name, value, ttl=300):
    """
    Updates an A, CNAME or MX record on Route 53.
    
    Usage: fab a.r53.zone:[r53 zone] a.r53.update_record:[type],[name],[value]
    """
    record_type = record_type.upper()
    if record_type not in ('A', 'CNAME', 'MX'):
        raise ValueError('Invalid record_type')
    
    zone = env.zone

    if not confirm(
        "Are you sure you want to update the record %s in the zone %s?" %
        (name, zone.name), 
        default=False):
        sys.exit()
    
    if record_type == "A":
        zone.update_a(name, value, ttl)
    if record_type == "CNAME":
        zone.update_cname(name, value, ttl)
    if record_type == "MX":
        zone.update_mx(name, value, ttl)

@task
def delete_record(record_type, name, value, ttl=300):
    """
    Deletes an A, CNAME or MX record on Route 53.
    
    Usage: fab a.r53.zone:[r53 zone] a.r53.delete_record:[type],[name],[value]
    """
    
    record_type = record_type.upper()
    if record_type not in ('A', 'CNAME', 'MX'):
        raise ValueError('Invalid record_type')
    
    if not confirm(
        "Are you sure you want to delete the record %s in the zone %s?" %
        (name, zone.name), 
        default=False):
        sys.exit()
    
    zone = env.zone
    if record_type == "A":
        zone.delete_a(name)
    if record_type == "CNAME":
        zone.delete_cname(name)
    if record_type == "MX":
        zone.delete_mx(name)

@task
def create_cname(cname):
    """
    Assign a given cname to the selected amazon host. 
    """
    create_record('cname', cname, env['host_string'])
