from __future__ import print_function
import os
import sys
import time
import getpass
import datetime
import dateutil.parser
from functools import wraps

from fabric.api import run, task, env, settings, execute, prompt, hide, abort
from cotton.colors import *
from cotton.common import current_instance
import boto
from boto.s3.bucket import Bucket

from cotton import common
from cotton import config
from aws_specs import AWS_INSTANCE_SPECS, get_aws_specs
from boto.manage.server import Bundler, CommandLineGetter
import r53
import s3

#TODO: add key location

# Import AWS configuration from ../config dir
try:
    import config_aws
    config.aws = config_aws
except ImportError as e:
    import imp
    config.aws = imp.new_module("aws")


@task
def sg(name):
    """
    aws: sets security groups used for instance creation
    """
    config.aws.SECURITY_GROUPS = name.split(":")

@task
def key(name):
    """
    aws: sets ssh key used for instance creation
    """
    config.aws.KEY_PAIR_NAME = name


@task
def userdata(filename):
    """
    aws: sets the user data for the instance to the contents of the given file

    """
    config.aws.DEFAULT_USER_DATA_FILE = filename


### AWS selectors


@task
def name(instance_name):
    """
    aws: select host based on ec2 name
    i.e. fab name:wiki-new ssh
    """
    conn = get_ec2_connection()
    selected = False
    for reservation in conn.get_all_instances():
        instance = reservation.instances[0]
        if instance.state not in ['terminated', 'shutting-down']:
            if "Name" in instance.tags and instance.tags["Name"] == instance_name:
                env.hosts.append(instance.public_dns_name)
                configure_provider(instance.public_dns_name)
                env.instances[instance.public_dns_name] = instance
                selected = True
                print("selected aws instance: {}".format(instance.id))

    if not selected:
        print(red("Warning: {} not found!".format(instance_name), bold=True))

@task
def iid(instance_id):
    """
    aws: select host based on ec2 id
    i.e. fab iid:i-11223344 ssh
    """
    conn = get_ec2_connection()
    selected = False
    for reservation in conn.get_all_instances(instance_ids=[instance_id]):
        instance = reservation.instances[0]
        if instance.state not in ['terminated', 'shutting-down']:
            env.hosts.append(instance.public_dns_name)
            configure_provider(instance.public_dns_name)
            env.instances[instance.public_dns_name] = instance
            selected = True
            print("selected: {}".format(instance.id))

    if not selected:
        print(red("Warning: {} not found!".format(instance_id), bold=True))


@task
def role(instance_role):
    """
    aws: select host based on ec2 role
    i.e. fab role:wiki ssh
    """
    conn = get_ec2_connection()
    selected = False
    for reservation in conn.get_all_instances():
        instance = reservation.instances[0]
        if instance.state not in ['terminated', 'shutting-down']:
            if "roles" in instance.tags and instance_role in instance.tags["roles"].split(','):
                env.hosts.append(instance.public_dns_name)
                configure_provider(instance.public_dns_name)
                env.instances[instance.public_dns_name] = instance
                selected = True
                print("selected: {}".format(instance.id))

    if not selected:
        print(red("Warning: {} not found!".format(instance_role), bold=True))


@task
def stack(instance_role):
    """
    aws: select host based on ec2 stack
    i.e. fab stack:staging uptime
    """
    conn = get_ec2_connection()
    selected = False
    for reservation in conn.get_all_instances():
        instance = reservation.instances[0]
        if instance.state not in ['terminated', 'shutting-down']:
            if "stack" in instance.tags and instance.tags["stack"] == instance_role:
                env.hosts.append(instance.public_dns_name)
                configure_provider(instance.public_dns_name)
                env.instances[instance.public_dns_name] = instance
                selected = True
                print("selected: {}".format(instance.id))

    if not selected:
        print(red("Warning: {} not found!".format(instance_role), bold=True))



### AWS helper functions

def requires_ec2conn(func):
    """
    Decorator for all functions that need to access EC2. Sets env.ec2conn using
    get_ec2_connection().
    """
    @wraps(func)
    def inner(*args, **kwargs):
        get_ec2_connection()
        return func(*args, **kwargs)
    return inner


def get_ec2_connection():
    if not env.get('ec2conn'):
        env.ec2conn = boto.ec2.connect_to_region(
            config.aws.REGION,
            aws_access_key_id=config.aws.ACCESS_KEY_ID,
            aws_secret_access_key=config.aws.SECRET_ACCESS_KEY)
        assert env.ec2conn is not None
    return env.ec2conn


@task
def settag(key, value):
    """
    aws: set specific tag for EC2 host
    to allow setting lists replaces ';' with ','
    """
    if ";" in value:
        value = value.replace(';', ',')
    for instance in env.instances.values():
        instance.add_tag(key, value)


@task
def setname(new_name):
    """
    aws: set name for EC2 host
    """
    execute(settag, "Name", new_name)


@task
@current_instance
def terminate(instance):
    """
    aws: terminate EC2 instance
    """
    info()

    if env.force:
        sure = 'T'
    else:
        sure = prompt(red("Type 'T' to confirm termination"), default='N')

    if sure == 'T':
        #TODO: ask for enter to be pressed
        conn = get_ec2_connection()
        old_name = instance.tags.get("Name", "")
        new_name = "{}-deleting".format(old_name)
        instance.add_tag("Name", new_name)
        print(yellow("Renamed to: {}".format(new_name)))
        conn.terminate_instances(instance_ids=[instance.id])
        print("Terminated")
    else:
        print("Aborting termination")


### AWS instance methods

@task
@current_instance
def info(instance):
    """
    aws: display detailed info about EC2 instance
    """
    p_info = lambda key, value: print(yellow("{:<12} {}".format(key, value)))

    print(green("Info", bold=True))
    p_info("Hostname", instance.public_dns_name)
    p_info("id", instance.id)
    p_info("type", instance.instance_type)
    p_info("placement", instance.placement)
    p_info("state", instance.state)
    p_info("architecture", instance.architecture)
    p_info("age", datetime.datetime.now()-dateutil.parser.parse(instance.launch_time).replace(tzinfo=None))
    print(green("Tags"))
    for tag in sorted(instance.tags):
        p_info(tag, instance.tags[tag])


@task
def stop():
    """
    aws: stop EC2 instance
    """
    conn = get_ec2_connection()
    conn.stop_instances(instance_ids=[instance.id for instance in env.instances.values()])


def instance_to_resource(instance):
    """
    Takes an instance and returns some details of the instance as a resource
    """
    for instance_type in AWS_INSTANCE_SPECS:
        itype = instance_type()
        if instance.instance_type == itype.get_instancetype():
            start_time = datetime.datetime.strptime(
                instance.launch_time, "%Y-%m-%dT%H:%M:%S.000Z")
            upsecs = (datetime.datetime.now() - start_time).seconds
            updays = (datetime.datetime.now() - start_time).days
            uptime = upsecs + (updays * 24 * 60 * 60)
            cost = itype.price * uptime / 3600
            tags = instance.tags
            return {
                "id": instance.id,
                "rate": itype.price,
                "cost": cost,
                "uptime": uptime,
                "type": instance.instance_type,
                "state": instance.state,
                "placement": instance.placement,
                "public_dns_name": instance.public_dns_name,
                "tags": tags,
                "name": instance.tags.get("Name", None),
                "creator": instance.tags.get("creator", ''),
                "roles": instance.tags.get("roles", ''),
                "stack": instance.tags.get("stack", ''),
                "project": instance.tags.get("project", 'default')
            }


@task
@requires_ec2conn
def status(sort_key=None, owner=None):
    """
    aws: EC2 status of running instances
    """
    
    if owner == 'me':
        owner = env.user
    
    resources = list()
    for reservation in env.ec2conn.get_all_instances():
        instance = reservation.instances[0]
        if instance.state != 'terminated':
            resource = instance_to_resource(instance)
            if resource:
                resources.append(resource)
            else:
                print(red("Unsupported instance: {}".format(instance)))

    if sort_key:
        decorated = [(dict_[sort_key], dict_) for dict_ in resources]
        decorated.sort(reverse=True)
        sorted_resources = [dict_ for (key, dict_) in decorated]
        resources = sorted_resources
        print(green(
            "{:<12} {:<24} {:<10} {:<10} {:<10} {:<10} {:<9} {:<9} {:<9} {:<9} {:<9}".format(
                "ID", "Name", "Project", "Stack", "Type", "Hourly$", "Total$", "HoursUp", "DaysUp", "Roles", "Creator"), bold=True))
        for r in resources:
            print(yellow(
                "{0:<12} {1:<24} {2:<10} {3:<10} {4:<10} {5:<5.2f} {6:<5.2f} {7:<5} {8:<5} {9:<10} {10:<10}".format(
                r['id'],
                r['name'],
                r['project'],
                r['stack'],
                r['type'],
                r['rate'],
                r['cost'],
                r['uptime'] / (3600),
                r['uptime'] / (3600 * 24),
                r['roles'],
                r['creator'])))
    else:
        print(green(
            "{:<12} {:<24} {:<10} {:<14} {:<10} {:<10} {:<14} {:<11} {:<52} {:<10}".format(
                "ID", "Name", "Project", "Stack", "Type", "State", "Creator", "Placement", "Public name", "Roles"), bold=True))
        for r in resources:
            if owner and r['creator'] != owner:
                continue
            print(yellow(
                "{:<12} {:<24} {:<10} {:<14} {:<10} {:<10} {:<14} {:<11} {:<52} {:<10}".format(
                r['id'],
                r['name'],
                r['project'],
                r['stack'],
                r['type'],
                r['state'],
                r['creator'],
                r['placement'],
                r['public_dns_name'],
                r['roles'])))


### AWS storage methods


@task
def status_ebs():
    """
    aws: EBS status
    """
    conn = get_ec2_connection()
    print("{:<12} {:<32} {:<12} {:<12}".format("ID", "Name", "Zone", "Status"))
    for v in conn.get_all_volumes():
        v_name = v.tags.get("Name", None)
        print("{:<12} {:<32} {:<12} {:<12}".format(
            v.id, v_name, v.zone, v.status
        ))


@task
def backup_ebs(volume_id, bucket_name='latest', bucket_size=3):
    """
    aws: backup specific EBS volume
    """
    conn = get_ec2_connection()
    for volume in conn.get_all_volumes([volume_id]):
        _backup_ebs(volume, bucket_name=bucket_name, bucket_size=bucket_size)


def _backup_ebs(volume, bucket_name, bucket_size):
    description = "Backup of {}:{}".format(volume.id, volume.tags.get("Name", None))
    print(green(description))

    vs = volume.create_snapshot(description=description)
    vs.add_tag("bucket", bucket_name)

    snapshots = volume.snapshots()
    snapshots_sorted = sorted(filter(lambda x: x.tags.get("bucket", None) == bucket_name, snapshots), key=lambda x: x.start_time, reverse=True)
    for s in snapshots_sorted[bucket_size:]:
        s.delete()
    snapshots_sorted = snapshots_sorted[:bucket_size]

    format_string = "{:<14} {:<25} {:<12} {:<12} {:<12}"

    print(format_string.format("ID", "Started", "Bucket", "Status", "Description"))
    for snapshot in snapshots_sorted:
        print(format_string.format(snapshot.id, snapshot.start_time, snapshot.tags.get("bucket", None), snapshot.status, snapshot.description))


@task
def backup_all_ebs(bucket_name='latest', bucket_size=3):
    """
    aws: backup all EBS volumes
    """
    conn = get_ec2_connection()
    for volume in conn.get_all_volumes():
        print(volume)
        _backup_ebs(volume, bucket_name, bucket_size)

@task
def get_ami_id(name=None, all_images=False):
    """Try finding one with the default name at Amazon, fall back to config"""
    conn = get_ec2_connection()
    if env.os == 'ubuntu':
        return config.aws.AMIS[env.os]
    images = conn.get_all_images(owners=['self'])
    if all_images:
        return images
    # Return the id for the specified image name
    for image in images:
        if 'name' in image.tags:
            if image.tags['name'] == name:
                print(image)
                print(image.id)
                return image.id
    # Return the id of the default image name
    for image in images:
        if 'name' in image.tags:
            if image.tags['name'] == config.aws.DEFAULT_AMI:
                print(image)
                print(image.id)
                return image.id
    # Return the fallback image id
    print("fallback")
    print(config.aws.AMIS[config.aws.DEFAULT_AMI])
    return config.aws.AMIS[config.aws.DEFAULT_AMI]


def create_instance(
        instance_type='m1.small',
        name="new-instance",
        security_groups=None,
        key_pair_name=None,
        tags=None,
        ami_id=None):
    """
    Create an AWS instance
    """
    
    if not security_groups:
        security_groups = config.aws.SECURITY_GROUPS
    common.provisioning()
    configure_provider()
    env.key_filename = config.aws.PROVISIONING_SSH_KEY_FILE
    if ami_id is None:
        ami_id = get_ami_id()

    conn = get_ec2_connection()

    if env.os == 'centos':
        user_data_file = os.path.join(env.templates_dir, "aws-user-data")
        with open(user_data_file, 'r') as f:
            user_data = f.read()
            reservation = conn.run_instances(
                ami_id,
                kernel_id=config.aws.AKIS[config.aws.DEFAULT_AKI],
                key_name=key_pair_name,
                instance_type=instance_type,
                user_data=user_data,
                security_groups=security_groups)
    else:
        reservation = conn.run_instances(
            ami_id,
            key_name=key_pair_name,
            instance_type=instance_type,
            security_groups=security_groups)

    instance = reservation.instances[0]

    instance.add_tag("Name", name)
    instance.add_tag("creator", getpass.getuser())

    if tags:
        for k, v in tags.iteritems():
            instance.add_tag(k, v)

    print("Waiting for instance to run",)
    while instance.state != 'running':
        instance.update()
        sys.stdout.write(".")
        sys.stdout.flush()
        time.sleep(1)
    print(" OK")

    with settings(host_string=instance.public_dns_name):
        common.wait_for_shell()
    env.providerforhost[instance.public_dns_name] = 'aws'
    env.instances[instance.public_dns_name] = instance

    return instance


@current_instance
def hostroles(instance):
    """
    Return the host's roles based on AWS tags
    """
    if "roles" in instance.tags:
        return instance.tags["roles"].split(',')
    else:
        return []

@current_instance
def hoststack(instance):
    """
    Return the host's stack based on its AWS tags
    """
    if "stack" in instance.tags:
        return instance.tags["stack"]
    else:
        return "development"


def configure_provider(host_string=None):
    """
    configure provider for host and sets global variables
    """
    if env.provisioning:
        env.key_filename = config.aws.PROVISIONING_SSH_KEY_FILE
        env.user = config.aws.PROVISIONING_USER
    else:
        env.key_filename = config.aws.SSH_KEY_FILE
        env.user = config.aws.USER

    if host_string:
        env.providerforhost[host_string] = 'aws'


def create_ebs_volume(size, instance_name, availability_zone):
    """
    Create new ebs device(s) up to <size> GB and return the volume ids
    providing it/them."""

    # AWS officially support from 10GB up to 1TB volumes however smaller
    # disks appear to possible.
    volume_ids = []
    if size < 1:
        raise ValueError("Size of must be greater than 1GB (AWS claim 10GB).")

    volumes = [1000 for _ in range(size / 1000)] + [size % 1000]
    conn = get_ec2_connection()
    # TODO: Handle a network timeout or other error more gracefully
    # Perhaps send an email to an admin to manually delete the volumes by id
    for disk_chunk in volumes:
        vol = conn.create_volume(disk_chunk, availability_zone)

        # AWS seems pretty quick today but maybe do dhcp-like retries
        while conn.get_all_volumes([vol.id])[0].status != u'available':
            time.sleep(1)
        volume_ids.append(vol.id)

    return volume_ids


def attach_ebs_volume(volume_id, instance_name, device):
    """Attach volumes to an instance as device."""
    name(instance_name)
    conn = get_ec2_connection()
    assert len(env.instances) == 1
    instance_id = None
    for instance in env.instances.values():
        instance_id = instance.id
    conn.attach_volume(volume_id, instance_id, device)

    # AWS seems pretty quick today but maybe do dhcp-like retries
    while conn.get_all_volumes([volume_id])[0].status != u'in-use':
        time.sleep(1)


def ec2_name_exists(name):
    conn = get_ec2_connection()
    names = set((x.instances[0].tags["Name"]
                 if x.instances[0].state != 'terminated'
                    and "Name" in x.instances[0].tags
                 else
                    None
                 for x in conn.get_all_instances()))
    return name in names


def clean_golden_image_bucket():
    """Delete golden image bucket objects that have no AMIs referencing them"""
    s3conn = s3.get_s3_connection()
    bucket = Bucket(s3conn, config.aws.S3_BUCKETS['GOLDEN_IMAGE_BUCKET'])
    all_s3_objects = []
    s3_objects_in_use = []
    s3_objects_to_delete = []
    all_images = get_ami_id(all_images=True)

    for image in all_images:
        try:
            bucketname, foldername, manifestname = image.location.split('/')
        except ValueError:
            bucketname, foldername = image.location.split('/')
        if bucketname == config.aws.S3_BUCKETS['GOLDEN_IMAGE_BUCKET']:
            s3_objects_in_use.append(foldername)

    for item in bucket.list():
        path_part = item.key.split('/')[0]
        if path_part not in all_s3_objects:
            all_s3_objects.append(path_part)

    for item in all_s3_objects:
        if item not in s3_objects_in_use:
            for s3item in bucket.list():
                if item == s3item.key.split('/')[0]:
                    if item not in s3_objects_to_delete:
                        s3_objects_to_delete.append(s3item)

    for item in s3_objects_to_delete:
        item.delete()

    return


@task
@current_instance
def associate_address(ip_address, instance):
    """
    associate elastic ip address with a server
    """
    conn = get_ec2_connection()
    conn.associate_address(instance.id, ip_address)
    print(green("Address {} has been successfully associated with {}".format(ip_address, instance.id)))


@task
def specs():
    """Prints AWS specs"""
    get_aws_specs()


@current_instance
def set_roles(roles, instance):
    settag('roles', ";".join(roles))


@current_instance
def getgrains(instance):
    grains = instance.tags.copy()

    # let's sanitize the structure
    grains['name'] = instance.tags['Name']
    grains['roles'] = instance.tags.get('roles', '').split(",")
    return grains

