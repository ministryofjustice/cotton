from __future__ import print_function
import boto.ec2
import getpass
import time
import datetime
import dateutil.parser
import copy
import pprint
from fabric.api import abort, env, prompt
from xml.etree import ElementTree as ET
from lxml import etree as lxml_ET
from cotton.colors import *
from cotton.provider.driver import Provider
from cotton.config import get_config
from cotton.config import get_provider_zone_config
import libcloud.compute.base
from libcloud.compute.base import NodeImage
from libcloud_skyscape import ImprovedVCloud_5_1_Driver

class VCloudProvider(Provider):
    """
    Class assumes that you are only using single vm per vapp configuration.
    A lowest common denominator with AWS
    """

    connection = None
    org = None

    def __init__(self, org=None, api=None, **kwargs):
        """
        initializes connection object
        """
        print(yellow("authenticating as user: {}".format(api['username'])))
        print(yellow("org name: {}".format(org)))
        self.connection = ImprovedVCloud_5_1_Driver(
            key='%(user)s@%(org)s' % {
                'user': api['username'],
                'org': org,
            },
            secret=api['password'],
            host=api['host'],
        )
        self.connection.connection.check_org()
        print(green("authentication: success"))
        print(yellow("org uuid: {}".format(self.connection.org.split('/')[-1])))

    def status(self):
        """
        lists all vms in all vapps
        """
        instances = []
        vapps = self.filter()
        for vapp in vapps:
            instance_data = self.info(vapp)
            instances.append(instance_data)
        return instances

    def create(self, name=None, size=None, vdc=None, net_fence='bridged', network='Default', ip_address=None, template=None, tags={},
               **kwargs):
        """
        return: server object
        instance is booting so don't forget to cotton.fabextras.wait_for_shell()
        """
        print("name: {}".format(name))
        print("size: {}".format(size))
        print("vdc: {}".format(vdc))
        print("net_fence: {}".format(net_fence))
        print("network: {}".format(network))
        print("ip_address: {}".format(ip_address))
        zone_config = get_provider_zone_config()
        memory = zone_config['sizes'][size]['memory']
        cpu = zone_config['sizes'][size]['cpu']

        result = self.filter(name=name)
        if result:
            abort(red("VM name already in use"))

        assert size is not None
        assert template is not None

        image = NodeImage(
            id='https://{}/api/vAppTemplate/vappTemplate-{}'.format(zone_config['api']['host'], template),
            name=name,
            driver=self.connection,
        )

        # Libcloud doesn't find networks right when the name is shared across vDCs.
        res = self.connection.ex_query(
            type='orgVdcNetwork',
            filter='vdcName=={};name=={}'.format(vdc, network),
            format='references'
        )

        if not res:
            abort(red("Cannot find network '{}' in vDC '{}'!".format(network, vdc), bold=True))
        network = res[0]['href']
        print(res)
        print("network: {}".format(network))

        node = self.connection.create_node(
            image=image,
            name=name,
            ex_vdc=vdc,
            ex_vm_fence=net_fence,
            ex_network=network,
            ex_vm_memory=memory,
            ex_vm_cpu=cpu,
            ex_vm_names=[name],
            ex_vm_ipmode=ip_address,
        )
        if tags:
            self.connection.ex_set_metadata_entries(node, **tags)

    def terminate(self, vapp):
        assert isinstance(vapp, libcloud.compute.base.Node)
        vapp.destroy()

    @classmethod
    def _filter_to_vdc(cls, vapps):
        zone_config = get_provider_zone_config()
        if zone_config.get('vdc-filter', False):
            filtered = []
            for vapp in vapps:
                if vapp.extra['vdc'] == zone_config['vm-defaults']['vdc']:
                    filtered.append(vapp)
            return filtered
        else:
            return vapps

    def filter(self, **kwargs):
        """
        return: list of objects matching filter args
        typically provide should support filter 'name'='foo'
        """
        if 'name' in kwargs:
            name = kwargs['name']
            vapps = []
            for vapp in self._filter_to_vdc(self.connection.list_nodes()):
                if vapp.name == name:
                    vapps.append(vapp)
#            res = self.connection.ex_query('vApp', 'name=={}'.format(name))
#            from IPython import embed
#            embed()
            return self._filter_to_vdc(vapps)
        elif len(kwargs) == 0:
            return self._filter_to_vdc(self.connection.list_nodes())
        else:
            raise NotImplementedError()

    def info(self, vapp):
        """
        returns dictionary with info about server (????)
        """
        assert isinstance(vapp, libcloud.compute.base.Node)
        return {
            'vapp_name': vapp.name,
            'state': vapp.state,
            'private_ip': vapp.private_ips,
            'vdc': vapp.extra['vdc'],
            'vm_state': vapp.extra['vms'][0]['state'],
            'size': self._find_node_size(vapp.size)
        }

    def host_string(self, vapp):
        """
        returns host_string in fab format such that we can ssh to server
        """
        assert isinstance(vapp, libcloud.compute.base.Node)
        if vapp.private_ips:
            return vapp.private_ips[0]
        else:
            print(red('Server IP is unknown'))
            return ''

    def _get_metadata(self, instance):
        #opportunity for grains storage, unused
        return self.connection.ex_get_metadata(instance)

    @classmethod
    def _find_node_size(cls, node_size):
        zone_config = get_provider_zone_config()
        for name, size in sorted(zone_config['sizes'].items(), key=lambda t: t[1]):
            if node_size.ram <= size['memory'] and node_size.cpus <= size['cpu']:
                return name
        return 'xx-large-unknown'
