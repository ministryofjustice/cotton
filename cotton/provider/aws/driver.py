from __future__ import print_function
import boto.ec2
import getpass
import time
import datetime
import dateutil.parser
import copy
import pprint
from fabric.api import abort, env, prompt
from cotton.colors import *
from cotton.provider.driver import Provider
from cotton.config import get_config
from cotton.config import get_provider_zone_config

class AWSProvider(Provider):

    connection = None

    def __init__(self, region_name=None, aws_access_key_id=None, aws_secret_access_key=None, **kwargs):
        """
        initializes connection object
        """
        self.connection = boto.ec2.connect_to_region(region_name=region_name,
                                                     aws_access_key_id=aws_access_key_id,
                                                     aws_secret_access_key=aws_secret_access_key)
        assert self.connection is not None

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
            abort(red("VM name already in use"))

        run_instances_args = dict()
        run_instances_args['image_id'] = zone_config['image_id']
        run_instances_args['key_name'] = zone_config['provisioning_ssh_key_name']
        run_instances_args['instance_type'] = zone_config['instance_type']
        if 'security_groups' in zone_config:
            run_instances_args['security_groups'] = zone_config['security_groups']

        reservation = self.connection.run_instances(**run_instances_args)
        instance = reservation.instances[0]

        instance.add_tag("Name", name)
        instance.add_tag("creator", getpass.getuser())

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
            print(yellow("Renamed to: {}".format(new_name)))
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
                        print("selected aws instance: {}".format(instance.id))

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
        info_dict["hostname"] = server.public_dns_name
        info_dict["id"] = server.id
        info_dict["type"] = server.instance_type
        info_dict["placement"] = server.placement
        info_dict["state"] = server.state
        info_dict["architecture"] = server.architecture
        info_dict["age"] = datetime.datetime.now()-dateutil.parser.parse(server.launch_time).replace(tzinfo=None)
        info_dict["tags"] = copy.deepcopy(server.tags)
        return info_dict

    def host_string(self, server):
        #TODO: where to select user/provisioning mode
        return self.info(server)["hostname"]
