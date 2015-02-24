from __future__ import print_function
import getpass
import time
import datetime
import dateutil.parser
import copy
import pprint

import boto
import boto.ec2
import boto.cloudformation
import boto.iam

from fabric.api import env, prompt

from cotton.colors import *
from cotton.provider.driver import Provider
from cotton.config import get_provider_zone_config


class AWSProvider(Provider):

    connection = None
    _cloudformation_connection = None
    _route53_connection = None
    _s3_connection = None
    _iam_connection = None

    acl = dict()

    def __init__(self, region_name=None, aws_access_key_id=None, aws_secret_access_key=None, **kwargs):
        """
        initializes connection object
        """
        self.connection = boto.ec2.connect_to_region(region_name=region_name,
                                                     aws_access_key_id=aws_access_key_id,
                                                     aws_secret_access_key=aws_secret_access_key)
        self.acl['region_name'] = region_name
        self.acl['aws_access_key_id'] = aws_access_key_id
        self.acl['aws_secret_access_key'] = aws_secret_access_key

        assert self.connection is not None

    @property
    def ec2_connection(self):
        """
        just to keep naming convention
        :return: the same as self.connection
        """
        return self.connection

    @property
    def cloudformation_connection(self):
        """
        :return: boto cloudformation connection object based on __init__ credentials
        """
        if self._cloudformation_connection is None:
            self._cloudformation_connection = boto.cloudformation.connect_to_region(
                aws_access_key_id=self.acl['aws_access_key_id'],
                aws_secret_access_key=self.acl['aws_secret_access_key'],
                region_name=self.acl['region_name'])
        return self._cloudformation_connection

    @property
    def route53_connection(self):
        """
        :return: boto route53 connection object based on __init__ credentials
        """
        if self._route53_connection is None:
            self._route53_connection = boto.connect_route53(
                aws_access_key_id=self.acl['aws_access_key_id'],
                aws_secret_access_key=self.acl['aws_secret_access_key'])
        return self._route53_connection

    @property
    def s3_connection(self):
        """
        :return: boto s3 connection object based on __init__ credentials
        """
        if self._s3_connection is None:
            self._s3_connection = boto.s3.connect_to_region(
                aws_access_key_id=self.acl['aws_access_key_id'],
                aws_secret_access_key=self.acl['aws_secret_access_key'],
                region_name=self.acl['region_name'])
        return self._s3_connection

    @property
    def iam_connection(self):
        """
        :return: boto iam connection object based on __init__ credentials
        """
        if self._iam_connection is None:
            self._iam_connection = boto.iam.connect_to_region(
                aws_access_key_id=self.acl['aws_access_key_id'],
                aws_secret_access_key=self.acl['aws_secret_access_key'],
                region_name=self.acl['region_name'])
        return self._iam_connection

    def status(self):
        instances = []
        for reservation in self.connection.get_all_instances():
            instance = reservation.instances[0]
            if instance.state != 'terminated':
                instance_data = self.info(instance)
                instances.append(instance_data)
        return instances

    def create(self, name=None, **kwargs):
        """
        return: aws instance object
        instance is booting so don't forget to cotton.fabextras.wait_for_shell()
        """
        zone_config = get_provider_zone_config()

        result = self.filter(name=name)
        if result:
            raise ValueError("VM name already in use")

        run_instances_args = dict()
        run_instances_args['image_id'] = zone_config['image_id']
        run_instances_args['key_name'] = zone_config['provisioning_ssh_key_name']
        run_instances_args['instance_type'] = zone_config['instance_type']

        if 'subnet_id' in zone_config:
            print("Found subnet_id - creating instance within VPC")
            run_instances_args['subnet_id'] = zone_config['subnet_id']
            if 'security_groups' in zone_config:
                raise ValueError("VPC does not accept security_groups - use security_groups_ids instead")
            if 'security_groups_ids' in zone_config:
                run_instances_args['security_group_ids'] = zone_config['security_groups_ids']
        else:
            if 'security_groups_ids' in zone_config:
                raise ValueError("Non VPC does not accept security_group_ids - use security_groups instead")
            if 'security_groups' in zone_config:
                run_instances_args['security_groups'] = zone_config['security_groups']

        if 'root_ebs_size' in zone_config or 'root_ebs_type' in zone_config:
            dev_sda1 = boto.ec2.blockdevicemapping.EBSBlockDeviceType(delete_on_termination=True)
            if 'root_ebs_size' in zone_config:
                dev_sda1.size = zone_config['root_ebs_size'] # size in Gigabytes
            if 'root_ebs_type' in zone_config:
                dev_sda1.volume_type = zone_config['root_ebs_type']
            bdm = boto.ec2.blockdevicemapping.BlockDeviceMapping()
            bdm['/dev/sda1'] = dev_sda1
            run_instances_args['block_device_map'] = bdm

        reservation = self.connection.run_instances(**run_instances_args)
        instance = reservation.instances[0]

        instance.add_tag("Name", name)
        instance.add_tag("creator", getpass.getuser())

        if 'tags' in kwargs:
            for key in kwargs['tags']:
                instance.add_tag(key, kwargs['tags'][key])

        print("Waiting for instance to run",)
        while instance.state != 'running':
            instance.update()
            sys.stdout.write(".")
            sys.stdout.flush()
            time.sleep(1)
        print(" OK")
        return instance

    def terminate(self, server):
        pprint.pprint(self.info(server))

        if env.force:
            sure = 'T'
        else:
            sure = prompt(red("Type 'T' to confirm termination"), default='N')

        if sure == 'T':
            old_name = server.tags.get("Name", "")
            new_name = "{}-deleting".format(old_name)
            server.add_tag("Name", new_name)
            print(green("Renamed to: {}".format(new_name)))
            self.connection.terminate_instances(instance_ids=[server.id])
            print("Terminated")
        else:
            print("Aborting termination")

    def filter(self, **kwargs):
        """
        return: list of objects matching filter args
        typically provide should support filter 'name'='foo'
        """
        instances = []

        if 'name' in kwargs:
            name = kwargs['name']
            selected = False
            for reservation in self.connection.get_all_instances():
                instance = reservation.instances[0]
                if instance.state not in ['terminated', 'shutting-down']:
                    if "Name" in instance.tags and instance.tags["Name"] == name:
                        instances.append(instance)
                        selected = True
                        print(green("Selected aws instance: {}".format(instance.id)))

            if not selected:
                print(yellow("Warning: {} not found!".format(name), bold=True))
        else:
            raise NotImplementedError()

        return instances

    def info(self, server):
        """
        returns dictionary with info about server
        """
        info_dict = dict()
        info_dict["ip"] = server.private_ip_address
        info_dict["hostname"] = server.public_dns_name
        info_dict["id"] = server.id
        info_dict["type"] = server.instance_type
        info_dict["placement"] = server.placement
        info_dict["state"] = server.state
        info_dict["architecture"] = server.architecture
        info_dict["age"] = datetime.datetime.now()-dateutil.parser.parse(server.launch_time).replace(tzinfo=None)
        tags = info_dict["tags"] = copy.deepcopy(server.tags)

        if "Role" in tags:
            info_dict["roles"] = [tags["Role"]]
        elif "Roles" in tags:
            info_dict["roles"] = tags["Roles"].split(',')
        elif "roles" in tags:
            info_dict["roles"] = tags["roles"].split(',')
        else:
            info_dict["roles"] = []

        info_dict["roles"] = map(lambda x: x.encode('utf-8'), info_dict["roles"])

        return info_dict

    def host_string(self, server):
        if self.info(server)["hostname"]:
            # public dns entry is available
            return self.info(server)["hostname"]
        else:
            # only private ip is available so user will need to be using jumpbox
            return self.info(server)["ip"]
